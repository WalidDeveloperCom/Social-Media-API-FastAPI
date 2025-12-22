"""
File upload utility functions
"""
import os
import uuid
import shutil
from pathlib import Path
from typing import Optional
from fastapi import UploadFile
import aiofiles
from app.config import settings

logger = logging.getLogger(__name__)


async def save_upload_file(upload_file: UploadFile, subdirectory: str = "") -> str:
    """
    Save uploaded file to disk
    
    Returns:
        URL path to the saved file
    """
    try:
        # Generate unique filename
        file_extension = Path(upload_file.filename).suffix if upload_file.filename else ""
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        
        # Create directory if it doesn't exist
        upload_dir = Path(settings.UPLOAD_DIR) / subdirectory
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        # Save file
        file_path = upload_dir / unique_filename
        
        async with aiofiles.open(file_path, 'wb') as out_file:
            content = await upload_file.read()
            await out_file.write(content)
        
        # Return relative path for URL
        return f"/uploads/{subdirectory}/{unique_filename}" if subdirectory else f"/uploads/{unique_filename}"
    
    except Exception as e:
        logger.error(f"Error saving uploaded file: {e}")
        raise


async def delete_file(file_path: str) -> bool:
    """Delete file from disk"""
    try:
        # Remove leading slash if present
        if file_path.startswith('/'):
            file_path = file_path[1:]
        
        full_path = Path(file_path)
        if full_path.exists():
            full_path.unlink()
            return True
        return False
    except Exception as e:
        logger.error(f"Error deleting file {file_path}: {e}")
        return False


def generate_profile_picture_url(
    username: str, 
    email: str, 
    size: int = 150
) -> str:
    """
    Generate profile picture URL
    
    Options:
    1. Use Gravatar based on email
    2. Generate from username initials
    3. Use default avatar
    """
    # Option 1: Gravatar
    import hashlib
    
    # Create MD5 hash of email for Gravatar
    email_hash = hashlib.md5(email.lower().encode()).hexdigest()
    gravatar_url = f"https://www.gravatar.com/avatar/{email_hash}?s={size}&d=identicon"
    
    return gravatar_url


def is_allowed_file(filename: str) -> bool:
    """Check if file extension is allowed"""
    if not filename:
        return False
    
    file_extension = Path(filename).suffix.lower()
    return file_extension in settings.ALLOWED_EXTENSIONS


def get_file_size(file_path: str) -> int:
    """Get file size in bytes"""
    try:
        return os.path.getsize(file_path)
    except:
        return 0


async def cleanup_old_files(directory: str, days_old: int = 30):
    """Clean up old files in directory"""
    import time
    from datetime import datetime, timedelta
    
    try:
        dir_path = Path(directory)
        if not dir_path.exists():
            return
        
        cutoff_time = datetime.now() - timedelta(days=days_old)
        
        for file_path in dir_path.rglob("*"):
            if file_path.is_file():
                file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                if file_mtime < cutoff_time:
                    file_path.unlink()
                    logger.info(f"Deleted old file: {file_path}")
    
    except Exception as e:
        logger.error(f"Error cleaning up old files: {e}")