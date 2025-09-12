#!/usr/bin/env python3
"""
Image Processor for basic image information extraction.
Simplified version that only extracts basic image metadata without conversion.
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional, Set

from PIL import Image

# Configure logging
logger = logging.getLogger(__name__)

# Supported image extensions
SUPPORTED_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp'
}

class ImageProcessor:
    """Simplified image processor for basic information extraction."""
    
    def __init__(self):
        """Initialize the image processor."""
        logger.info("ImageProcessor initialized")
    
    def is_supported_format(self, file_path: Path) -> bool:
        """Check if the file format is supported.
        
        Args:
            file_path: Path to the image file
        
        Returns:
            True if format is supported, False otherwise
        """
        return file_path.suffix.lower() in SUPPORTED_EXTENSIONS
    
    def get_image_info(self, file_path: Path) -> Dict[str, Any]:
        """Extract basic image information.
        
        Args:
            file_path: Path to the image file
        
        Returns:
            Dictionary containing image information
        
        Raises:
            Exception: If image cannot be processed
        """
        try:
            if not file_path.exists():
                raise FileNotFoundError(f"Image file not found: {file_path}")
            
            if not self.is_supported_format(file_path):
                raise ValueError(f"Unsupported image format: {file_path.suffix}")
            
            # Open and analyze image
            with Image.open(file_path) as img:
                # Get basic image information
                info = {
                    'width': img.width,
                    'height': img.height,
                    'format': img.format,
                    'mode': img.mode,
                    'size_bytes': file_path.stat().st_size,
                    'filename': file_path.name
                }
                
                # Add additional metadata if available
                if hasattr(img, 'info') and img.info:
                    # Only include safe metadata
                    safe_keys = {'dpi', 'quality', 'transparency'}
                    for key in safe_keys:
                        if key in img.info:
                            info[key] = img.info[key]
                
                logger.debug(f"Extracted info for {file_path.name}: {info}")
                return info
                
        except Exception as e:
            logger.error(f"Failed to get image info for {file_path.name}: {e}")
            raise
    
    def validate_image(self, file_path: Path) -> bool:
        """Validate if the file is a valid image.
        
        Args:
            file_path: Path to the image file
        
        Returns:
            True if image is valid, False otherwise
        """
        try:
            with Image.open(file_path) as img:
                # Try to load the image data to verify it's valid
                img.verify()
                return True
        except Exception as e:
            logger.warning(f"Image validation failed for {file_path.name}: {e}")
            return False
    
    def get_supported_extensions(self) -> Set[str]:
        """Get set of supported file extensions.
        
        Returns:
            Set of supported extensions
        """
        return SUPPORTED_EXTENSIONS.copy()
    
    def get_image_dimensions(self, file_path: Path) -> tuple[int, int]:
        """Get image dimensions quickly without loading full image data.
        
        Args:
            file_path: Path to the image file
        
        Returns:
            Tuple of (width, height)
        
        Raises:
            Exception: If image cannot be processed
        """
        try:
            with Image.open(file_path) as img:
                return img.size
        except Exception as e:
            logger.error(f"Failed to get dimensions for {file_path.name}: {e}")
            raise
    
    def is_image_file(self, file_path: Path) -> bool:
        """Check if a file is a valid image file.
        
        Args:
            file_path: Path to check
        
        Returns:
            True if file is a valid image, False otherwise
        """
        if not file_path.exists() or not file_path.is_file():
            return False
        
        if not self.is_supported_format(file_path):
            return False
        
        return self.validate_image(file_path)
    
    def get_file_info(self, file_path: Path) -> Dict[str, Any]:
        """Get comprehensive file and image information.
        
        Args:
            file_path: Path to the image file
        
        Returns:
            Dictionary with file and image information
        """
        try:
            # Get file system information
            stat = file_path.stat()
            file_info = {
                'filename': file_path.name,
                'file_size': stat.st_size,
                'modified_time': stat.st_mtime,
                'extension': file_path.suffix.lower(),
                'is_supported': self.is_supported_format(file_path)
            }
            
            # Add image information if it's a valid image
            if file_info['is_supported']:
                try:
                    image_info = self.get_image_info(file_path)
                    file_info.update(image_info)
                    file_info['is_valid_image'] = True
                except Exception as e:
                    logger.warning(f"Could not extract image info for {file_path.name}: {e}")
                    file_info['is_valid_image'] = False
            else:
                file_info['is_valid_image'] = False
            
            return file_info
            
        except Exception as e:
            logger.error(f"Failed to get file info for {file_path.name}: {e}")
            raise

# Utility functions for backward compatibility
def get_supported_extensions() -> Set[str]:
    """Get supported image extensions.
    
    Returns:
        Set of supported extensions
    """
    return SUPPORTED_EXTENSIONS.copy()

def is_image_file(file_path: Path) -> bool:
    """Check if file is a supported image format.
    
    Args:
        file_path: Path to check
    
    Returns:
        True if supported image format, False otherwise
    """
    processor = ImageProcessor()
    return processor.is_image_file(file_path)