"""
Migration utilities for the application
"""
import asyncio
from pathlib import Path
from typing import Optional
from alembic.config import Config
from alembic import command
import logging

logger = logging.getLogger(__name__)

def get_alembic_config(db_url: Optional[str] = None) -> Config:
    """Get Alembic configuration"""
    alembic_ini_path = Path(__file__).parent.parent.parent / "alembic.ini"
    
    config = Config(str(alembic_ini_path))
    
    if db_url:
        config.set_main_option("sqlalchemy.url", db_url)
    
    return config

async def run_migrations(db_url: Optional[str] = None) -> None:
    """Run database migrations"""
    config = get_alembic_config(db_url)
    
    # Run migrations
    command.upgrade(config, "head")
    logger.info("Database migrations completed successfully")

async def create_migration(message: str, autogenerate: bool = True) -> None:
    """Create a new migration"""
    config = get_alembic_config()
    
    if autogenerate:
        command.revision(config, message=message, autogenerate=True)
    else:
        command.revision(config, message=message)
    
    logger.info(f"Created migration: {message}")

async def downgrade_migration(revision: str) -> None:
    """Downgrade to a specific revision"""
    config = get_alembic_config()
    command.downgrade(config, revision)
    logger.info(f"Downgraded to revision: {revision}")

async def show_migrations() -> None:
    """Show migration history"""
    config = get_alembic_config()
    command.history(config)

async def check_migration_status() -> bool:
    """Check if database is up to date"""
    config = get_alembic_config()
    
    # Get current revision
    from alembic.script import ScriptDirectory
    script = ScriptDirectory.from_config(config)
    
    # Get current revision from database
    from alembic.runtime.environment import EnvironmentContext
    from sqlalchemy import create_engine
    
    def get_current_rev(connection, **kwargs):
        context = EnvironmentContext(config, script)
        return context.get_current_revision()
    
    engine = create_engine(config.get_main_option("sqlalchemy.url"))
    
    with engine.connect() as connection:
        current_rev = get_current_rev(connection)
    
    head_rev = script.get_current_head()
    
    return current_rev == head_rev