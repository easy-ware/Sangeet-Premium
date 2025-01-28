import os
import platform
import subprocess
import sys
import requests
import stat
from pathlib import Path
from shutil import which

def get_system_info():
    """
    Get detailed system information including OS and architecture.
    Returns:
        tuple: (system, machine, is_64bit)
    """
    system = platform.system().lower()
    machine = platform.machine().lower()
    is_64bit = platform.architecture()[0] == '64bit'
    return system, machine, is_64bit

def install_via_pip():
    """
    Install yt-dlp using pip and return the executable path.
    Returns:
        str: Path to the yt-dlp executable or None if installation fails
    """
    try:
        # Check if pip is available
        if not which('pip') and not which('pip3'):
            return None
            
        print("Installing yt-dlp via pip...")
        
        # Try to upgrade pip first
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--upgrade', 'pip'], 
                      check=True, capture_output=True)
        
        # Install/upgrade yt-dlp
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--upgrade', 'yt-dlp'],
                      check=True, capture_output=True)
        
        # Find the installed executable
        yt_dlp_path = which('yt-dlp')
        if not yt_dlp_path:
            # On Windows, also check for .exe
            yt_dlp_path = which('yt-dlp.exe')
            
        if yt_dlp_path:
            print(f"Successfully installed yt-dlp via pip at: {yt_dlp_path}")
            return yt_dlp_path
            
        return None
    except subprocess.CalledProcessError as e:
        print(f"Pip installation failed: {e}")
        return None
    except Exception as e:
        print(f"Error during pip installation: {e}")
        return None

def setup_ytdlp():
    """
    Set up yt-dlp executable and return its path.
    First tries pip installation, falls back to binary download if needed.
    Returns:
        str: Path to the yt-dlp executable
    """
    try:
        system, machine, is_64bit = get_system_info()
        print(f"Detected system: {system}")
        print(f"Detected machine architecture: {machine}")
        
        # First, try to install via pip
        pip_path = install_via_pip()
        if pip_path:
            return pip_path
            
        print("Pip installation not available or failed, falling back to binary download...")
        
        # Binary download patterns (fallback method)
        download_patterns = {
            "windows": {
                "x86_64": "yt-dlp.exe",
                "i386": "yt-dlp_x86.exe",
            },
            "darwin": {
                "x86_64": "yt-dlp_macos",
                "aarch64": "yt-dlp_macos",
                "legacy": "yt-dlp_macos_legacy"
            },
            "linux": {
                "x86_64": "yt-dlp_linux",
                "aarch64": "yt-dlp_linux_aarch64",
                "armv7l": "yt-dlp_linux_armv7l",
                "armv6l": "yt-dlp_linux_armv7l"
            }
        }
        
        try:
            download_pattern = download_patterns[system][machine]
        except KeyError:
            raise Exception(f"Unsupported system/architecture combination: {system}/{machine}")
            
        print(f"Selected download pattern: {download_pattern}")
        
        # Create system-specific directory for binary method
        res_dir = Path('res') / system / machine
        res_dir.mkdir(parents=True, exist_ok=True)
        
        executable = "yt-dlp.exe" if system == "windows" else "yt-dlp"
        executable_path = res_dir / executable
        
        # Get latest release info
        try:
            api_url = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
            response = requests.get(api_url, timeout=10)
            response.raise_for_status()
            release_data = response.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to fetch release data: {e}")
        
        # Find download URL
        download_url = None
        for asset in release_data['assets']:
            if asset['name'] == download_pattern:
                download_url = asset['browser_download_url']
                print(f"Found matching asset: {asset['name']}")
                break
        
        if not download_url:
            print("\nAvailable files in release:")
            for asset in release_data['assets']:
                print(f"- {asset['name']} ({asset['size'] / 1024 / 1024:.1f} MB)")
            raise Exception(f"No executable found for pattern: {download_pattern}")
        
        print(f"\nDownloading from: {download_url}")
        
        # Download executable
        try:
            response = requests.get(download_url, timeout=30)
            response.raise_for_status()
            with open(executable_path, 'wb') as f:
                f.write(response.content)
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to download executable: {e}")
        
        # Set executable permissions for non-Windows systems
        if system != "windows":
            try:
                executable_path.chmod(executable_path.stat().st_mode | stat.S_IEXEC)
            except OSError as e:
                raise Exception(f"Failed to set executable permissions: {e}")
            
        print(f"Successfully installed to: {executable_path}")
        return str(executable_path)
    
    except Exception as e:
        print(f"Error setting up yt-dlp: {e}")
        return None

if __name__ == "__main__":
    YTDLP_PATH = setup_ytdlp()
    if YTDLP_PATH:
        print(f"\nYT-DLP ready to use at: {YTDLP_PATH}")
