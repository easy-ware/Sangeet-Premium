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
import tarfile
import struct
import json
from datetime import datetime

# Initialize colorama
init(autoreset=True)

# GitHub API endpoints and repositories
GITHUB_API = {
    'Windows': {
        'repo': 'BtbN/FFmpeg-Builds',
        'api_url': 'https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest'
    },
    'Linux': {
        'repo': 'FFmpeg/FFmpeg',
        'api_url': 'https://api.github.com/repos/FFmpeg/FFmpeg/releases/latest'
    },
    'Darwin': {
        'repo': 'FFmpeg/FFmpeg',
        'api_url': 'https://api.github.com/repos/FFmpeg/FFmpeg/releases/latest'
    }
}

# Required files for each platform
REQUIRED_FILES = {
    'Windows': ['ffmpeg.exe', 'ffprobe.exe', 'ffplay.exe'],
    'Linux': ['ffmpeg', 'ffprobe', 'ffplay'],
    'Darwin': ['ffmpeg', 'ffprobe', 'ffplay']
}

class ColoredLogger:
    def __init__(self):
        self.logger = logging.getLogger('FFmpegDownloader')
        self.logger.setLevel(logging.INFO)
        self.logger.handlers = []
        
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

    def status(self, msg): self.logger._log(100, msg, ())
    def success(self, msg): self.logger._log(101, msg, ())
    def info(self, msg): self.logger.info(msg)
    def error(self, msg): self.logger.error(msg)
    def warning(self, msg): self.logger.warning(msg)

def get_system_info():
    system = platform.system()
    machine = platform.machine().lower()
    
    arch_map = {
        'x86_64': 'x64',
        'amd64': 'x64',
        'i386': 'x86',
        'i686': 'x86',
        'aarch64': 'arm64',
        'arm64': 'arm64'
    }
    
    arch = arch_map.get(machine, machine)
    
    return system, arch

def format_size(size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0

def get_github_release(system, arch, logger):
    headers = {}
    if 'GITHUB_TOKEN' in os.environ:
        headers['Authorization'] = f"token {os.environ['GITHUB_TOKEN']}"
    
    try:
        api_url = GITHUB_API[system]['api_url']
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()
        release_data = response.json()
        
        # Get assets based on system and architecture
        if system == 'Windows':
            asset_pattern = f"ffmpeg-master-latest-win{arch}-gpl.zip"
        elif system == 'Linux':
            asset_pattern = f"ffmpeg-release-{arch}-static.tar.xz"
        else:  # Darwin
            asset_pattern = f"ffmpeg-{arch}-static.zip"
        
        for asset in release_data['assets']:
            if asset_pattern.lower() in asset['name'].lower():
                return {
                    'url': asset['browser_download_url'],
                    'size': asset['size'],
                    'version': release_data['tag_name'],
                    'name': asset['name']
                }
        
        raise Exception(f"No matching release found for {system} {arch}")
        
    except Exception as e:
        logger.error(f"Failed to get release info: {str(e)}")
        return None

def download_with_progress(url, dest_path, logger):
    try:
        headers = {}
        if 'GITHUB_TOKEN' in os.environ:
            headers['Authorization'] = f"token {os.environ['GITHUB_TOKEN']}"
        
        response = requests.get(url, stream=True, headers=headers)
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
                
                elapsed = time.time() - start_time
                if elapsed >= 1:
                    speed = downloaded / (1024 * 1024 * elapsed)  # MB/s
                    pbar.set_postfix({'Speed': f'{speed:.2f} MB/s'}, refresh=True)
        
        return True
    except Exception as e:
        logger.error(f"Download failed: {str(e)}")
        return False

def extract_archive(archive_path, extract_path, logger):
    try:
        logger.status("Extracting files...")
        if archive_path.endswith('.zip'):
            with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                for file in tqdm(zip_ref.namelist(), desc="Extracting"):
                    zip_ref.extract(file, extract_path)
        elif archive_path.endswith(('.tar.gz', '.tar.xz')):
            with tarfile.open(archive_path) as tar_ref:
                for file in tqdm(tar_ref.getmembers(), desc="Extracting"):
                    tar_ref.extract(file, extract_path)
        return True
    except Exception as e:
        logger.error(f"Extraction failed: {str(e)}")
        return False

def find_ffmpeg_files(directory, system):
    required_files = REQUIRED_FILES[system]
    found_files = {}
    
    for root, _, files in os.walk(directory):
        for file in files:
            if file in required_files or file.lower() in [f.lower() for f in required_files]:
                found_files[file] = os.path.join(root, file)
                
    return found_files

def install_ffmpeg(system, arch, install_dir, logger):
    # Create installation directory
    os.makedirs(install_dir, exist_ok=True)
    
    # Get latest release information
    release_info = get_github_release(system, arch, logger)
    if not release_info:
        return False
    
    logger.status(f"Found FFmpeg version: {release_info['version']}")
    
    # Download archive
    archive_path = os.path.join(install_dir, release_info['name'])
    if not download_with_progress(release_info['url'], archive_path, logger):
        return False
    
    # Extract archive
    if not extract_archive(archive_path, install_dir, logger):
        return False
    
    # Find and move FFmpeg files
    found_files = find_ffmpeg_files(install_dir, system)
    
    # Move files to final location
    for file_name, file_path in found_files.items():
        target_path = os.path.join(install_dir, file_name)
        if file_path != target_path:
            shutil.move(file_path, target_path)
    
    # Clean up temporary files
    logger.status("Cleaning up...")
    try:
        os.remove(archive_path)
        # Remove empty directories
        for root, dirs, files in os.walk(install_dir, topdown=False):
            for name in dirs:
                try:
                    dir_path = os.path.join(root, name)
                    if not os.listdir(dir_path):
                        os.rmdir(dir_path)
                except:
                    pass
    except Exception as e:
        logger.warning(f"Cleanup failed: {str(e)}")
    
    # Verify installation
    missing_files = [f for f in REQUIRED_FILES[system] 
                    if not os.path.exists(os.path.join(install_dir, f))]
    
    if missing_files:
        logger.error(f"Missing files: {', '.join(missing_files)}")
        return False
    
    # Set executable permissions on Unix-like systems
    if system != 'Windows':
        for file_name in REQUIRED_FILES[system]:
            file_path = os.path.join(install_dir, file_name)
            if os.path.exists(file_path):
                os.chmod(file_path, 0o755)
    
    return True

def main():
    logger = ColoredLogger()
    
    # Get system information
    system, arch = get_system_info()
    logger.status(f"Detected system: {system} ({arch})")
    
    # Set installation directory
    install_dir = os.path.join(os.getcwd(), 'ffmpeg', 'bin')
    logger.status(f"Installation directory: {install_dir}")
    
    # Check if system is supported
    if system not in GITHUB_API:
        logger.error(f"Unsupported system: {system}")
        return
    
    # Install FFmpeg
    if install_ffmpeg(system, arch, install_dir, logger):
        logger.success("FFmpeg installation completed successfully!")
        logger.info(f"FFmpeg binaries location: {install_dir}")
        
        # Add usage instructions
        if system == 'Windows':
            logger.info("Add the following path to your system's PATH environment variable:")
            logger.info(f"{install_dir}")
        else:
            logger.info("Add the following line to your ~/.bashrc or ~/.zshrc:")
            logger.info(f"export PATH=\"{install_dir}:$PATH\"")
    else:
        logger.error("FFmpeg installation failed!")

if __name__ == "__main__":
    main()
