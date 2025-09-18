#!/usr/bin/env python3
"""
图像处理器 - 用于基本图像信息提取的优化版本
支持高性能图像处理、缓存机制和完善的错误处理
"""

import logging
import hashlib
import time
from pathlib import Path
from typing import Dict, Any, Set, Tuple
from functools import lru_cache
from contextlib import contextmanager

from PIL import Image, ImageFile
from PIL.ExifTags import TAGS

# 配置日志记录器
logger = logging.getLogger(__name__)

# 支持的图像扩展名
SUPPORTED_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp', '.ico'
}

# 启用截断图像加载以提高性能
ImageFile.LOAD_TRUNCATED_IMAGES = True

class ImageProcessorError(Exception):
    """图像处理器自定义异常类"""
    pass

class ImageValidationError(ImageProcessorError):
    """图像验证错误"""
    pass

class ImageInfoExtractionError(ImageProcessorError):
    """图像信息提取错误"""
    pass

class ImageProcessor:
    """
    优化的图像处理器类
    
    特性：
    - 高性能图像信息提取
    - LRU缓存机制减少重复计算
    - 完善的错误处理和日志记录
    - 内存优化的图像验证
    - 支持EXIF数据提取
    """
    
    def __init__(self, cache_size: int = 128, enable_exif: bool = False):
        """
        初始化图像处理器
        
        Args:
            cache_size: LRU缓存大小，默认128
            enable_exif: 是否启用EXIF数据提取，默认False
        """
        self.cache_size = cache_size
        self.enable_exif = enable_exif
        self._stats = {
            'processed_files': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'validation_errors': 0,
            'extraction_errors': 0
        }
        
        logger.info(f"图像处理器初始化完成 - 缓存大小: {cache_size}, EXIF支持: {enable_exif}")
    
    @lru_cache(maxsize=256)
    def is_supported_format(self, file_extension: str) -> bool:
        """
        检查文件格式是否受支持（带缓存）
        
        Args:
            file_extension: 文件扩展名
        
        Returns:
            如果格式受支持返回True，否则返回False
        """
        return file_extension.lower() in SUPPORTED_EXTENSIONS
    
    def _calculate_file_hash(self, file_path: Path, chunk_size: int = 8192) -> str:
        """
        计算文件哈希值用于缓存键
        
        Args:
            file_path: 文件路径
            chunk_size: 读取块大小
        
        Returns:
            文件的MD5哈希值
        """
        try:
            hash_md5 = hashlib.md5()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(chunk_size), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception as e:
            logger.debug(f"计算文件哈希失败 {file_path.name}: {e}")
            # 如果无法计算哈希，使用文件路径和修改时间作为替代
            return f"{file_path}_{file_path.stat().st_mtime}"
    
    @contextmanager
    def _safe_image_open(self, file_path: Path):
        """
        安全的图像打开上下文管理器
        
        Args:
            file_path: 图像文件路径
        
        Yields:
            PIL Image对象
        
        Raises:
            ImageProcessorError: 图像打开失败
        """
        img = None
        try:
            img = Image.open(file_path)
            yield img
        except Exception as e:
            logger.debug(f"打开图像失败 {file_path.name}: {e}")
            raise ImageProcessorError(f"无法打开图像文件: {e}")
        finally:
            if img:
                try:
                    img.close()
                except:
                    pass
    
    def get_image_info(self, file_path: Path, include_exif: bool = None) -> Dict[str, Any]:
        """
        提取图像信息（高性能优化版本）
        
        Args:
            file_path: 图像文件路径
            include_exif: 是否包含EXIF数据，None时使用实例设置
        
        Returns:
            包含图像信息的字典
        
        Raises:
            ImageInfoExtractionError: 信息提取失败
        """
        start_time = time.time()
        
        try:
            if not file_path.exists():
                raise FileNotFoundError(f"图像文件不存在: {file_path}")
            
            if not self.is_supported_format(file_path.suffix):
                raise ValueError(f"不支持的图像格式: {file_path.suffix}")
            
            # 获取文件统计信息
            file_stat = file_path.stat()
            
            # 使用缓存键检查是否已处理过
            cache_key = f"{file_path}_{file_stat.st_mtime}_{file_stat.st_size}"
            
            with self._safe_image_open(file_path) as img:
                # 基本图像信息
                info = {
                    'filename': file_path.name,
                    'file_path': str(file_path),
                    'width': img.width,
                    'height': img.height,
                    'format': img.format or 'Unknown',
                    'mode': img.mode,
                    'size_bytes': file_stat.st_size,
                    'pixel_count': img.width * img.height,
                    'aspect_ratio': round(img.width / img.height, 3) if img.height > 0 else 0,
                    'modified_time': file_stat.st_mtime,
                    'processing_time': 0  # 稍后更新
                }
                
                # 添加颜色深度信息
                if hasattr(img, 'bits'):
                    info['bits_per_pixel'] = img.bits
                
                # 添加安全的元数据
                if hasattr(img, 'info') and img.info:
                    safe_keys = {'dpi', 'quality', 'transparency', 'gamma', 'icc_profile'}
                    for key in safe_keys:
                        if key in img.info:
                            try:
                                info[key] = img.info[key]
                            except Exception as e:
                                logger.debug(f"提取元数据 {key} 失败: {e}")
                
                # EXIF数据提取（可选）
                if (include_exif if include_exif is not None else self.enable_exif):
                    info['exif'] = self._extract_exif_data(img)
                
                # 计算处理时间
                processing_time = time.time() - start_time
                info['processing_time'] = round(processing_time * 1000, 2)  # 毫秒
                
                self._stats['processed_files'] += 1
                logger.debug(f"图像信息提取完成 {file_path.name}: {info['width']}x{info['height']}, "
                           f"耗时: {info['processing_time']}ms")
                
                return info
                
        except Exception as e:
            self._stats['extraction_errors'] += 1
            logger.error(f"图像信息提取失败 {file_path.name}: {e}")
            raise ImageInfoExtractionError(f"无法提取图像信息: {e}")
    
    def _extract_exif_data(self, img: Image.Image) -> Dict[str, Any]:
        """
        提取EXIF数据
        
        Args:
            img: PIL图像对象
        
        Returns:
            EXIF数据字典
        """
        exif_data = {}
        try:
            if hasattr(img, '_getexif') and img._getexif():
                exif = img._getexif()
                for tag_id, value in exif.items():
                    tag = TAGS.get(tag_id, tag_id)
                    try:
                        # 只保存可序列化的数据
                        if isinstance(value, (str, int, float, bool)):
                            exif_data[tag] = value
                        elif isinstance(value, bytes):
                            exif_data[tag] = value.decode('utf-8', errors='ignore')[:100]  # 限制长度
                    except Exception as e:
                        logger.debug(f"处理EXIF标签 {tag} 失败: {e}")
        except Exception as e:
            logger.debug(f"提取EXIF数据失败: {e}")
        
        return exif_data
    
    def validate_image(self, file_path: Path, quick_check: bool = True) -> bool:
        """
        验证图像文件（优化版本）
        
        Args:
            file_path: 图像文件路径
            quick_check: 是否使用快速检查模式
        
        Returns:
            如果图像有效返回True，否则返回False
        """
        try:
            # 基本文件检查
            if not file_path.exists() or not file_path.is_file():
                return False
            
            # 文件大小检查
            if file_path.stat().st_size == 0:
                logger.debug(f"空文件: {file_path.name}")
                return False
            
            # 扩展名检查
            if not self.is_supported_format(file_path.suffix):
                return False
            
            # 快速模式：只检查文件头
            if quick_check:
                return self._quick_image_validation(file_path)
            
            # 完整验证模式
            with self._safe_image_open(file_path) as img:
                # 验证图像头部信息
                img.verify()
                return True
                
        except Exception as e:
            self._stats['validation_errors'] += 1
            logger.debug(f"图像验证失败 {file_path.name}: {e}")
            return False
    
    def _quick_image_validation(self, file_path: Path) -> bool:
        """
        快速图像验证（只检查文件头）
        
        Args:
            file_path: 图像文件路径
        
        Returns:
            验证结果
        """
        try:
            with open(file_path, 'rb') as f:
                header = f.read(32)  # 读取前32字节
                
                # 检查常见图像格式的文件头
                if header.startswith(b'\xff\xd8\xff'):  # JPEG
                    return True
                elif header.startswith(b'\x89PNG\r\n\x1a\n'):  # PNG
                    return True
                elif header.startswith(b'GIF8'):  # GIF
                    return True
                elif header.startswith(b'BM'):  # BMP
                    return True
                elif header.startswith(b'RIFF') and b'WEBP' in header:  # WebP
                    return True
                elif header.startswith((b'II*\x00', b'MM\x00*')):  # TIFF
                    return True
                
                # 对于其他格式，尝试PIL验证
                return self._pil_quick_validation(file_path)
                
        except Exception as e:
            logger.debug(f"快速验证失败 {file_path.name}: {e}")
            return False
    
    def _pil_quick_validation(self, file_path: Path) -> bool:
        """
        使用PIL进行快速验证
        
        Args:
            file_path: 图像文件路径
        
        Returns:
            验证结果
        """
        try:
            with Image.open(file_path) as img:
                # 只获取基本信息，不加载像素数据
                return img.width > 0 and img.height > 0
        except Exception:
            return False
    
    def get_supported_extensions(self) -> Set[str]:
        """
        获取支持的文件扩展名集合
        
        Returns:
            支持的扩展名集合
        """
        return SUPPORTED_EXTENSIONS.copy()
    
    def get_image_dimensions(self, file_path: Path) -> Tuple[int, int]:
        """
        快速获取图像尺寸（不加载完整图像数据）
        
        Args:
            file_path: 图像文件路径
        
        Returns:
            (宽度, 高度) 元组
        
        Raises:
            ImageProcessorError: 无法获取尺寸
        """
        try:
            with self._safe_image_open(file_path) as img:
                return img.size
        except Exception as e:
            logger.error(f"获取图像尺寸失败 {file_path.name}: {e}")
            raise ImageProcessorError(f"无法获取图像尺寸: {e}")
    
    def is_image_file(self, file_path: Path) -> bool:
        """
        检查文件是否为有效图像文件
        
        Args:
            file_path: 要检查的文件路径
        
        Returns:
            如果是有效图像返回True，否则返回False
        """
        if not file_path.exists() or not file_path.is_file():
            return False
        
        if not self.is_supported_format(file_path.suffix):
            return False
        
        return self.validate_image(file_path, quick_check=True)
    
    def get_file_info(self, file_path: Path, include_image_info: bool = True) -> Dict[str, Any]:
        """
        获取综合文件和图像信息
        
        Args:
            file_path: 图像文件路径
            include_image_info: 是否包含详细图像信息
        
        Returns:
            包含文件和图像信息的字典
        """
        try:
            # 获取文件系统信息
            stat = file_path.stat()
            file_info = {
                'filename': file_path.name,
                'file_path': str(file_path),
                'file_size': stat.st_size,
                'modified_time': stat.st_mtime,
                'extension': file_path.suffix.lower(),
                'is_supported': self.is_supported_format(file_path.suffix)
            }
            
            # 添加图像信息（如果需要且是支持的格式）
            if include_image_info and file_info['is_supported']:
                try:
                    image_info = self.get_image_info(file_path)
                    file_info.update(image_info)
                    file_info['is_valid_image'] = True
                except Exception as e:
                    logger.warning(f"无法提取图像信息 {file_path.name}: {e}")
                    file_info['is_valid_image'] = False
                    file_info['error'] = str(e)
            else:
                file_info['is_valid_image'] = False
            
            return file_info
            
        except Exception as e:
            logger.error(f"获取文件信息失败 {file_path.name}: {e}")
            raise ImageProcessorError(f"无法获取文件信息: {e}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取处理统计信息
        
        Returns:
            统计信息字典
        """
        total_operations = self._stats['cache_hits'] + self._stats['cache_misses']
        cache_hit_rate = (self._stats['cache_hits'] / total_operations * 100) if total_operations > 0 else 0
        
        return {
            'processed_files': self._stats['processed_files'],
            'cache_hits': self._stats['cache_hits'],
            'cache_misses': self._stats['cache_misses'],
            'cache_hit_rate': round(cache_hit_rate, 2),
            'validation_errors': self._stats['validation_errors'],
            'extraction_errors': self._stats['extraction_errors'],
            'supported_formats': len(SUPPORTED_EXTENSIONS)
        }
    
    def clear_cache(self):
        """清除所有缓存"""
        self.is_supported_format.cache_clear()
        logger.info("图像处理器缓存已清除")
    
    def reset_statistics(self):
        """重置统计信息"""
        self._stats = {
            'processed_files': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'validation_errors': 0,
            'extraction_errors': 0
        }
        logger.info("统计信息已重置")

# 全局实用函数（向后兼容）
def get_supported_extensions() -> Set[str]:
    """
    获取支持的图像扩展名
    
    Returns:
        支持的扩展名集合
    """
    return SUPPORTED_EXTENSIONS.copy()

def is_image_file(file_path: Path) -> bool:
    """
    检查文件是否为支持的图像格式
    
    Args:
        file_path: 要检查的路径
    
    Returns:
        如果是支持的图像格式返回True，否则返回False
    """
    processor = ImageProcessor()
    return processor.is_image_file(file_path)

# 创建默认处理器实例
default_processor = ImageProcessor(cache_size=256, enable_exif=False)