#!/usr/bin/env python3
"""
Database backup and restore utility
"""
import asyncio
import sys
import shutil
from pathlib import Path
from datetime import datetime
import gzip
import json

# Add the app directory to the Python path
current_dir = Path(__file__).parent
root_dir = current_dir.parent
sys.path.insert(0, str(root_dir))

async def backup_database(output_dir: Path = None, compress: bool = True) -> Path:
    """Backup database"""
    from app.config import settings
    import subprocess
    
    if output_dir is None:
        output_dir = Path("backups")
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"social_db_backup_{timestamp}"
    
    if "sqlite" in settings.database_url:
        # SQLite backup
        db_path = settings.database_url.split("///")[-1]
        if ":" in db_path:  # Remove Windows drive letter if present
            db_path = db_path.split(":")[-1]
        
        db_file = Path(db_path)
        if not db_file.exists():
            print(f"❌ Database file not found: {db_file}")
            sys.exit(1)
        
        backup_file = output_dir / f"{backup_name}.db"
        shutil.copy2(db_file, backup_file)
        
        print(f"✅ SQLite database backed up to: {backup_file}")
        
        if compress:
            compressed_file = backup_file.with_suffix(".db.gz")
            with open(backup_file, 'rb') as f_in:
                with gzip.open(compressed_file, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            backup_file.unlink()  # Remove uncompressed file
            backup_file = compressed_file
            print(f"✅ Compressed backup: {backup_file}")
        
        return backup_file
    
    else:
        # PostgreSQL backup using pg_dump
        try:
            # Extract connection info
            import re
            pattern = r"postgresql\+asyncpg://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)"
            match = re.match(pattern, settings.database_url)
            
            if not match:
                print("❌ Could not parse PostgreSQL URL")
                sys.exit(1)
            
            username, password, host, port, database = match.groups()
            
            # Create backup command
            backup_file = output_dir / f"{backup_name}.sql"
            
            # Set PGPASSWORD environment variable
            env = os.environ.copy()
            env['PGPASSWORD'] = password
            
            cmd = [
                "pg_dump",
                "-h", host,
                "-p", port,
                "-U", username,
                "-d", database,
                "-f", str(backup_file),
                "--clean",  # Add DROP statements
                "--if-exists",
                "--no-owner",
                "--no-privileges"
            ]
            
            print(f"🔧 Running: {' '.join(cmd[:5])}...")
            result = subprocess.run(cmd, env=env, capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"❌ Backup failed: {result.stderr}")
                sys.exit(1)
            
            print(f"✅ PostgreSQL database backed up to: {backup_file}")
            
            if compress:
                compressed_file = backup_file.with_suffix(".sql.gz")
                with open(backup_file, 'rb') as f_in:
                    with gzip.open(compressed_file, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                
                backup_file.unlink()  # Remove uncompressed file
                backup_file = compressed_file
                print(f"✅ Compressed backup: {backup_file}")
            
            return backup_file
            
        except FileNotFoundError:
            print("❌ pg_dump not found. Install PostgreSQL client tools.")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Backup failed: {e}")
            sys.exit(1)

async def restore_database(backup_file: Path, confirm: bool = False) -> None:
    """Restore database from backup"""
    if not backup_file.exists():
        print(f"❌ Backup file not found: {backup_file}")
        sys.exit(1)
    
    if not confirm:
        print(f"⚠️  WARNING: This will OVERWRITE the current database!")
        print(f"   Backup file: {backup_file}")
        print("   Use --confirm flag to proceed")
        return
    
    from app.config import settings
    
    print(f"🔧 Restoring from backup: {backup_file}")
    
    if backup_file.suffix == '.gz':
        # Decompress first
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=backup_file.stem) as tmp:
            with gzip.open(backup_file, 'rb') as f_in:
                shutil.copyfileobj(f_in, tmp)
            restore_path = Path(tmp.name)
    else:
        restore_path = backup_file
    
    try:
        if "sqlite" in settings.database_url or restore_path.suffix == '.db':
            # SQLite restore
            db_path = settings.database_url.split("///")[-1]
            if ":" in db_path:  # Remove Windows drive letter if present
                db_path = db_path.split(":")[-1]
            
            db_file = Path(db_path)
            db_file.parent.mkdir(parents=True, exist_ok=True)
            
            shutil.copy2(restore_path, db_file)
            print(f"✅ SQLite database restored from: {backup_file}")
            
        elif restore_path.suffix in ['.sql', '.gz']:
            # PostgreSQL restore using psql
            import subprocess
            import re
            
            # Extract connection info
            pattern = r"postgresql\+asyncpg://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)"
            match = re.match(pattern, settings.database_url)
            
            if not match:
                print("❌ Could not parse PostgreSQL URL")
                sys.exit(1)
            
            username, password, host, port, database = match.groups()
            
            # Set PGPASSWORD environment variable
            env = os.environ.copy()
            env['PGPASSWORD'] = password
            
            cmd = [
                "psql",
                "-h", host,
                "-p", port,
                "-U", username,
                "-d", database,
                "-f", str(restore_path)
            ]
            
            print(f"🔧 Running: {' '.join(cmd[:5])}...")
            result = subprocess.run(cmd, env=env, capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"❌ Restore failed: {result.stderr}")
                sys.exit(1)
            
            print(f"✅ PostgreSQL database restored from: {backup_file}")
            
    except FileNotFoundError:
        print("❌ psql not found. Install PostgreSQL client tools.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Restore failed: {e}")
        sys.exit(1)
    finally:
        if 'tmp' in locals():
            Path(tmp.name).unlink()

async def list_backups(backup_dir: Path = None) -> None:
    """List available backups"""
    if backup_dir is None:
        backup_dir = Path("backups")
    
    if not backup_dir.exists():
        print("❌ Backup directory not found")
        return
    
    backups = []
    for file in backup_dir.glob("social_db_backup_*"):
        if file.suffix in ['.db', '.sql', '.gz']:
            backups.append(file)
    
    if not backups:
        print("📭 No backups found")
        return
    
    print(f"📂 Backups in {backup_dir}:")
    for i, backup in enumerate(sorted(backups, reverse=True), 1):
        size = backup.stat().st_size / (1024 * 1024)  # MB
        print(f"  {i:2d}. {backup.name} ({size:.2f} MB)")

async def backup_metadata(output_dir: Path = None) -> Path:
    """Backup database metadata (schema only)"""
    from app.db.session import engine
    from sqlalchemy import MetaData, create_engine
    import json
    
    if output_dir is None:
        output_dir = Path("backups/metadata")
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    metadata_file = output_dir / f"schema_metadata_{timestamp}.json"
    
    # Create a sync engine for metadata reflection
    sync_url = str(engine.url).replace("+asyncpg", "")
    sync_engine = create_engine(sync_url)
    
    metadata = MetaData()
    metadata.reflect(bind=sync_engine)
    
    schema_info = {
        "timestamp": timestamp,
        "database_url": str(engine.url),
        "tables": {}
    }
    
    for table_name, table in metadata.tables.items():
        schema_info["tables"][table_name] = {
            "columns": [
                {
                    "name": col.name,
                    "type": str(col.type),
                    "nullable": col.nullable,
                    "primary_key": col.primary_key,
                    "foreign_keys": [
                        {
                            "target_table": fk.column.table.name,
                            "target_column": fk.column.name
                        }
                        for fk in col.foreign_keys
                    ]
                }
                for col in table.columns
            ],
            "primary_key": [key.name for key in table.primary_key],
            "indexes": [
                {
                    "name": idx.name,
                    "columns": [col.name for col in idx.columns],
                    "unique": idx.unique
                }
                for idx in table.indexes
            ]
        }
    
    with open(metadata_file, 'w') as f:
        json.dump(schema_info, f, indent=2, default=str)
    
    print(f"✅ Schema metadata backed up to: {metadata_file}")
    return metadata_file

async def schedule_backup(cron_expression: str) -> None:
    """Schedule automatic backups"""
    import platform
    from crontab import CronTab
    
    system = platform.system()
    
    if system == "Windows":
        print("❌ Automatic scheduling not supported on Windows")
        print("   Use Windows Task Scheduler instead")
        return
    
    # Get script path
    script_path = Path(__file__).absolute()
    
    # Create cron job
    cron = CronTab(user=True)
    
    # Remove existing jobs for this script
    cron.remove_all(command=str(script_path))
    
    # Add new job
    job = cron.new(command=f"cd {root_dir} && {sys.executable} {script_path} backup --quiet")
    job.setall(cron_expression)
    
    cron.write()
    
    print(f"✅ Backup scheduled with cron: {cron_expression}")
    print(f"   Next run: {job.schedule().get_next()}")

def main() -> None:
    """Main entry point"""
    import argparse
    import os
    
    parser = argparse.ArgumentParser(description="Database Backup and Restore")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Backup command
    backup_parser = subparsers.add_parser("backup", help="Backup database")
    backup_parser.add_argument("--output", "-o", help="Output directory")
    backup_parser.add_argument("--no-compress", action="store_true", help="Don't compress backup")
    backup_parser.add_argument("--quiet", action="store_true", help="Quiet mode")
    
    # Restore command
    restore_parser = subparsers.add_parser("restore", help="Restore database")
    restore_parser.add_argument("file", help="Backup file to restore from")
    restore_parser.add_argument("--confirm", action="store_true", help="Confirm restore")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List backups")
    list_parser.add_argument("--dir", help="Backup directory")
    
    # Metadata command
    subparsers.add_parser("metadata", help="Backup schema metadata")
    
    # Schedule command
    schedule_parser = subparsers.add_parser("schedule", help="Schedule automatic backups")
    schedule_parser.add_argument("cron", help="Cron expression (e.g., '0 2 * * *' for daily at 2 AM)")
    
    # Auto command
    auto_parser = subparsers.add_parser("auto", help="Automatic backup management")
    auto_parser.add_argument("--keep", type=int, default=7, help="Number of backups to keep")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    try:
        if args.command == "backup":
            output_dir = Path(args.output) if args.output else None
            backup_file = asyncio.run(backup_database(output_dir, not args.no_compress))
            
            if not args.quiet:
                print(f"✅ Backup completed: {backup_file}")
            
        elif args.command == "restore":
            backup_file = Path(args.file)
            asyncio.run(restore_database(backup_file, args.confirm))
            
        elif args.command == "list":
            backup_dir = Path(args.dir) if args.dir else None
            asyncio.run(list_backups(backup_dir))
            
        elif args.command == "metadata":
            output_dir = Path(args.output) if args.output else None
            asyncio.run(backup_metadata(output_dir))
            
        elif args.command == "schedule":
            asyncio.run(schedule_backup(args.cron))
            
        elif args.command == "auto":
            # Automatic backup with rotation
            print("🔄 Running automatic backup...")
            backup_file = asyncio.run(backup_database())
            
            # Clean old backups
            backup_dir = backup_file.parent
            backups = sorted(backup_dir.glob("social_db_backup_*"), reverse=True)
            
            if len(backups) > args.keep:
                for old_backup in backups[args.keep:]:
                    old_backup.unlink()
                    print(f"🗑️  Deleted old backup: {old_backup.name}")
            
            print(f"✅ Automatic backup completed. Keeping {args.keep} backups.")
            
    except KeyboardInterrupt:
        print("\n⚠️  Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()