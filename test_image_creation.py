#!/usr/bin/env python3
"""
Create test images for verifying the image conversion functionality.
"""

from PIL import Image
from pathlib import Path
import os

def create_test_images():
    """Create test images in different formats."""
    test_dir = Path("test_input")
    test_dir.mkdir(exist_ok=True)
    
    # Create test images
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]  # Red, Green, Blue
    formats = [('PNG', 'png'), ('BMP', 'bmp'), ('WEBP', 'webp')]
    
    created_files = []
    
    for i, (color, (format_name, ext)) in enumerate(zip(colors, formats)):
        # Create a simple colored image
        img = Image.new('RGB', (200, 200), color)
        
        # Add some text to make it more interesting
        filename = test_dir / f"test_image_{i+1}.{ext}"
        
        if format_name == 'WEBP':
            img.save(filename, format_name, quality=85)
        else:
            img.save(filename, format_name)
        
        created_files.append(filename)
        print(f"Created: {filename} ({filename.stat().st_size} bytes)")
    
    return created_files

if __name__ == "__main__":
    print("Creating test images...")
    files = create_test_images()
    print(f"\nCreated {len(files)} test images in 'test_input' directory.")
    print("\nTo test the converter:")
    print("python main.py --watch-path ./test_input --output-dir D:\\converted_images")