#!/usr/bin/env python3
"""
Main application for Image Duplicate Detector.
Scans folders for image files, detects duplicates by hash, and manages file operations.
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, Any
from threading import Lock
import signal
import shutil

from dotenv import load_dotenv
import coloredlogs

from database import db_manager, initialize_database
from image_processor import ImageProcessor, SUPPORTED_EXTENSIONS
from file_monitor import FileScanner

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

class ImageDuplicateDetector:
    """Main application class for image duplicate detection and file management."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the application with configuration.
        
        Args:
            config: Application configuration dictionary
        """
        self.config = config
        self.is_running = False
        self.processing_lock = Lock()
        
        # Initialize components
        self.image_processor = ImageProcessor()
        self.file_scanner = None
        
        # Statistics
        self.stats = {
            'processed': 0,
            'duplicates': 0,
            'moved': 0,
            'errors': 0,
            'start_time': None
        }
        
        logger.info("ImageDuplicateDetector initialized")
    
    def initialize(self) -> bool:
        """Initialize database and components.
        
        Returns:
            True if initialization successful, False otherwise
        """
        try:
            # Initialize database connection and tables
            if not initialize_database():
                logger.error("Failed to initialize database")
                return False
            
            # Ensure output directory exists
            output_dir = Path(self.config['output_dir'])
            output_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Output directory: {output_dir.resolve()}")
            
            # Initialize file scanner with supported extensions and callback
            scan_interval = self.config.get('scan_interval', 5)
            self.file_scanner = FileScanner(
                supported_extensions=SUPPORTED_EXTENSIONS,
                file_processor_callback=self._process_file,
                scan_interval=scan_interval
            )
            
            # Validate and add scan paths
            for scan_path in self.config['scan_paths']:
                if not self.file_scanner.add_scan_path(scan_path, recursive=True):
                    logger.error(f"Failed to add scan path: {scan_path}")
                    return False
            if not self.file_scanner.scan_paths:
                logger.error("No valid scan paths configured after initialization")
                return False
            
            logger.info("Application initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize application: {e}")
            return False
    
    def _process_file(self, file_path: Path):
        """Process a single file (called by file scanner).
        
        This method runs in the FileScanner's worker thread. Keep it fast and thread-safe.
        Args:
            file_path: Path to the image file
        """
        try:
            # Check if file still exists and is accessible
            if not file_path.exists():
                logger.debug(f"File no longer exists: {file_path.name}")
                return
            
            if not file_path.is_file():
                logger.debug(f"Path is not a file: {file_path.name}")
                return
            
            # Process the image file
            success = self._process_image_file(file_path)
            
            # Update stats under lock to avoid race conditions
            with self.processing_lock:
                if success:
                    self.stats['processed'] += 1
                else:
                    self.stats['errors'] += 1
                processed = self.stats['processed']
            
            # Print progress every 10 files (read processed value outside lock)
            if processed > 0 and processed % 10 == 0:
                self._print_stats()
                
        except Exception as e:
            logger.error(f"Error in file processing callback: {e}")
            with self.processing_lock:
                self.stats['errors'] += 1
    
    def _process_image_file(self, file_path: Path) -> bool:
        """Process a single image file with duplicate detection.
        
        Flow:
        1) 快速验证文件与图片格式；2) 计算哈希并查重；3) 记录元数据；4) 移动到输出目录。
        Args:
            file_path: Path to the image file
        
        Returns:
            True if processing successful, False otherwise
        """
        try:
            print(f"[处理] 正在处理文件: {file_path.name}")
            
            # 先进行图片快速校验，避免对无效文件做昂贵的哈希/数据库操作
            if not self.image_processor.is_supported_format(file_path):
                print(f"[跳过] 不支持的图片格式: {file_path.suffix}")
                return True  # 非错误，仅跳过
            if not self.image_processor.validate_image(file_path):
                print(f"[跳过] 非法或损坏的图片文件: {file_path.name}")
                return True  # 非错误，仅跳过
            
            # 获取文件大小（用于元数据）
            file_size = file_path.stat().st_size
            
            # Calculate file hash（用于去重）
            print(f"[计算] 计算文件hash: {file_path.name}")
            file_hash = db_manager.calculate_file_hash(file_path)
            
            # Check for duplicates
            existing_filename = db_manager.check_duplicate(file_hash)
            if existing_filename:
                print(f"[重复] 发现重复文件: {file_path.name} (与 {existing_filename} 重复)")
                
                # Delete duplicate file
                try:
                    file_path.unlink()
                    print(f"[删除] 已删除重复文件: {file_path.name}")
                    
                    with self.processing_lock:
                        self.stats['duplicates'] += 1
                    
                    return True
                    
                except Exception as e:
                    print(f"[错误] 删除重复文件失败 {file_path.name}: {e}")
                    logger.error(f"Failed to delete duplicate file {file_path.name}: {e}")
                    return False
            
            # Get basic image info (optional, for logging)
            try:
                image_info = self.image_processor.get_image_info(file_path)
                print(f"[信息] 图片尺寸: {image_info.get('width', 'N/A')}x{image_info.get('height', 'N/A')}, 格式: {image_info.get('format', 'N/A')}")
            except Exception as e:
                print(f"[警告] 无法获取图片信息: {e}")
                image_info = {}
            
            # Add to database
            try:
                _ = db_manager.add_image_metadata(
                    filename=file_path.name,
                    original_path=str(file_path),
                    file_size=file_size,
                    file_hash=file_hash
                )
                print(f"[数据库] 已保存文件信息到数据库: {file_path.name}")
            except Exception as e:
                print(f"[错误] 保存文件信息到数据库失败 {file_path.name}: {e}")
                logger.error(f"Failed to add image metadata for {file_path.name}: {e}")
                return False
            
            # Move file to output directory
            output_dir = Path(self.config['output_dir'])
            output_path = output_dir / file_path.name
            
            # Ensure unique output filename
            counter = 1
            while output_path.exists():
                stem = file_path.stem
                suffix = file_path.suffix
                output_path = output_dir / f"{stem}_{counter}{suffix}"
                counter += 1
            
            try:
                shutil.move(str(file_path), str(output_path))
                print(f"[移动] 文件已移动到: {output_path}")
                
                with self.processing_lock:
                    self.stats['moved'] += 1
                
                return True
                
            except Exception as e:
                print(f"[错误] 移动文件失败 {file_path.name}: {e}")
                logger.error(f"Failed to move file {file_path.name}: {e}")
                return False
            
        except Exception as e:
            print(f"[错误] 处理文件失败 {file_path.name}: {e}")
            logger.error(f"Failed to process image file {file_path.name}: {e}")
            return False
    
    def batch_process_folder(self, folder_path: str, recursive: bool = True) -> Dict[str, int]:
        """批量处理文件夹中的所有图片文件，计算hash去重后插入数据库。
        
        Args:
            folder_path: 要处理的文件夹路径
            recursive: 是否递归处理子文件夹
            
        Returns:
            处理结果统计字典，包含processed、duplicates、errors、skipped等计数
        """
        folder = Path(folder_path)
        if not folder.exists() or not folder.is_dir():
            logger.error(f"文件夹不存在或不是有效目录: {folder_path}")
            return {'processed': 0, 'duplicates': 0, 'errors': 0, 'skipped': 0}
        
        # 初始化统计
        batch_stats = {
            'processed': 0,
            'duplicates': 0, 
            'errors': 0,
            'skipped': 0
        }
        
        print(f"\n=== 开始批量处理文件夹 ===")
        print(f"目标文件夹: {folder.resolve()}")
        print(f"递归处理: {'是' if recursive else '否'}")
        print(f"支持格式: {', '.join(SUPPORTED_EXTENSIONS)}")
        print("========================\n")
        
        try:
            # 获取所有图片文件
            pattern = '**/*' if recursive else '*'
            all_files = []
            
            for ext in SUPPORTED_EXTENSIONS:
                # 支持大小写不敏感的扩展名匹配
                all_files.extend(folder.glob(f"{pattern}.{ext}"))
                all_files.extend(folder.glob(f"{pattern}.{ext.upper()}"))
            
            total_files = len(all_files)
            print(f"[扫描] 找到 {total_files} 个图片文件")
            
            if total_files == 0:
                print("[完成] 未找到任何图片文件")
                return batch_stats
            
            # 处理每个文件
            for i, file_path in enumerate(all_files, 1):
                try:
                    print(f"\n[{i}/{total_files}] 处理文件: {file_path.name}")
                    
                    # 验证文件格式和有效性
                    if not self.image_processor.is_supported_format(file_path):
                        print(f"[跳过] 不支持的图片格式: {file_path.suffix}")
                        batch_stats['skipped'] += 1
                        continue
                        
                    if not self.image_processor.validate_image(file_path):
                        print(f"[跳过] 非法或损坏的图片文件: {file_path.name}")
                        batch_stats['skipped'] += 1
                        continue
                    
                    # 获取文件信息
                    file_size = file_path.stat().st_size
                    
                    # 计算文件hash
                    print(f"[计算] 计算文件hash...")
                    file_hash = db_manager.calculate_file_hash(file_path)
                    
                    # 检查重复
                    existing_filename = db_manager.check_duplicate(file_hash)
                    if existing_filename:
                        print(f"[重复] 发现重复文件 (与 {existing_filename} 重复)")
                        batch_stats['duplicates'] += 1
                        continue
                    
                    # 插入数据库
                    try:
                        _ = db_manager.add_image_metadata(
                            filename=file_path.name,
                            original_path=str(file_path),
                            file_size=file_size,
                            file_hash=file_hash
                        )
                        print(f"[数据库] 已保存文件信息到数据库")
                        batch_stats['processed'] += 1
                        
                    except Exception as e:
                        print(f"[错误] 保存到数据库失败: {e}")
                        logger.error(f"Failed to add image metadata for {file_path.name}: {e}")
                        batch_stats['errors'] += 1
                        
                except Exception as e:
                    print(f"[错误] 处理文件失败: {e}")
                    logger.error(f"Failed to process file {file_path.name}: {e}")
                    batch_stats['errors'] += 1
                
                # 每处理10个文件打印一次进度
                if i % 10 == 0:
                    print(f"\n--- 进度报告 ({i}/{total_files}) ---")
                    print(f"已处理: {batch_stats['processed']}")
                    print(f"重复: {batch_stats['duplicates']}")
                    print(f"跳过: {batch_stats['skipped']}")
                    print(f"错误: {batch_stats['errors']}")
                    print("---------------------------\n")
            
            # 打印最终统计
            print(f"\n=== 批量处理完成 ===")
            print(f"总文件数: {total_files}")
            print(f"成功处理: {batch_stats['processed']}")
            print(f"重复文件: {batch_stats['duplicates']}")
            print(f"跳过文件: {batch_stats['skipped']}")
            print(f"错误文件: {batch_stats['errors']}")
            print("==================\n")
            
            return batch_stats
            
        except Exception as e:
            logger.error(f"批量处理文件夹失败: {e}")
            print(f"[错误] 批量处理失败: {e}")
            return batch_stats
    
    def _print_stats(self):
        """Print current processing statistics."""
        with self.processing_lock:
            elapsed = time.time() - self.stats['start_time'] if self.stats['start_time'] else 0
            queue_size = self.file_scanner.get_queue_size() if self.file_scanner else 0
            
            print(f"\n=== 处理统计 ===")
            print(f"已处理: {self.stats['processed']} 个文件")
            print(f"重复文件: {self.stats['duplicates']} 个")
            print(f"已移动: {self.stats['moved']} 个")
            print(f"错误: {self.stats['errors']} 个")
            print(f"队列中: {queue_size} 个文件")
            print(f"运行时间: {elapsed:.1f} 秒")
            print(f"================\n")
    
    def start(self):
        """Start the application."""
        if self.is_running:
            logger.warning("Application is already running")
            return
        
        try:
            print("\n=== 图片重复检测器启动 ===")
            print(f"扫描路径: {self.config['scan_paths']}")
            print(f"输出目录: {self.config['output_dir']}")
            print(f"扫描间隔: {self.config.get('scan_interval', 5)} 秒")
            print("========================\n")
            
            # Reset statistics
            self.stats = {
                'processed': 0,
                'duplicates': 0,
                'moved': 0,
                'errors': 0,
                'start_time': time.time()
            }
            
            # Start file scanner
            if not self.file_scanner.start():
                logger.error("Failed to start file scanner")
                return
            
            self.is_running = True
            logger.info("Application started successfully")
            
            # Print initial stats
            self._print_stats()
            
            # Keep running until stopped
            try:
                # 动态打印间隔（当队列空闲时减少打印频率）
                idle_print_interval = 20
                busy_print_interval = 10
                while self.is_running:
                    # 根据队列状态调整打印频率
                    interval = busy_print_interval
                    if self.file_scanner and self.file_scanner.is_queue_empty():
                        interval = idle_print_interval
                    time.sleep(interval)
                    if self.is_running:
                        self._print_stats()
                        
            except KeyboardInterrupt:
                print("\n收到停止信号，正在关闭...")
                self.stop()
            
        except Exception as e:
            logger.error(f"Failed to start application: {e}")
            self.stop()
    
    def stop(self):
        """Stop the application gracefully: stop worker threads, print final stats, and close database connections."""
        if not self.is_running:
            # 即使当前状态为未运行，也尝试关闭数据库连接以确保资源释放
            try:
                db_manager.close()
            except Exception:
                pass
            return
        
        print("\n正在停止应用程序...")
        
        try:
            # 标记停止运行，通知后台循环退出
            self.is_running = False
            
            # 停止文件扫描与处理线程
            if self.file_scanner:
                self.file_scanner.stop()
            
            # 打印最终统计快照
            print("\n=== 最终统计 ===")
            self._print_stats()
            
            # 确保数据库连接被正确释放，避免连接泄漏
            try:
                db_manager.close()
            except Exception as e:
                logger.warning(f"Failed to close database cleanly: {e}")
            
            logger.info("Application stopped successfully")
            
        except Exception as e:
            logger.error(f"Error stopping application: {e}")

def load_config() -> Dict[str, Any]:
    """从环境变量加载配置（可被命令行参数覆盖）。
    
    返回：
        配置字典
    """
    # 解析扫描路径，兼容 SCAN_PATHS 与历史 WATCH_PATHS，逗号分隔
    scan_paths_str = os.getenv('SCAN_PATHS', os.getenv('WATCH_PATHS', ''))
    scan_paths = [path.strip() for path in scan_paths_str.split(',') if path.strip()]
    
    if not scan_paths:
        scan_paths = ['./test_input']  # 默认路径，便于开箱即用
    
    config = {
        'scan_paths': scan_paths,
        'output_dir': os.getenv('OUTPUT_DIR', './converted_images'),
        'scan_interval': int(os.getenv('SCAN_INTERVAL', '5')),
        'log_level': os.getenv('LOG_LEVEL', 'INFO'),
    }
    
    return config

def setup_logging(log_level: str = 'INFO'):
    """Setup logging configuration.
    
    Args:
        log_level: Logging level
    """
    # Configure coloredlogs
    coloredlogs.install(
        level=log_level,
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Set specific logger levels
    logging.getLogger('PIL').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)

def signal_handler(signum, frame):
    """Handle system signals for graceful shutdown.
    Note: main() registers this handler and will call app.stop() in finally block.
    Here we simply raise KeyboardInterrupt to trigger graceful shutdown path.
    """
    print(f"\n收到信号 {signum}，正在关闭应用程序...")
    raise KeyboardInterrupt

def main():
    """Main entry point."""
    # Setup argument parser
    parser = argparse.ArgumentParser(description='Image Duplicate Detector')
    parser.add_argument('--config', help='Configuration file path')
    parser.add_argument('--scan-paths', nargs='+', help='Paths to scan for images')
    parser.add_argument('--output-dir', help='Output directory for processed images')
    parser.add_argument('--scan-interval', type=int, help='Scan interval in seconds')
    parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'], help='Log level')
    
    # 添加批量处理功能的参数
    parser.add_argument('--batch-process', metavar='FOLDER_PATH', help='批量处理指定文件夹中的所有图片文件，计算hash去重后插入数据库')
    parser.add_argument('--no-recursive', action='store_true', help='批量处理时不递归处理子文件夹（默认递归处理）')
    
    args = parser.parse_args()
    
    # Load configuration
    config = load_config()
    
    # Override with command line arguments
    if args.scan_paths:
        config['scan_paths'] = args.scan_paths
    if args.output_dir:
        config['output_dir'] = args.output_dir
    if args.scan_interval:
        config['scan_interval'] = args.scan_interval
    if args.log_level:
        config['log_level'] = args.log_level
    
    # Setup logging
    setup_logging(config['log_level'])
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create and run application
    app = ImageDuplicateDetector(config)
    
    if not app.initialize():
        logger.error("Failed to initialize application")
        sys.exit(1)
    
    try:
        # 检查是否是批量处理模式
        if args.batch_process:
            # 批量处理模式
            recursive = not args.no_recursive
            print(f"\n=== 批量处理模式 ===")
            print(f"目标文件夹: {args.batch_process}")
            print(f"递归处理: {'是' if recursive else '否'}")
            print("==================\n")
            
            # 执行批量处理
            result = app.batch_process_folder(args.batch_process, recursive=recursive)
            
            # 打印最终结果
            print(f"\n=== 批量处理结果 ===")
            print(f"成功处理: {result['processed']} 个文件")
            print(f"重复文件: {result['duplicates']} 个文件")
            print(f"跳过文件: {result['skipped']} 个文件")
            print(f"错误文件: {result['errors']} 个文件")
            print("==================\n")
            
            if result['errors'] > 0:
                print(f"警告: 有 {result['errors']} 个文件处理失败，请检查日志")
                sys.exit(1)
            else:
                print("批量处理成功完成！")
        else:
            # 常规监控模式
            app.start()
    except KeyboardInterrupt:
        print("\n用户中断，正在退出...")
    except Exception as e:
        logger.error(f"Application error: {e}")
        sys.exit(1)
    finally:
        app.stop()

if __name__ == "__main__":
    main()