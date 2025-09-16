#!/usr/bin/env python3
"""
Main application for Image Duplicate Detector.
Scans folders for image files, detects duplicates by hash, and manages file operations.
"""

# Standard library imports
import argparse
import logging
import os
import signal
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Dict, Any, Optional, List, Union

# Third-party imports
import coloredlogs
from dotenv import load_dotenv

# Local imports
from database import db_manager, initialize_database
from file_monitor import FileScanner
from image_processor import ImageProcessor, SUPPORTED_EXTENSIONS

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

class ImageDuplicateDetector:
    """
    主应用程序类，用于图片重复检测和文件管理。
    
    该类提供了完整的图片文件监控、重复检测、数据库管理和文件操作功能。
    支持实时监控指定目录，自动检测重复文件并进行相应处理。
    
    Attributes:
        config (Dict[str, Any]): 应用程序配置字典
        is_running (bool): 应用程序运行状态标志
        processing_lock (Lock): 线程同步锁，用于保护统计数据
        image_processor (ImageProcessor): 图片处理器实例
        file_scanner (Optional[FileScanner]): 文件扫描器实例
        stats (Dict[str, Union[int, float, None]]): 处理统计信息
    """
    
    def __init__(self, config: Dict[str, Any]) -> None:
        """
        初始化应用程序实例。
        
        Args:
            config (Dict[str, Any]): 应用程序配置字典，包含扫描路径、输出目录等设置
        """
        self.config: Dict[str, Any] = config
        self.is_running: bool = False
        self.processing_lock: Lock = Lock()
        
        # Initialize components
        self.image_processor: ImageProcessor = ImageProcessor()
        self.file_scanner: Optional[FileScanner] = None
        
        # Statistics
        self.stats: Dict[str, Union[int, float, None]] = {
            'processed': 0,
            'duplicates': 0,
            'moved': 0,
            'errors': 0,
            'start_time': None
        }
        
        logger.info("ImageDuplicateDetector initialized")
    
    def initialize(self) -> bool:
        """
        初始化数据库和组件。
        
        执行以下初始化步骤：
        1. 初始化数据库连接和表结构
        2. 创建输出目录
        3. 初始化文件扫描器
        4. 验证并添加扫描路径
        
        Returns:
            bool: 初始化成功返回 True，失败返回 False
            
        Raises:
            Exception: 当初始化过程中发生错误时抛出异常
        """
        try:
            # Initialize database connection and tables
            if not initialize_database():
                logger.error("数据库初始化失败：无法建立连接或创建表结构")
                return False
            
            # Ensure output directory exists
            output_dir = Path(self.config['output_dir'])
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"输出目录已准备就绪: {output_dir.resolve()}")
            except (OSError, PermissionError) as e:
                logger.error(f"无法创建输出目录 {output_dir}: {e}")
                return False
            
            # Initialize file scanner with supported extensions and callback
            scan_interval = self.config.get('scan_interval', 5)
            try:
                self.file_scanner = FileScanner(
                    supported_extensions=SUPPORTED_EXTENSIONS,
                    file_processor_callback=self._process_file,
                    scan_interval=scan_interval
                )
            except Exception as e:
                logger.error(f"文件扫描器初始化失败: {e}")
                return False
            
            # Validate and add scan paths
            valid_paths_count = 0
            for scan_path in self.config['scan_paths']:
                try:
                    if self.file_scanner.add_scan_path(scan_path, recursive=True):
                        valid_paths_count += 1
                        logger.info(f"已添加扫描路径: {scan_path}")
                    else:
                        logger.warning(f"无法添加扫描路径: {scan_path} (路径不存在或无访问权限)")
                except Exception as e:
                    logger.error(f"添加扫描路径 {scan_path} 时发生错误: {e}")
            
            if valid_paths_count == 0:
                logger.error("没有有效的扫描路径，应用程序无法启动")
                return False
            
            logger.info(f"应用程序初始化成功，共添加 {valid_paths_count} 个有效扫描路径")
            return True
            
        except Exception as e:
            logger.error(f"应用程序初始化过程中发生未预期的错误: {e}")
            logger.exception("详细错误信息:")
            return False
    
    def _process_file(self, file_path: Path) -> None:
        """
        处理单个文件（由文件扫描器调用）。
        
        该方法在 FileScanner 的工作线程中运行，需要保持快速和线程安全。
        执行文件存在性检查、格式验证，然后调用图片处理逻辑。
        
        Args:
            file_path (Path): 图片文件的路径对象
            
        Note:
            此方法在后台线程中执行，应避免长时间阻塞操作
        """
        try:
            # Check if file still exists and is accessible
            if not file_path.exists():
                logger.debug(f"文件已不存在: {file_path.name}")
                return
            
            if not file_path.is_file():
                logger.debug(f"路径不是文件: {file_path.name}")
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
                
        except FileNotFoundError:
            logger.debug(f"文件处理过程中文件消失: {file_path.name}")
        except PermissionError:
            logger.warning(f"文件访问权限不足: {file_path.name}")
            with self.processing_lock:
                self.stats['errors'] += 1
        except Exception as e:
            logger.error(f"文件处理回调中发生错误: {e}")
            logger.exception(f"处理文件 {file_path.name} 时的详细错误:")
            with self.processing_lock:
                self.stats['errors'] += 1
    
    def _validate_file_format(self, file_path: Path) -> bool:
        """
        验证文件格式和有效性。
        
        Args:
            file_path (Path): 文件路径
            
        Returns:
            bool: 文件有效返回 True，否则返回 False
        """
        if not self.image_processor.is_supported_format(file_path):
            print(f"[跳过] 不支持的图片格式: {file_path.suffix}")
            return False
            
        if not self.image_processor.validate_image(file_path):
            print(f"[跳过] 非法或损坏的图片文件: {file_path.name}")
            return False
            
        return True
    
    def _handle_duplicate_file(self, file_path: Path, existing_filename: str) -> bool:
        """
        处理重复文件。
        
        Args:
            file_path (Path): 重复文件路径
            existing_filename (str): 已存在的文件名
            
        Returns:
            bool: 处理成功返回 True，失败返回 False
        """
        print(f"[重复] 发现重复文件: {file_path.name} (与 {existing_filename} 重复)")
        
        try:
            file_path.unlink()
            print(f"[删除] 已删除重复文件: {file_path.name}")
            
            with self.processing_lock:
                self.stats['duplicates'] += 1
            
            return True
            
        except Exception as e:
            print(f"[错误] 删除重复文件失败 {file_path.name}: {e}")
            logger.error(f"删除重复文件失败 - 文件: {file_path.name}, 错误: {e}")
            return False
    
    def _save_file_to_database(self, file_path: Path, file_size: int, file_hash: str) -> bool:
        """
        保存文件信息到数据库。
        
        Args:
            file_path (Path): 文件路径
            file_size (int): 文件大小
            file_hash (str): 文件哈希值
            
        Returns:
            bool: 保存成功返回 True，失败返回 False
        """
        try:
            _ = db_manager.add_file_record(
                original_name=file_path.name,
                source_path=str(file_path),
                file_size=file_size,
                file_hash=file_hash,
                extension=file_path.suffix.lower(),
                created_at=datetime.utcnow()
            )
            print(f"[数据库] 已保存文件信息到数据库: {file_path.name}")
            return True
        except Exception as e:
            print(f"[错误] 保存文件信息到数据库失败 {file_path.name}: {e}")
            logger.error(f"数据库操作失败 - 文件: {file_path.name}, 错误: {e}")
            logger.exception("数据库操作详细错误:")
            return False
    
    def _move_file_to_output(self, file_path: Path) -> bool:
        """
        移动文件到输出目录。
        
        Args:
            file_path (Path): 源文件路径
            
        Returns:
            bool: 移动成功返回 True，失败返回 False
        """
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
            
        except (OSError, PermissionError) as e:
            print(f"[错误] 移动文件失败 {file_path.name}: {e}")
            logger.error(f"文件移动失败 - 源: {file_path}, 目标: {output_path}, 错误: {e}")
            return False
        except Exception as e:
                print(f"[错误] 移动文件时发生未预期错误 {file_path.name}: {e}")
                logger.error(f"文件移动过程中的未预期错误: {e}")
                logger.exception("文件移动详细错误:")
                return False
    
    def _process_image_file(self, file_path: Path) -> bool:
        """
        处理单个图片文件，包含重复检测功能。
        
        执行完整的图片处理流程：
        1. 快速验证文件与图片格式
        2. 计算文件哈希并检查重复
        3. 记录文件元数据到数据库
        4. 移动文件到输出目录
        
        Args:
            file_path (Path): 图片文件的路径对象
        
        Returns:
            bool: 处理成功返回 True，失败返回 False
            
        Note:
            对于重复文件，会自动删除并更新统计信息
        """
        try:
            print(f"[处理] 正在处理文件: {file_path.name}")
            
            # 验证文件格式和有效性
            if not self._validate_file_format(file_path):
                return True  # 非错误，仅跳过
            
            # 获取文件大小
            file_size = file_path.stat().st_size
            

            file_hash = db_manager.calculate_file_hash(file_path)
            # 计算文件哈希
            print(f"[计算] 计算文件hash: {file_hash}")
            # 检查重复文件
            existing_filename = db_manager.check_duplicate(file_hash)
            if existing_filename:
                return self._handle_duplicate_file(file_path, existing_filename)
            
            # 获取图片信息（可选，用于日志）
            try:
                image_info = self.image_processor.get_image_info(file_path)
                print(f"[信息] 图片尺寸: {image_info.get('width', 'N/A')}x{image_info.get('height', 'N/A')}, 格式: {image_info.get('format', 'N/A')}")
            except Exception as e:
                print(f"[警告] 无法获取图片信息: {e}")
            
            # 保存到数据库
            if not self._save_file_to_database(file_path, file_size, file_hash):
                return False
            
            # 移动文件到输出目录
            return self._move_file_to_output(file_path)
            
        except Exception as e:
            print(f"[错误] 处理文件失败 {file_path.name}: {e}")
            logger.error(f"处理图片文件失败 - 文件: {file_path.name}, 错误: {e}")
            logger.exception("处理图片文件详细错误:")
            return False
    
    def batch_process_folder(self, folder_path: str, recursive: bool = True, batch_size: int = 100) -> Dict[str, int]:
        """
        批量处理文件夹中的所有图片文件（优化版本）。
        
        扫描指定文件夹，对所有支持的图片格式进行哈希计算和重复检测，
        然后将文件信息插入数据库。使用批量处理和内存优化提高性能。
        
        Args:
            folder_path (str): 要处理的文件夹路径
            recursive (bool, optional): 是否递归处理子文件夹，默认为 True
            batch_size (int, optional): 批量处理大小，默认为 100
            
        Returns:
            Dict[str, int]: 处理结果统计字典，包含以下键值：
                - processed: 成功处理的文件数量
                - duplicates: 发现的重复文件数量
                - errors: 处理失败的文件数量
                - skipped: 跳过的文件数量（格式不支持或文件损坏）
                
        Raises:
            Exception: 当文件夹不存在或访问权限不足时抛出异常
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
        
        print(f"\n=== 开始批量处理文件夹（优化版本）===")
        print(f"目标文件夹: {folder.resolve()}")
        print(f"递归处理: {'是' if recursive else '否'}")
        print(f"批量大小: {batch_size}")
        print(f"支持格式: {', '.join(SUPPORTED_EXTENSIONS)}")
        print("========================\n")
        
        try:
            # 使用生成器优化内存使用，避免一次性加载所有文件
            def get_image_files():
                """生成器函数，逐个返回图片文件路径"""
                pattern = '**/*' if recursive else '*'
                for ext in SUPPORTED_EXTENSIONS:
                    # 支持大小写不敏感的扩展名匹配
                    yield from folder.glob(f"{pattern}{ext}")
                    yield from folder.glob(f"{pattern}{ext.upper()}")
            
            # 预先统计文件数量用于进度显示
            all_files = list(get_image_files())
            total_files = len(all_files)
            print(f"[扫描] 找到 {total_files} 个图片文件")
            
            if total_files == 0:
                print("[完成] 未找到任何图片文件")
                return batch_stats
            
            # 批量处理文件，减少数据库连接开销
            processed_count = 0
            start_time = time.time()
            
            for i, file_path in enumerate(all_files, 1):
                try:
                    # 显示进度（每处理10个文件或最后一个文件时显示）
                    if i % 10 == 0 or i == total_files:
                        elapsed = time.time() - start_time
                        rate = i / elapsed if elapsed > 0 else 0
                        print(f"[进度] {i}/{total_files} ({i/total_files*100:.1f}%) - 处理速度: {rate:.1f} 文件/秒")
                    
                    # 快速预检查：文件大小和扩展名
                    if not self.image_processor.is_supported_format(file_path):
                        batch_stats['skipped'] += 1
                        continue
                    
                    # 获取文件基本信息
                    try:
                        file_stat = file_path.stat()
                        file_size = file_stat.st_size
                        
                        # 跳过空文件
                        if file_size == 0:
                            logger.debug(f"跳过空文件: {file_path.name}")
                            batch_stats['skipped'] += 1
                            continue
                            
                    except OSError as e:
                        logger.warning(f"无法获取文件信息 {file_path.name}: {e}")
                        batch_stats['errors'] += 1
                        continue
                    
                    # 验证图像有效性（使用优化的验证方法）
                    if not self.image_processor.validate_image(file_path):
                        logger.debug(f"跳过无效图像: {file_path.name}")
                        batch_stats['skipped'] += 1
                        continue
                    
                    # 计算文件hash（使用优化的哈希计算）
                    file_hash = db_manager.calculate_file_hash(file_path)
                    
                    # 检查重复（使用优化的查询）
                    existing_filename = db_manager.check_duplicate(file_hash)
                    if existing_filename:
                        print(f"[重复] 发现重复文件 (与 {existing_filename} 重复)")
                        batch_stats['duplicates'] += 1
                        continue
                    
                    # 插入数据库
                    try:
                        from datetime import datetime
                        _ = db_manager.add_file_record(
                            original_name=file_path.name,
                            source_path=str(file_path),
                            file_size=file_size,
                            file_hash=file_hash,
                            extension=file_path.suffix.lower(),
                            created_at=datetime.utcnow()
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
    
    def _print_stats(self) -> None:
        """
        打印当前处理统计信息。
        
        显示已处理文件数、重复文件数、移动文件数、错误数、
        队列中待处理文件数以及运行时间等统计信息。
        
        Note:
            使用线程锁确保统计数据的一致性
        """
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
    
    def start(self) -> None:
        """
        启动应用程序。
        
        初始化统计信息，启动文件扫描器，并进入主循环。
        主循环会定期打印统计信息，直到收到停止信号。
        
        Note:
            - 如果应用程序已在运行，会记录警告并返回
            - 支持通过 Ctrl+C 优雅停止
            - 根据队列状态动态调整统计信息打印频率
        """
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
    
    def stop(self) -> None:
        """
        优雅地停止应用程序。
        
        执行以下停止步骤：
        1. 停止工作线程
        2. 打印最终统计信息
        3. 关闭数据库连接
        
        确保所有资源得到正确释放，避免连接泄漏。
        
        Note:
            即使应用程序未运行，也会尝试关闭数据库连接以确保资源释放
        """
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
    """
    从环境变量加载应用程序配置。
    
    读取环境变量并构建配置字典，支持命令行参数覆盖。
    如果未设置扫描路径，将使用默认的测试目录。
    
    Returns:
        Dict[str, Any]: 包含以下配置项的字典：
            - scan_paths: 扫描路径列表
            - output_dir: 输出目录路径
            - scan_interval: 扫描间隔（秒）
            - log_level: 日志级别
            
    Note:
        兼容 SCAN_PATHS 和历史的 WATCH_PATHS 环境变量
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

def setup_logging(log_level: str = 'INFO') -> None:
    """
    设置日志配置。
    
    配置 coloredlogs 以提供彩色日志输出，并设置特定库的日志级别
    以减少不必要的日志信息。
    
    Args:
        log_level (str, optional): 日志级别，默认为 'INFO'
        
    Note:
        - PIL 和 urllib3 的日志级别被设置为 WARNING 以减少噪音
        - 使用标准的时间戳格式
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

def signal_handler(signum: int, frame) -> None:
    """
    处理系统信号以实现优雅关闭。
    
    当接收到 SIGINT (Ctrl+C) 或 SIGTERM 信号时，
    设置全局停止标志以通知主程序优雅退出。
    
    Args:
        signum (int): 信号编号
        frame: 当前堆栈帧（未使用）
        
    Note:
        main() 函数会注册此处理器并监控全局停止标志
    """
    print(f"\n收到信号 {signum}，正在关闭应用程序...")
    raise KeyboardInterrupt

def main() -> None:
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