# Image Converter with Monitoring and Duplicate Detection

A Python 3.12+ solution that monitors folders for new image files, converts them to specified formats, and prevents duplicate processing using PostgreSQL database with hash-based duplicate detection.

## Features

- **Real-time File Monitoring**: Monitors specified folders for new image files using watchdog
- **Image Format Conversion**: Converts images between multiple formats (JPEG, PNG, WebP, BMP, TIFF, GIF, SVG)
- **Duplicate Detection**: Uses SHA-256 hash comparison to detect and automatically delete duplicate images
- **Database Integration**: PostgreSQL database stores image metadata and hash values
- **Thread-Safe Processing**: Concurrent processing with configurable worker threads
- **Connection Pooling**: Efficient database connection management
- **Comprehensive Logging**: Detailed logging with colored output
- **Error Handling**: Robust error handling and recovery mechanisms

## Supported Image Formats

**Input formats**: JPG, JPEG, PNG, GIF, WebP, BMP, SVG, TIFF
**Output formats**: JPG, PNG, WebP, BMP, TIFF, GIF

## Requirements

- Python 3.12 or higher
- PostgreSQL database
- Virtual environment (recommended)

## Installation

### 1. Clone or Download

```bash
# Navigate to your project directory
cd /path/to/img-convert-simple
```

### 2. Setup Virtual Environment

```bash
# Run the setup script (recommended)
python setup.py

# OR manually create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Database Setup

The application will automatically create the required database tables on first run. Ensure your PostgreSQL database is accessible with the provided credentials:

- **Host**: 10.0.201.34
- **Port**: 5432
- **Database**: user_tZGjBb
- **Username**: user_tZGjBb
- **Password**: password_fajJed

### 4. Configuration

Copy the example environment file and customize as needed:

```bash
cp .env.example .env
```

Edit `.env` file to match your requirements.

## Usage

### Basic Usage

```bash
# Activate virtual environment first
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/macOS

# Run with default settings (monitors current directory)
python main.py

# Monitor specific directory
python main.py --watch-path "C:\Images\Input"

# Convert to PNG format
python main.py --format png --watch-path "./input_images"

# Multiple watch paths
python main.py -w "./folder1" -w "./folder2" -o "./output"
```

### Command Line Options

```bash
python main.py [OPTIONS]

Options:
  -w, --watch-path PATH     Directory to monitor (can be used multiple times)
  -o, --output-dir PATH     Output directory for converted images
  -f, --format FORMAT       Target format: jpg, png, webp, bmp, tiff
  -q, --quality INT         JPEG quality (1-100, default: 85)
  --no-delete              Keep original files after conversion
  --no-scan                Skip scanning existing files on startup
  --workers INT            Number of worker threads (default: 4)
  --log-level LEVEL        Logging level: DEBUG, INFO, WARNING, ERROR
  -h, --help               Show help message
```

### Examples

```bash
# High-quality JPEG conversion with original file preservation
python main.py -w "./photos" -f jpg -q 95 --no-delete

# WebP conversion with custom output directory
python main.py -w "./input" -o "./webp_output" -f webp

# Debug mode with verbose logging
python main.py --log-level DEBUG -w "./test_images"

# Production setup with multiple workers
python main.py -w "./production_input" --workers 8 -f png
```

## Database Schema

The application creates the following table structure:

```sql
CREATE TABLE image_metadata (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    original_path TEXT NOT NULL,
    file_size BIGINT NOT NULL,
    file_hash VARCHAR(64) UNIQUE NOT NULL,  -- SHA-256 hash
    image_width INTEGER,
    image_height INTEGER,
    image_format VARCHAR(10),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP,
    output_path TEXT,
    is_duplicate BOOLEAN DEFAULT FALSE
);

-- Indexes for performance
CREATE INDEX idx_file_hash ON image_metadata(file_hash);
CREATE INDEX idx_filename ON image_metadata(filename);
CREATE INDEX idx_created_at ON image_metadata(created_at);
```

## How It Works

1. **File Monitoring**: The application uses `watchdog` to monitor specified directories for new image files
2. **Hash Calculation**: When a new file is detected, it calculates a SHA-256 hash of the file content
3. **Duplicate Check**: The hash is compared against existing database records
4. **Processing**: If not a duplicate:
   - Image metadata is stored in PostgreSQL
   - Image is converted to the target format
   - Original file is deleted (if configured)
   - Database is updated with processing information
5. **Duplicate Handling**: If duplicate detected, the file is automatically deleted

## Configuration Options

### Environment Variables (.env file)

```env
# Database
DATABASE_URL=postgresql://user:pass@host:port/dbname

