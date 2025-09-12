#!/usr/bin/env python3
"""
Demo script for Image Converter application.
Shows how to set up and run the application with different configurations.
"""

import os
import sys
from pathlib import Path
import tempfile
import shutil
from PIL import Image
import coloredlogs

# Setup logging
coloredlogs.install(level='INFO')

def create_sample_images(directory: Path, count: int = 5):
    """Create sample images for testing."""
    directory.mkdir(parents=True, exist_ok=True)
    
    formats = ['JPEG', 'PNG', 'BMP']
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (255, 0, 255)]
    
    for i in range(count):
        # Create a simple colored image
        img = Image.new('RGB', (100, 100), colors[i % len(colors)])
        
        # Save in different formats
        format_name = formats[i % len(formats)]
        extension = format_name.lower() if format_name != 'JPEG' else 'jpg'
        
        filename = directory / f"sample_{i+1}.{extension}"
        img.save(filename, format=format_name)
        
        print(f"Created sample image: {filename}")

def demo_local_setup():
    """Demonstrate local setup without database."""
    print("\n=== Image Converter Demo (Local Setup) ===")
    print("This demo shows the application structure and components.")
    print("Note: Database connection will fail as the server is not accessible.")
    
    # Create temporary directories
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        input_dir = temp_path / "input_images"
        output_dir = temp_path / "output_images"
        
        print(f"\nUsing temporary directory: {temp_path}")
        
        # Create sample images
        print("\nCreating sample images...")
        create_sample_images(input_dir)
        
        # Show directory structure
        print(f"\nInput directory contents:")
        for file in input_dir.iterdir():
            if file.is_file():
                print(f"  - {file.name} ({file.stat().st_size} bytes)")
        
        # Demonstrate image processor
        print("\n=== Testing Image Processor ===")
        try:
            from image_processor import ImageProcessor
            
            processor = ImageProcessor(quality=85)
            
            # Test image info extraction
            for img_file in input_dir.glob("*.jpg"):
                info = processor.get_image_info(img_file)
                print(f"Image info for {img_file.name}: {info}")
                break
            
            # Test conversion
            output_dir.mkdir(exist_ok=True)
            test_file = next(input_dir.glob("*"), None)
            if test_file:
                output_file = output_dir / f"{test_file.stem}_converted.png"
                success = processor.convert_image(test_file, output_file, 'png')
                print(f"Conversion test: {'SUCCESS' if success else 'FAILED'}")
                
                if success:
                    print(f"Converted: {test_file.name} -> {output_file.name}")
        
        except Exception as e:
            print(f"Image processor test failed: {e}")
        
        # Demonstrate file monitor (briefly)
        print("\n=== Testing File Monitor ===")
        try:
            from file_monitor import FileMonitor
            from image_processor import SUPPORTED_EXTENSIONS
            
            def test_callback(file_info):
                print(f"Monitor detected: {file_info['path'].name}")
            
            monitor = FileMonitor(SUPPORTED_EXTENSIONS, test_callback)
            monitor.add_watch_path(str(input_dir))
            
            # Scan existing files
            monitor.scan_existing_files(str(input_dir))
            
            status = monitor.get_status()
            print(f"Monitor status: {status}")
            
        except Exception as e:
            print(f"File monitor test failed: {e}")
        
        print("\n=== Demo Complete ===")
        print("\nTo run with a real database:")
        print("1. Set up a local PostgreSQL database")
        print("2. Update the DATABASE_URL in database.py")
        print("3. Run: python main.py --watch-path ./input_images")
        
        input("\nPress Enter to continue...")

def show_usage_examples():
    """Show usage examples."""
    print("\n=== Usage Examples ===")
    
    examples = [
        {
            'title': 'Basic Usage',
            'command': 'python main.py',
            'description': 'Monitor current directory, convert to JPG'
        },
        {
            'title': 'Specific Directory',
            'command': 'python main.py --watch-path "C:\\Images\\Input"',
            'description': 'Monitor specific directory'
        },
        {
            'title': 'PNG Conversion',
            'command': 'python main.py --format png --output-dir "./png_output"',
            'description': 'Convert all images to PNG format'
        },
        {
            'title': 'High Quality JPEG',
            'command': 'python main.py --format jpg --quality 95 --no-delete',
            'description': 'High quality JPEG, keep originals'
        },
        {
            'title': 'Multiple Directories',
            'command': 'python main.py -w "./dir1" -w "./dir2" -o "./output"',
            'description': 'Monitor multiple directories'
        },
        {
            'title': 'Debug Mode',
            'command': 'python main.py --log-level DEBUG',
            'description': 'Run with verbose logging'
        }
    ]
    
    for i, example in enumerate(examples, 1):
        print(f"\n{i}. {example['title']}")
        print(f"   Command: {example['command']}")
        print(f"   Description: {example['description']}")

def show_project_structure():
    """Show project structure and files."""
    print("\n=== Project Structure ===")
    
    current_dir = Path('.')
    
    files = [
        ('main.py', 'Main application entry point'),
        ('database.py', 'Database operations and models'),
        ('image_processor.py', 'Image conversion and processing'),
        ('file_monitor.py', 'File system monitoring'),
        ('setup.py', 'Environment setup script'),
        ('requirements.txt', 'Python dependencies'),
        ('.env.example', 'Environment configuration template'),
        ('README.md', 'Documentation'),
        ('demo.py', 'This demo script')
    ]
    
    print("\nProject Files:")
    for filename, description in files:
        file_path = current_dir / filename
        status = "✓" if file_path.exists() else "✗"
        size = f"({file_path.stat().st_size} bytes)" if file_path.exists() else ""
        print(f"  {status} {filename:<20} - {description} {size}")
    
    # Check virtual environment
    venv_path = current_dir / "venv"
    venv_status = "✓" if venv_path.exists() else "✗"
    print(f"\nEnvironment:")
    print(f"  {venv_status} Virtual Environment (venv/)")
    
    # Check dependencies
    try:
        import PIL
        import watchdog
        import sqlalchemy
        import psycopg2
        print(f"  ✓ All dependencies installed")
    except ImportError as e:
        print(f"  ✗ Missing dependency: {e}")

def main():
    """Main demo function."""
    print("Image Converter Application Demo")
    print("=" * 40)
    
    while True:
        print("\nSelect an option:")
        print("1. Show project structure")
        print("2. Show usage examples")
        print("3. Run local demo (no database)")
        print("4. Exit")
        
        choice = input("\nEnter choice (1-4): ").strip()
        
        if choice == '1':
            show_project_structure()
        elif choice == '2':
            show_usage_examples()
        elif choice == '3':
            demo_local_setup()
        elif choice == '4':
            print("\nGoodbye!")
            break
        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    main()