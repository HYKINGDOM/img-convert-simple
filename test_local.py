#!/usr/bin/env python3
"""
Local test script using SQLite database to verify image conversion functionality.
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path
from PIL import Image
import sqlite3
import hashlib
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def calculate_file_hash(file_path: Path) -> str:
    """Calculate SHA-256 hash of a file."""
    hash_sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_sha256.update(chunk)
    return hash_sha256.hexdigest()

def setup_sqlite_db(db_path: Path):
    """Setup SQLite database for testing."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS image_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            original_path TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            file_hash TEXT NOT NULL UNIQUE,
            image_width INTEGER,
            image_height INTEGER,
            image_format TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMP,
            output_path TEXT,
            is_duplicate BOOLEAN DEFAULT 0
        )
    ''')
    
    conn.commit()
    return conn

def convert_image(input_path: Path, output_path: Path, target_format: str = 'JPEG', quality: int = 85) -> bool:
    """Convert image to target format."""
    try:
        with Image.open(input_path) as img:
            # Convert RGBA to RGB if necessary for JPEG
            if target_format.upper() == 'JPEG' and img.mode in ('RGBA', 'LA', 'P'):
                # Create white background
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            
            # Save with appropriate parameters
            save_kwargs = {'format': target_format, 'optimize': True}
            if target_format.upper() == 'JPEG':
                save_kwargs['quality'] = quality
            
            img.save(output_path, **save_kwargs)
            return True
            
    except Exception as e:
        logger.error(f"Failed to convert {input_path}: {e}")
        return False

def test_conversion():
    """Test the image conversion functionality."""
    logger.info("Starting local image conversion test...")
    
    # Setup paths
    input_dir = Path("test_input")
    output_dir = Path("D:/converted_images")
    output_dir.mkdir(exist_ok=True)
    
    # Setup SQLite database
    db_path = Path("test_images.db")
    conn = setup_sqlite_db(db_path)
    cursor = conn.cursor()
    
    try:
        # Process each image in test_input
        for img_file in input_dir.glob("*"):
            if img_file.is_file() and img_file.suffix.lower() in ['.png', '.jpg', '.jpeg', '.bmp', '.webp']:
                logger.info(f"Processing: {img_file.name}")
                
                # Calculate hash
                file_hash = calculate_file_hash(img_file)
                file_size = img_file.stat().st_size
                
                # Check for duplicates
                cursor.execute("SELECT * FROM image_metadata WHERE file_hash = ?", (file_hash,))
                existing = cursor.fetchone()
                
                if existing:
                    logger.warning(f"Duplicate detected: {img_file.name}")
                    # Delete duplicate
                    img_file.unlink()
                    logger.info(f"Deleted duplicate: {img_file.name}")
                    continue
                
                # Get image info
                try:
                    with Image.open(img_file) as img:
                        width, height = img.size
                        format_name = img.format
                except Exception as e:
                    logger.error(f"Failed to get image info for {img_file.name}: {e}")
                    continue
                
                # Insert into database
                cursor.execute('''
                    INSERT INTO image_metadata 
                    (filename, original_path, file_size, file_hash, image_width, image_height, image_format)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (img_file.name, str(img_file), file_size, file_hash, width, height, format_name))
                
                image_id = cursor.lastrowid
                
                # Convert image
                output_filename = f"{img_file.stem}.jpg"
                output_path = output_dir / output_filename
                
                # Ensure unique filename
                counter = 1
                while output_path.exists():
                    output_filename = f"{img_file.stem}_{counter}.jpg"
                    output_path = output_dir / output_filename
                    counter += 1
                
                # Perform conversion
                success = convert_image(img_file, output_path, 'JPEG', 85)
                
                if success:
                    # Update database
                    cursor.execute('''
                        UPDATE image_metadata 
                        SET processed_at = CURRENT_TIMESTAMP, output_path = ?
                        WHERE id = ?
                    ''', (str(output_path), image_id))
                    
                    # Delete original file
                    img_file.unlink()
                    logger.info(f"Successfully processed: {img_file.name} -> {output_filename}")
                    logger.info(f"Deleted original: {img_file.name}")
                else:
                    logger.error(f"Failed to convert: {img_file.name}")
        
        conn.commit()
        
        # Show results
        logger.info("\n=== Conversion Results ===")
        cursor.execute("SELECT filename, output_path, processed_at FROM image_metadata WHERE processed_at IS NOT NULL")
        results = cursor.fetchall()
        
        for filename, output_path, processed_at in results:
            logger.info(f"✓ {filename} -> {Path(output_path).name} (processed: {processed_at})")
        
        # Check output directory
        logger.info(f"\nOutput directory contents:")
        for file in output_dir.glob("*"):
            if file.is_file():
                logger.info(f"  - {file.name} ({file.stat().st_size} bytes)")
        
        # Check if original files were deleted
        logger.info(f"\nInput directory contents (should be empty):")
        remaining_files = list(input_dir.glob("*"))
        if remaining_files:
            for file in remaining_files:
                logger.info(f"  - {file.name} (NOT DELETED)")
        else:
            logger.info("  (empty - all files processed and deleted)")
            
    except Exception as e:
        logger.error(f"Test failed: {e}")
    finally:
        conn.close()
        
        # Cleanup
        if db_path.exists():
            db_path.unlink()

if __name__ == "__main__":
    test_conversion()