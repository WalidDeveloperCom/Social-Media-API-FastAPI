#!/usr/bin/env python3
"""
Migration script for Social Media API

Usage:
    python scripts/migrate.py upgrade        # Run all migrations
    python scripts/migrate.py downgrade -1   # Downgrade one revision
    python scripts/migrate.py create "Add new field"  # Create migration
    python scripts/migrate.py history        # Show migration history
    python scripts/migrate.py status         # Check migration status
"""
import asyncio
import argparse
import sys
import os
from pathlib import Path
from typing import Optional

# Add the app directory to the Python path
current_dir = Path(__file__).parent
root_dir = current_dir.parent
sys.path.insert(0, str(root_dir))

async def run_alembic_command(args_list: list) -> None:
    """Run Alembic command directly"""
    from alembic.config import CommandLine
    
    # Create command line interface
    alembic = CommandLine()
    
    # Modify sys.argv to pass arguments to Alembic
    original_argv = sys.argv
    try:
        sys.argv = ['alembic'] + args_list
        alembic.run_cmd()
    except SystemExit as e:
        if e.code != 0:
            raise
    finally:
        sys.argv = original_argv

async def upgrade(revision: str = "head") -> None:
    """Upgrade database to a specific revision"""
    print(f"🔧 Upgrading database to revision: {revision}")
    await run_alembic_command(["upgrade", revision])
    print("✅ Database upgraded successfully")

async def downgrade(revision: str) -> None:
    """Downgrade database to a specific revision"""
    print(f"🔧 Downgrading database to revision: {revision}")
    await run_alembic_command(["downgrade", revision])
    print("✅ Database downgraded successfully")

async def create_migration(message: str, autogenerate: bool = True) -> None:
    """Create a new migration"""
    print(f"📝 Creating migration: {message}")
    
    args = ["revision", "--message", message]
    if autogenerate:
        args.append("--autogenerate")
    
    await run_alembic_command(args)
    print("✅ Migration created successfully")

async def show_history(verbose: bool = False) -> None:
    """Show migration history"""
    print("📜 Migration History:")
    args = ["history"]
    if verbose:
        args.append("--verbose")
    await run_alembic_command(args)

async def show_status() -> None:
    """Show current migration status"""
    print("📊 Migration Status:")
    await run_alembic_command(["current"])
    await run_alembic_command(["heads"])

async def stamp(revision: str) -> None:
    """Stamp the database with a revision without running migrations"""
    print(f"🏷️  Stamping database with revision: {revision}")
    await run_alembic_command(["stamp", revision])
    print("✅ Database stamped successfully")

async def show_branches() -> None:
    """Show migration branches"""
    print("🌿 Migration Branches:")
    await run_alembic_command(["branches"])

async def edit(revision: str) -> None:
    """Edit a revision file"""
    print(f"✏️  Editing revision: {revision}")
    await run_alembic_command(["edit", revision])

async def merge(revisions: list, message: Optional[str] = None) -> None:
    """Merge multiple revisions"""
    print(f"🔄 Merging revisions: {', '.join(revisions)}")
    args = ["merge"]
    if message:
        args.extend(["-m", message])
    args.extend(revisions)
    await run_alembic_command(args)
    print("✅ Revisions merged successfully")

async def check() -> None:
    """Check if there are any new migrations to generate"""
    print("🔍 Checking for new migrations...")
    await run_alembic_command(["check"])

async def reset_db(confirm: bool = False) -> None:
    """Reset database (drop all tables and recreate)"""
    if not confirm:
        print("⚠️  WARNING: This will drop ALL tables and data!")
        print("   Use --confirm flag to proceed")
        return
    
    print("🔄 Resetting database...")
    
    # Import database components
    from app.db.session import engine
    from app.models import Base
    from app.config import settings
    
    # Drop all tables
    async with engine.begin() as conn:
        print("🗑️  Dropping all tables...")
        await conn.run_sync(Base.metadata.drop_all)
    
    # Create all tables
    async with engine.begin() as conn:
        print("🏗️  Creating tables...")
        await conn.run_sync(Base.metadata.create_all)
    
    # Stamp with head revision
    await stamp("head")
    
    print("✅ Database reset completed")

async def run_migrations_offline() -> None:
    """Generate SQL script for offline migration"""
    print("💾 Generating offline migration script...")
    await run_alembic_command(["upgrade", "--sql", "head"])
    print("✅ Offline migration script generated")

