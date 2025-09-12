#!/usr/bin/env python3
"""
Setup script for Image Converter application.
This script creates a virtual environment and installs required dependencies.
"""

import subprocess
import sys
import os
from pathlib import Path

def run_command(command, cwd=None):
    """Run a command and return the result."""
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            check=True, 
            capture_output=True, 
            text=True,
            cwd=cwd
        )
        print(f"✓ {command}")
        return result
    except subprocess.CalledProcessError as e:
        print(f"✗ Error running: {command}")
        print(f"Error: {e.stderr}")
        sys.exit(1)

def setup_environment():
    """Set up the virtual environment and install dependencies."""
    project_dir = Path(__file__).parent
    venv_dir = project_dir / "venv"
    
    print("Setting up Image Converter environment...")
    
    # Check Python version
    if sys.version_info < (3, 12):
        print("Error: Python 3.12+ is required")
        sys.exit(1)
    
    print(f"✓ Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro} detected")
    
    # Create virtual environment
    if not venv_dir.exists():
        print("Creating virtual environment...")
        run_command(f"python -m venv {venv_dir}")
    else:
        print("✓ Virtual environment already exists")
    
    # Activate virtual environment and install dependencies
    if os.name == 'nt':  # Windows
        activate_script = venv_dir / "Scripts" / "activate.bat"
        pip_path = venv_dir / "Scripts" / "pip.exe"
    else:  # Unix/Linux/macOS
        activate_script = venv_dir / "bin" / "activate"
        pip_path = venv_dir / "bin" / "pip"
    
    # Install dependencies
    print("Installing dependencies...")
    run_command(f"{pip_path} install --upgrade pip")
    run_command(f"{pip_path} install -r requirements.txt")
    
    print("\n✓ Setup complete!")
    print(f"\nTo activate the virtual environment:")
    if os.name == 'nt':
        print(f"  {activate_script}")
    else:
        print(f"  source {activate_script}")
    
    print("\nTo run the application:")
    print("  python main.py")

if __name__ == "__main__":
    setup_environment()