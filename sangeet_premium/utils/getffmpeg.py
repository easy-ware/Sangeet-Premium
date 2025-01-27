import os
import sys
import platform
import requests
import logging
import subprocess
from pathlib import Path
from colorama import init, Fore, Style, Back
from tqdm import tqdm
import time
import shutil
import zipfile
import struct

# Initialize colorama with autoreset
init(autoreset=True)

# FFmpeg URLs for different platforms and architectures
FFMPEG_URLS = {
    'Windows': {
        '64bit': 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip',
        '32bit': 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win32-gpl.zip'
    }
}

# Required executables
REQUIRED_EXES = ['ffmpeg.exe', 'ffplay.exe', 'ffprobe.exe']

# Directory setup
FFMPEG_DIR = os.path.join(os.getcwd(), 'ffmpeg', 'bin')

class ColoredLogger:
    def __init__(self):
        self.logger = logging.getLogger('FFmpegDownloader')
        self.logger.setLevel(logging.INFO)
        
        # Remove existing handlers
        self.logger.handlers = []
        
        # Console handler with custom formatter
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        class ColoredFormatter(logging.Formatter):
            formats = {
                logging.DEBUG: Fore.CYAN + '%(asctime)s - %(message)s' + Style.RESET_ALL,
                logging.INFO: Fore.GREEN + '%(asctime)s - %(message)s' + Style.RESET_ALL,
                logging.WARNING: Fore.YELLOW + '%(asctime)s - WARNING - %(message)s' + Style.RESET_ALL,
                logging.ERROR: Fore.RED + '%(asctime)s - ERROR - %(message)s' + Style.RESET_ALL,
                'STATUS': Fore.BLUE + Back.WHITE + '%(asctime)s - STATUS - %(message)s' + Style.RESET_ALL,
                'SUCCESS': Fore.BLACK + Back.GREEN + '%(asctime)s - SUCCESS - %(message)s' + Style.RESET_ALL
            }

            def format(self, record):
                format_orig = self.formats.get(record.levelno, self.formats['STATUS'])
                formatter = logging.Formatter(format_orig, datefmt='%H:%M:%S')
                return formatter.format(record)

        console_handler.setFormatter(ColoredFormatter())
        self.logger.addHandler(console_handler)

    def status(self, msg):
        self.logger._log(100, msg, ())

    def success(self, msg):
        self.logger._log(101, msg, ())

    def info(self, msg):
        self.logger.info(msg)

    def error(self, msg):
        self.logger.error(msg)

    def warning(self, msg):
        self.logger.warning(msg)

def get_system_info():
    system = platform.system()
    machine = platform.machine().lower()
    
    # Determine architecture
    is_64bits = struct.calcsize('P') * 8 == 64
    arch = '64bit' if is_64bits else '32bit'
    
    # Map architecture names
    arch_map = {
        'amd64': '64bit',
        'x86_64': '64bit',
        'i386': '32bit',
        'x86': '32bit',
        'arm64': '64bit',
        'aarch64': '64bit'
    }
    
    if machine in arch_map:
        arch = arch_map[machine]
    
    return system, arch

def format_size(size):
    units = ['B', 'KB', 'MB', 'GB']
    unit_index = 0
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    return f"{size:.2f} {units[unit_index]}"

def download_with_progress(url, dest_path, logger):
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        block_size = 8192
        
        logger.status(f"Starting download - Total size: {format_size(total_size)}")
        
        with open(dest_path, 'wb') as file, \
             tqdm(
                desc=f"{Fore.BLUE}Downloading",
                total=total_size,
                unit='iB',
                unit_scale=True,
                unit_divisor=1024,
                bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}] {rate_fmt}',
                colour='blue'
             ) as pbar:
            
            start_time = time.time()
            downloaded = 0
            
            for chunk in response.iter_content(chunk_size=block_size):
                size = file.write(chunk)
                pbar.update(size)
                downloaded += size
                
                # Calculate and show speed every second
                elapsed = time.time() - start_time
                if elapsed >= 1:
                    speed = downloaded / (1024 * 1024 * elapsed)  # MB/s
                    pbar.set_postfix({'Speed': f'{speed:.2f} MB/s'}, refresh=True)
        
        return True
    except Exception as e:
        logger.error(f"Download failed: {str(e)}")
        return False

def extract_ffmpeg(zip_path, logger):
    try:
        logger.status("Starting extraction process...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # Find all exe files in the zip
            exe_files = [f for f in zip_ref.namelist() if f.endswith('.exe') and '/bin/' in f]
            
            with tqdm(total=len(REQUIRED_EXES), desc=f"{Fore.BLUE}Extracting", colour='blue') as pbar:
                for zip_path in exe_files:
                    exe_name = os.path.basename(zip_path)
                    if exe_name in REQUIRED_EXES:
                        logger.info(f"Extracting {exe_name}")
                        source = zip_ref.read(zip_path)
                        target_path = os.path.join(FFMPEG_DIR, exe_name)
                        with open(target_path, 'wb') as f:
                            f.write(source)
                        pbar.update(1)
        return True
    except Exception as e:
        logger.error(f"Extraction failed: {str(e)}")
        return False

def main():
    logger = ColoredLogger()
    
    # Get system information
    system, arch = get_system_info()
    logger.status(f"System detected: {system} ({arch})")
    
    # Check if system is supported
    if system != 'Windows':
        logger.error("This script is for Windows only!")
        return
    
    if arch not in FFMPEG_URLS[system]:
        logger.error(f"Unsupported architecture: {arch}")
        return
    
    # Create directory
    Path(FFMPEG_DIR).mkdir(parents=True, exist_ok=True)
    logger.status(f"Using directory: {FFMPEG_DIR}")
    
    # Check existing files
    existing_files = [exe for exe in REQUIRED_EXES if os.path.exists(os.path.join(FFMPEG_DIR, exe))]
    if existing_files:
        logger.info(f"Found existing files: {', '.join(existing_files)}")
        if len(existing_files) == len(REQUIRED_EXES):
            logger.success("All required files already exist!")
            return
    
    # Download FFmpeg
    zip_path = os.path.join(FFMPEG_DIR, 'ffmpeg.zip')
    url = FFMPEG_URLS[system][arch]
    
    logger.status(f"Downloading FFmpeg for {system} {arch}")
    if not download_with_progress(url, zip_path, logger):
        return
    
    # Extract files
    if not extract_ffmpeg(zip_path, logger):
        return
    
    # Clean up
    try:
        os.remove(zip_path)
        logger.info("Cleaned up temporary files")
    except Exception as e:
        logger.warning(f"Could not remove temporary file: {str(e)}")
    
    # Verify installation
    missing_files = [exe for exe in REQUIRED_EXES if not os.path.exists(os.path.join(FFMPEG_DIR, exe))]
    if missing_files:
        logger.error(f"Missing files after installation: {', '.join(missing_files)}")
    else:
        logger.success("FFmpeg installation completed successfully!")
        logger.info(f"FFmpeg binaries location: {FFMPEG_DIR}")

if __name__ == "__main__":
    main()