# Application
WATCH_PATHS=./input1,./input2
OUTPUT_DIR=./converted_images
TARGET_FORMAT=jpg
IMAGE_QUALITY=85
DELETE_ORIGINALS=true
SCAN_EXISTING=true
MAX_WORKERS=4

# Logging
LOG_LEVEL=INFO
STATS_INTERVAL=60
```

### Application Settings

- **watch_paths**: List of directories to monitor
- **output_dir**: Directory for converted images
- **target_format**: Default conversion format
- **quality**: JPEG quality (1-100)
- **delete_originals**: Whether to delete source files
- **scan_existing**: Scan existing files on startup
- **max_workers**: Number of processing threads

## Logging

The application provides comprehensive logging with different levels:

- **DEBUG**: Detailed processing information
- **INFO**: General application flow and statistics
- **WARNING**: Non-critical issues (duplicates, etc.)
- **ERROR**: Processing errors and failures

Logs include:
- File processing status
- Duplicate detection results
- Database operations
- Performance statistics
- Error details

## Performance Considerations

- **Thread Pool**: Configurable number of worker threads for concurrent processing
- **Connection Pooling**: Database connections are pooled for efficiency
- **File Readiness**: Files are checked for completion before processing
- **Memory Management**: Images are processed in streaming mode when possible
- **Batch Operations**: Database operations are optimized for batch processing

## Error Handling

- **Database Errors**: Automatic retry and connection recovery
- **File System Errors**: Graceful handling of locked or inaccessible files
- **Image Processing Errors**: Detailed error logging with file preservation
- **Network Issues**: Connection timeout and retry mechanisms

## Monitoring and Statistics

The application provides real-time statistics:

```
Statistics - Runtime: 120.5s, Processed: 45, Duplicates: 3, Errors: 1, DB Total: 150
```

- **Runtime**: Application uptime
- **Processed**: Successfully converted images
- **Duplicates**: Detected and removed duplicates
- **Errors**: Processing failures
- **DB Total**: Total images in database

## Troubleshooting

### Common Issues

1. **Database Connection Failed**
   ```
   ERROR - Failed to initialize database engine
   ```
   - Check database credentials and network connectivity
   - Verify PostgreSQL service is running
   - Test connection manually

2. **Permission Errors**
   ```
   ERROR - Failed to delete original file: Permission denied
   ```
   - Check file permissions
   - Ensure application has write access to directories
   - Run with appropriate privileges

3. **Image Processing Errors**
   ```
   ERROR - Failed to convert image: Unsupported format
   ```
   - Verify input file is a valid image
   - Check if format is supported
   - Ensure file is not corrupted

### Debug Mode

Run with debug logging for detailed information:

```bash
python main.py --log-level DEBUG
```

### Database Inspection

Connect to PostgreSQL to inspect data:

```sql
-- Check image statistics
SELECT 
    COUNT(*) as total_images,
    COUNT(CASE WHEN processed_at IS NOT NULL THEN 1 END) as processed,
    COUNT(CASE WHEN is_duplicate THEN 1 END) as duplicates
FROM image_metadata;

-- View recent images
SELECT filename, image_format, file_size, created_at, processed_at
FROM image_metadata
ORDER BY created_at DESC
LIMIT 10;
```

## Development

### Project Structure

```
img-convert-simple/
├── main.py              # Main application entry point
├── database.py          # Database operations and models
├── image_processor.py   # Image conversion and processing
├── file_monitor.py      # File system monitoring
├── setup.py            # Environment setup script
├── requirements.txt    # Python dependencies
├── .env.example       # Environment configuration template
└── README.md          # This file
```

### Testing

Test individual components:

```bash
# Test database connection
python database.py

# Test image processor
python image_processor.py

# Test file monitor
python file_monitor.py
```

### Contributing

1. Follow PEP 8 style guidelines
2. Add comprehensive logging
3. Include error handling
4. Update documentation
5. Test thoroughly

## License

This project is provided as-is for educational and development purposes.

## Support

For issues and questions:
1. Check the troubleshooting section
2. Enable debug logging
3. Review application logs
4. Verify database connectivity