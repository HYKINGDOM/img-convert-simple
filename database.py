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

class ImageMetadata(Base):
    """SQLAlchemy model for image metadata storage."""
    __tablename__ = 'image_metadata'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(255), nullable=False)
    original_path = Column(Text, nullable=False)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    format = Column(String(10), nullable=True)
    file_size = Column(BigInteger, nullable=False)
    file_hash = Column(String(64), nullable=False, unique=True)  # SHA-256 hash
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    processed_at = Column(DateTime, nullable=True)
    moved_to_path = Column(String(500), nullable=True)
    is_duplicate = Column(Boolean, nullable=False, default=False)
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_file_hash', 'file_hash'),
        Index('idx_filename', 'filename'),
        Index('idx_created_at', 'created_at'),
        UniqueConstraint('file_hash', name='uq_image_hash'),
    )
    
    def __repr__(self):
        return f"<ImageMetadata(filename='{self.filename}', hash='{self.file_hash[:8]}...')>"

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
    
    def calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA-256 hash of a file."""
        hash_sha256 = hashlib.sha256()
        try:
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        except Exception as e:
            logger.error(f"Failed to calculate hash for {file_path}: {e}")
            raise
    
    def check_duplicate(self, file_hash: str) -> Optional[str]:
        """Check if an image with the same hash already exists."""
        try:
            with self.get_session() as session:
                existing = session.query(ImageMetadata).filter(
                    ImageMetadata.file_hash == file_hash
                ).first()
                return existing.filename if existing else None
        except Exception as e:
            logger.error(f"Failed to check duplicate for hash {file_hash}: {e}")
            raise
    
    def add_image_metadata(self, 
                          filename: str,
                          original_path: str,
                          file_size: int,
                          file_hash: str) -> int:
        """Add new image metadata to database."""
        try:
            with self.get_session() as session:
                metadata = ImageMetadata(
                    filename=filename,
                    original_path=original_path,
                    file_size=file_size,
                    file_hash=file_hash
                )
                session.add(metadata)
                session.flush()  # Get the ID without committing
                metadata_id = metadata.id
                logger.info(f"Added image metadata for {filename}")
                return metadata_id
        except IntegrityError as e:
            logger.warning(f"Duplicate hash detected for {filename}: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to add image metadata for {filename}: {e}")
            raise
    

    
    def get_statistics(self) -> Dict[str, Any]:
        """Get database statistics."""
        try:
            with self.get_session() as session:
                total_images = session.query(ImageMetadata).count()
                processed_images = session.query(ImageMetadata).filter(
                    ImageMetadata.processed_at.isnot(None)
                ).count()
                duplicate_images = session.query(ImageMetadata).filter(
                    ImageMetadata.is_duplicate == True
                ).count()
                
                return {
                    'total_images': total_images,
                    'processed_images': processed_images,
                    'duplicate_images': duplicate_images,
                    'pending_images': total_images - processed_images
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