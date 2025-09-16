#!/usr/bin/env python3
"""
Database module for Image Converter application.
Handles PostgreSQL connection, schema creation, and image metadata operations.
"""

import hashlib
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from contextlib import contextmanager

from dotenv import load_dotenv
from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, BigInteger,
    Boolean, Text, Index, UniqueConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

# Database configuration
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://localhost:5432/defaultdb')

# SQLAlchemy setup
Base = declarative_base()

class FileRecord(Base):
    """SQLAlchemy model for file records storage."""
    __tablename__ = 'file_records'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    hash = Column(String(128), nullable=False, unique=True)
    original_name = Column(String(500), nullable=False)
    file_size = Column(BigInteger, nullable=False)
    extension = Column(String(50), nullable=False)
    created_at = Column(DateTime, nullable=False)
    processed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    source_path = Column(Text, nullable=False)
    target_path = Column(Text, nullable=True)
    hash_type = Column(String(20), nullable=False, default='sha256')
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_file_records_hash', 'hash'),
        Index('idx_file_records_extension', 'extension'),
        Index('idx_file_records_processed_at', 'processed_at'),
        Index('idx_file_records_file_size', 'file_size'),
        UniqueConstraint('hash', name='uq_file_hash'),
    )
    
    def __repr__(self):
        return f"<FileRecord(original_name='{self.original_name}', hash='{self.hash[:8]}...')>"

class DatabaseManager:
    """Manages database connections and operations with connection pooling."""
    
    def __init__(self, database_url: str = DATABASE_URL):
        """Initialize database manager with connection pooling."""
        self.database_url = database_url
        self.engine = None
        self.SessionLocal = None
        self._initialize_engine()
    
    def _initialize_engine(self):
        """Initialize SQLAlchemy engine with connection pooling."""
        try:
            self.engine = create_engine(
                self.database_url,
                poolclass=QueuePool,
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,
                pool_recycle=3600,
                echo=False  # Set to True for SQL debugging
            )
            self.SessionLocal = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=self.engine
            )
            logger.info("Database engine initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database engine: {e}")
            raise
    
    def create_tables(self):
        """Create all database tables if they don't exist."""
        try:
            Base.metadata.create_all(bind=self.engine)
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Failed to create database tables: {e}")
            raise
    
    @contextmanager
    def get_session(self):
        """Context manager for database sessions."""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()
    
    def calculate_file_hash(self, file_path: Path, chunk_size: int = 65536) -> str:
        """
        计算文件的 SHA-256 哈希值（优化版本）。
        
        使用更大的缓冲区提高 I/O 性能，并添加文件大小检查优化。
        
        Args:
            file_path (Path): 文件路径
            chunk_size (int): 读取缓冲区大小，默认 64KB
            
        Returns:
            str: 文件的 SHA-256 哈希值
            
        Raises:
            Exception: 文件读取失败时抛出异常
        """
        hash_sha256 = hashlib.sha256()
        try:
            # 获取文件大小用于优化小文件处理
            file_size = file_path.stat().st_size
            
            # 对于小文件（<1MB），一次性读取
            if file_size < 1024 * 1024:
                with open(file_path, 'rb') as f:
                    hash_sha256.update(f.read())
            else:
                # 对于大文件，使用优化的块大小分块读取
                with open(file_path, 'rb') as f:
                    while chunk := f.read(chunk_size):
                        hash_sha256.update(chunk)
                        
            return hash_sha256.hexdigest()
        except Exception as e:
            logger.error(f"计算文件哈希失败 {file_path}: {e}")
            raise
    
    def check_duplicate(self, file_hash: str) -> Optional[str]:
        """
        检查是否存在相同哈希值的文件（优化版本）。
        
        使用索引优化查询性能，只返回必要的字段。
        
        Args:
            file_hash (str): 文件哈希值
            
        Returns:
            Optional[str]: 如果存在重复文件，返回原始文件名；否则返回 None
            
        Raises:
            Exception: 数据库查询失败时抛出异常
        """
        try:
            with self.get_session() as session:
                # 只查询需要的字段，提高查询性能
                result = session.query(FileRecord.original_name).filter(
                    FileRecord.hash == file_hash
                ).first()
                return result[0] if result else None
        except Exception as e:
            logger.error(f"检查重复文件失败，哈希: {file_hash[:8]}..., 错误: {e}")
            raise
    
    def add_file_record(self, 
                       original_name: str,
                       source_path: str,
                       file_size: int,
                       file_hash: str,
                       extension: str,
                       created_at: datetime,
                       target_path: str = None,
                       hash_type: str = 'sha256') -> int:
        """Add new file record to database."""
        try:
            with self.get_session() as session:
                record = FileRecord(
                    hash=file_hash,
                    original_name=original_name,
                    source_path=source_path,
                    file_size=file_size,
                    extension=extension,
                    created_at=created_at,
                    target_path=target_path,
                    hash_type=hash_type
                )
                session.add(record)
                session.flush()  # Get the ID without committing
                record_id = record.id
                logger.info(f"Added file record for {original_name}")
                return record_id
        except IntegrityError as e:
            logger.warning(f"Duplicate hash detected for {original_name}: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to add file record for {original_name}: {e}")
            raise
    

    
    def get_statistics(self) -> Dict[str, Any]:
        """Get database statistics."""
        try:
            with self.get_session() as session:
                total_files = session.query(FileRecord).count()
                processed_files = session.query(FileRecord).filter(
                    FileRecord.processed_at.isnot(None)
                ).count()
                
                return {
                    'total_files': total_files,
                    'processed_files': processed_files,
                    'pending_files': total_files - processed_files
                }
        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            raise
    
    def close(self):
        """Close database connections."""
        if self.engine:
            self.engine.dispose()
            logger.info("Database connections closed")

# Global database manager instance
db_manager = DatabaseManager()

def initialize_database():
    """Initialize database and create tables."""
    try:
        db_manager.create_tables()
        logger.info("Database initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        return False

if __name__ == "__main__":
    # Test database connection and create tables
    import coloredlogs
    coloredlogs.install(level='INFO')
    
    if initialize_database():
        stats = db_manager.get_statistics()
        print(f"Database statistics: {stats}")
    else:
        print("Failed to initialize database")