async def show_config() -> None:
    """Show Alembic configuration"""
    print("⚙️  Alembic Configuration:")
    from alembic.config import Config
    from pathlib import Path
    
    alembic_ini = Path(__file__).parent.parent / "alembic.ini"
    config = Config(str(alembic_ini))
    
    print(f"Config file: {alembic_ini}")
    print(f"Script location: {config.get_main_option('script_location')}")
    print(f"Database URL: {config.get_main_option('sqlalchemy.url')}")

def main() -> None:
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Database Migration Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s upgrade                 # Run all migrations
  %(prog)s downgrade -1            # Downgrade one revision
  %(prog)s create "Add new field"  # Create new migration
  %(prog)s history --verbose       # Show detailed history
  %(prog)s status                  # Check migration status
  %(prog)s reset --confirm         # Reset database (DANGEROUS!)
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Upgrade command
    upgrade_parser = subparsers.add_parser("upgrade", help="Upgrade database")
    upgrade_parser.add_argument(
        "revision", 
        nargs="?", 
        default="head",
        help="Revision to upgrade to (default: head)"
    )
    
    # Downgrade command
    downgrade_parser = subparsers.add_parser("downgrade", help="Downgrade database")
    downgrade_parser.add_argument(
        "revision",
        help="Revision to downgrade to (e.g., -1, base, or specific revision)"
    )
    
    # Create command
    create_parser = subparsers.add_parser("create", help="Create new migration")
    create_parser.add_argument(
        "message",
        help="Migration description"
    )
    create_parser.add_argument(
        "--no-autogenerate",
        action="store_true",
        help="Create empty migration without autogenerate"
    )
    
    # History command
    history_parser = subparsers.add_parser("history", help="Show migration history")
    history_parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show verbose output"
    )
    
    # Status command
    subparsers.add_parser("status", help="Show migration status")
    
    # Stamp command
    stamp_parser = subparsers.add_parser("stamp", help="Stamp database with revision")
    stamp_parser.add_argument(
        "revision",
        help="Revision to stamp"
    )
    
    # Branches command
    subparsers.add_parser("branches", help="Show migration branches")
    
    # Edit command
    edit_parser = subparsers.add_parser("edit", help="Edit revision file")
    edit_parser.add_argument(
        "revision",
        help="Revision to edit"
    )
    
    # Merge command
    merge_parser = subparsers.add_parser("merge", help="Merge revisions")
    merge_parser.add_argument(
        "revisions",
        nargs="+",
        help="Revisions to merge"
    )
    merge_parser.add_argument(
        "--message", "-m",
        help="Merge message"
    )
    
    # Check command
    subparsers.add_parser("check", help="Check for new migrations")
    
    # Reset command
    reset_parser = subparsers.add_parser("reset", help="Reset database (DANGEROUS!)")
    reset_parser.add_argument(
        "--confirm",
        action="store_true",
        help="Confirm database reset"
    )
    
    # Offline command
    subparsers.add_parser("offline", help="Generate offline migration script")
    
    # Config command
    subparsers.add_parser("config", help="Show configuration")
    
    # Version command
    subparsers.add_parser("version", help="Show version information")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    try:
        if args.command == "upgrade":
            asyncio.run(upgrade(args.revision))
            
        elif args.command == "downgrade":
            asyncio.run(downgrade(args.revision))
            
        elif args.command == "create":
            asyncio.run(create_migration(args.message, not args.no_autogenerate))
            
        elif args.command == "history":
            asyncio.run(show_history(args.verbose))
            
        elif args.command == "status":
            asyncio.run(show_status())
            
        elif args.command == "stamp":
            asyncio.run(stamp(args.revision))
            
        elif args.command == "branches":
            asyncio.run(show_branches())
            
        elif args.command == "edit":
            asyncio.run(edit(args.revision))
            
        elif args.command == "merge":
            asyncio.run(merge(args.revisions, args.message))
            
        elif args.command == "check":
            asyncio.run(check())
            
        elif args.command == "reset":
            asyncio.run(reset_db(args.confirm))
            
        elif args.command == "offline":
            asyncio.run(run_migrations_offline())
            
        elif args.command == "config":
            asyncio.run(show_config())
            
        elif args.command == "version":
            from scripts import __version__
            print(f"Migration Scripts v{__version__}")
            
    except KeyboardInterrupt:
        print("\n⚠️  Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()