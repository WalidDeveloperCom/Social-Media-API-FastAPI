#!/usr/bin/env python3
"""
Database initialization script
"""
import asyncio
import sys
from pathlib import Path

# Add the app directory to the Python path
current_dir = Path(__file__).parent
root_dir = current_dir.parent
sys.path.insert(0, str(root_dir))

async def init_database() -> None:
    """Initialize database with tables"""
    from app.db.session import init_db
    from app.config import settings
    
    print(f"🚀 Initializing database: {settings.database_url}")
    
    try:
        await init_db()
        print("✅ Database initialized successfully")
        
        # Create initial admin user if needed
        await create_initial_data()
        
    except Exception as e:
        print(f"❌ Error initializing database: {e}")
        sys.exit(1)

async def create_initial_data() -> None:
    """Create initial data for development"""
    from app.db.session import get_db
    from app.models.user import User
    from app.services.auth_service import AuthService
    from sqlalchemy import select
    
    print("👤 Creating initial data...")
    
    async for db in get_db():
        try:
            # Check if admin user already exists
            stmt = select(User).where(User.username == "admin")
            result = await db.execute(stmt)
            admin = result.scalar_one_or_none()
            
            if not admin:
                # Create admin user
                auth_service = AuthService(db)
                admin_data = {
                    "username": "admin",
                    "email": "admin@example.com",
                    "password": "Admin123!",
                    "full_name": "Administrator",
                    "bio": "System Administrator",
                    "is_verified": True
                }
                
                admin = await auth_service.create_user(**admin_data)
                print(f"✅ Created admin user: {admin.username}")
            
            # Create test users for development
            test_users = [
                {
                    "username": "john_doe",
                    "email": "john@example.com",
                    "password": "Password123!",
                    "full_name": "John Doe",
                    "bio": "Software Developer"
                },
                {
                    "username": "jane_smith",
                    "email": "jane@example.com",
                    "password": "Password123!",
                    "full_name": "Jane Smith",
                    "bio": "Product Manager"
                },
                {
                    "username": "bob_wilson",
                    "email": "bob@example.com",
                    "password": "Password123!",
                    "full_name": "Bob Wilson",
                    "bio": "DevOps Engineer"
                }
            ]
            
            created_count = 0
            for user_data in test_users:
                stmt = select(User).where(User.username == user_data["username"])
                result = await db.execute(stmt)
                existing = result.scalar_one_or_none()
                
                if not existing:
                    auth_service = AuthService(db)
                    await auth_service.create_user(**user_data)
                    created_count += 1
            
            if created_count > 0:
                print(f"✅ Created {created_count} test users")
            
            await db.commit()
            
        except Exception as e:
            await db.rollback()
            print(f"⚠️  Error creating initial data: {e}")

async def check_database_connection() -> bool:
    """Check if database is accessible"""
    from app.db.session import engine
    from sqlalchemy import text
    
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        print("✅ Database connection successful")
        return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False

async def drop_database(confirm: bool = False) -> None:
    """Drop all database tables"""
    if not confirm:
        print("⚠️  WARNING: This will drop ALL tables and data!")
        print("   Use --confirm flag to proceed")
        return
    
    from app.db.session import engine
    from app.models import Base
    
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        print("✅ Database dropped successfully")
    except Exception as e:
        print(f"❌ Error dropping database: {e}")

def main() -> None:
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Database Initialization")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Init command
    subparsers.add_parser("init", help="Initialize database")
    
    # Check command
    subparsers.add_parser("check", help="Check database connection")
    
    # Drop command
    drop_parser = subparsers.add_parser("drop", help="Drop database (DANGEROUS!)")
    drop_parser.add_argument("--confirm", action="store_true", help="Confirm drop")
    
    # Seed command
    subparsers.add_parser("seed", help="Seed initial data")
    
    # Reset command
    reset_parser = subparsers.add_parser("reset", help="Drop and reinitialize")
    reset_parser.add_argument("--confirm", action="store_true", help="Confirm reset")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    try:
        if args.command == "init":
            asyncio.run(init_database())
            
        elif args.command == "check":
            success = asyncio.run(check_database_connection())
            sys.exit(0 if success else 1)
            
        elif args.command == "drop":
            asyncio.run(drop_database(args.confirm))
            
        elif args.command == "seed":
            asyncio.run(create_initial_data())
            
        elif args.command == "reset":
            if not args.confirm:
                print("⚠️  WARNING: This will drop ALL tables and data!")
                print("   Use --confirm flag to proceed")
                return
            
            asyncio.run(drop_database(True))
            asyncio.run(init_database())
            
    except KeyboardInterrupt:
        print("\n⚠️  Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()