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
            # Initialize database
            if not initialize_database():
                logger.error("Failed to initialize database")
                return False
            
            # Create output directory
            output_dir = Path(self.config['output_dir'])
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Initialize file scanner
            scan_interval = self.config.get('scan_interval', 5)
            self.file_scanner = FileScanner(
                supported_extensions=SUPPORTED_EXTENSIONS,
                file_processor_callback=self._process_file,
                scan_interval=scan_interval
            )
            
            # Add scan paths
            for scan_path in self.config['scan_paths']:
                if not self.file_scanner.add_scan_path(scan_path, recursive=True):
                    logger.error(f"Failed to add scan path: {scan_path}")
                    return False
            
            logger.info("Application initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize application: {e}")
            return False
    
    def _process_file(self, file_path: Path):
        """Process a single file (called by file scanner).
        
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
            
            with self.processing_lock:
                if success:
                    self.stats['processed'] += 1
                else:
                    self.stats['errors'] += 1
            
            # Print progress every 10 files
            if self.stats['processed'] % 10 == 0:
                self._print_stats()
                
        except Exception as e:
            logger.error(f"Error in file processing callback: {e}")
            with self.processing_lock:
                self.stats['errors'] += 1
    
    def _process_image_file(self, file_path: Path) -> bool:
        """Process a single image file with duplicate detection.
        
        Args:
            file_path: Path to the image file
        
        Returns:
            True if processing successful, False otherwise
        """
        try:
            print(f"[处理] 正在处理文件: {file_path.name}")
            
            # Get file information
            file_size = file_path.stat().st_size
            
            # Calculate file hash
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
                metadata_id = db_manager.add_image_metadata(
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
                while self.is_running:
                    time.sleep(10)  # Print stats every 10 seconds
                    if self.is_running:
                        self._print_stats()
                        
            except KeyboardInterrupt:
                print("\n收到停止信号，正在关闭...")
                self.stop()
            
        except Exception as e:
            logger.error(f"Failed to start application: {e}")
            self.stop()
    
    def stop(self):
        """Stop the application."""
        if not self.is_running:
            return
        
        print("\n正在停止应用程序...")
        
        try:
            self.is_running = False
            
            # Stop file scanner
            if self.file_scanner:
                self.file_scanner.stop()
            
            # Print final statistics
            print("\n=== 最终统计 ===")
            self._print_stats()
            
            logger.info("Application stopped successfully")
            
        except Exception as e:
            logger.error(f"Error stopping application: {e}")

def load_config() -> Dict[str, Any]:
    """Load configuration from environment variables.
    
    Returns:
        Configuration dictionary
    """
    # Parse scan paths
    scan_paths_str = os.getenv('SCAN_PATHS', os.getenv('WATCH_PATHS', ''))
    scan_paths = [path.strip() for path in scan_paths_str.split(',') if path.strip()]
    
    if not scan_paths:
        scan_paths = ['./test_input']  # Default path
    
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
    """Handle system signals for graceful shutdown."""
    print(f"\n收到信号 {signum}，正在关闭应用程序...")
    sys.exit(0)

def main():
    """Main entry point."""
    # Setup argument parser
    parser = argparse.ArgumentParser(description='Image Duplicate Detector')
    parser.add_argument('--config', help='Configuration file path')
    parser.add_argument('--scan-paths', nargs='+', help='Paths to scan for images')
    parser.add_argument('--output-dir', help='Output directory for processed images')
    parser.add_argument('--scan-interval', type=int, help='Scan interval in seconds')
    parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'], help='Log level')
    
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