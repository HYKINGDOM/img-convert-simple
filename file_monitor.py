#!/usr/bin/env python3
"""
File scanning module for Image Converter application.
Scans specified folders for image files at regular intervals.
"""

import logging
import time
from pathlib import Path
from typing import Set, Callable, Optional, Dict, Any, List
from threading import Thread, Event
from queue import Queue
import os

# Configure logging
logger = logging.getLogger(__name__)

class FileScanner:
    """Scans directories for image files at regular intervals."""
    
    def __init__(self, 
                 supported_extensions: Set[str],
                 file_processor_callback: Callable[[Path], None],
                 scan_interval: int = 5):
        """Initialize file scanner.
        
        Args:
            supported_extensions: Set of supported file extensions
            file_processor_callback: Callback function to process detected files
            scan_interval: Scan interval in seconds
        """
        self.supported_extensions = {ext.lower() for ext in supported_extensions}
        self.file_processor_callback = file_processor_callback
        self.scan_interval = scan_interval
        
        # Threading components
        self.file_queue = Queue()
        self.stop_event = Event()
        self.scan_thread = None
        self.process_thread = None
        
        # Scan paths
        self.scan_paths = set()
        
        self.is_running = False
        
        logger.info(f"FileScanner initialized with interval: {scan_interval}s, extensions: {self.supported_extensions}")
    
    def add_scan_path(self, path: str, recursive: bool = True) -> bool:
        """Add a directory to scan.
        
        Args:
            path: Directory path to scan
            recursive: Whether to scan subdirectories
        
        Returns:
            True if path added successfully, False otherwise
        """
        scan_path = Path(path)
        
        if not scan_path.exists():
            logger.error(f"Scan path does not exist: {scan_path}")
            return False
        
        if not scan_path.is_dir():
            logger.error(f"Scan path is not a directory: {scan_path}")
            return False
        
        self.scan_paths.add((str(scan_path), recursive))
        logger.info(f"Added scan path: {scan_path} (recursive={recursive})")
        return True
    
    def remove_scan_path(self, path: str):
        """Remove a directory from scanning.
        
        Args:
            path: Directory path to remove
        """
        scan_path = str(Path(path))
        self.scan_paths = {(p, r) for p, r in self.scan_paths if p != scan_path}
        logger.info(f"Removed scan path: {scan_path}")
    
    def _is_image_file(self, file_path: Path) -> bool:
        """Check if file is a supported image format."""
        return file_path.suffix.lower() in self.supported_extensions
    
    def _scan_directory(self, directory: Path, recursive: bool) -> List[Path]:
        """Scan directory for image files.
        
        Args:
            directory: Directory to scan
            recursive: Whether to scan subdirectories
        
        Returns:
            List of image file paths found
        """
        image_files = []
        
        try:
            if recursive:
                # Recursive scan using glob
                for ext in self.supported_extensions:
                    pattern = f"**/*{ext}"
                    image_files.extend(directory.glob(pattern))
            else:
                # Non-recursive scan
                for item in directory.iterdir():
                    if item.is_file() and self._is_image_file(item):
                        image_files.append(item)
        
        except Exception as e:
            logger.error(f"Error scanning directory {directory}: {e}")
        
        return image_files
    
    def _scan_worker(self):
        """Worker thread for scanning directories."""
        logger.info("File scanner worker started")
        
        while not self.stop_event.is_set():
            try:
                # Scan all configured paths
                for scan_path, recursive in self.scan_paths:
                    if self.stop_event.is_set():
                        break
                    
                    directory = Path(scan_path)
                    if not directory.exists():
                        logger.warning(f"Scan path no longer exists: {directory}")
                        continue
                    
                    # Scan for image files
                    image_files = self._scan_directory(directory, recursive)
                    
                    # Add found files to queue
                    for file_path in image_files:
                        if not self.stop_event.is_set():
                            self.file_queue.put(file_path)
                            logger.debug(f"Added file to queue: {file_path.name}")
                
                # Wait for next scan interval
                self.stop_event.wait(self.scan_interval)
                
            except Exception as e:
                logger.error(f"Error in scan worker: {e}")
                time.sleep(1)  # Brief pause before retrying
        
        logger.info("File scanner worker stopped")
    
    def _process_worker(self):
        """Worker thread for processing files from queue."""
        logger.info("File processor worker started")
        
        while not self.stop_event.is_set():
            try:
                # Get file from queue with timeout
                try:
                    file_path = self.file_queue.get(timeout=1.0)
                except:
                    continue  # Timeout, check stop event
                
                # Process the file
                try:
                    self.file_processor_callback(file_path)
                    logger.debug(f"Processed file: {file_path.name}")
                except Exception as e:
                    logger.error(f"Error processing file {file_path.name}: {e}")
                
                # Mark task as done
                self.file_queue.task_done()
                
            except Exception as e:
                logger.error(f"Error in process worker: {e}")
                time.sleep(1)  # Brief pause before retrying
        
        logger.info("File processor worker stopped")
    
    def start(self) -> bool:
        """Start the file scanner.
        
        Returns:
            True if started successfully, False otherwise
        """
        if self.is_running:
            logger.warning("File scanner is already running")
            return False
        
        if not self.scan_paths:
            logger.error("No scan paths configured")
            return False
        
        try:
            self.stop_event.clear()
            
            # Start worker threads
            self.scan_thread = Thread(target=self._scan_worker, daemon=True)
            self.process_thread = Thread(target=self._process_worker, daemon=True)
            
            self.scan_thread.start()
            self.process_thread.start()
            
            self.is_running = True
            logger.info("File scanner started successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start file scanner: {e}")
            return False
    
    def stop(self):
        """Stop the file scanner."""
        if not self.is_running:
            logger.warning("File scanner is not running")
            return
        
        logger.info("Stopping file scanner...")
        
        # Signal threads to stop
        self.stop_event.set()
        
        # Wait for threads to finish
        if self.scan_thread and self.scan_thread.is_alive():
            self.scan_thread.join(timeout=5.0)
        
        if self.process_thread and self.process_thread.is_alive():
            self.process_thread.join(timeout=5.0)
        
        self.is_running = False
        logger.info("File scanner stopped")
    
    def get_queue_size(self) -> int:
        """Get current queue size.
        
        Returns:
            Number of files in processing queue
        """
        return self.file_queue.qsize()
    
    def is_queue_empty(self) -> bool:
        """Check if processing queue is empty.
        
        Returns:
            True if queue is empty, False otherwise
        """
        return self.file_queue.empty()

# Backward compatibility alias
FileMonitor = FileScanner