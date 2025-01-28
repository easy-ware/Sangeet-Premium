import os
import platform
import requests
import stat
from pathlib import Path

def get_system_info():
    """
    Get detailed system information including OS and architecture.
    Returns:
        tuple: (system, machine, is_64bit)
    """
    system = platform.system().lower()
    machine = platform.machine().lower()
    is_64bit = platform.architecture()[0] == '64bit'
    
    # Handle Windows on ARM
    if system == "windows" and "arm" in machine:
        return "windows", "arm64" if is_64bit else "arm", is_64bit
    
    # Normalize architecture names
    if machine in ['x86_64', 'amd64']:
        machine = 'x86_64'
    elif machine in ['i386', 'i686', 'x86']:
        machine = 'i386'
    elif machine in ['aarch64', 'arm64']:
        machine = 'aarch64'
    elif 'armv' in machine:
        machine = 'armv7l' if machine >= 'armv7' else 'armv6l'
        
    return system, machine, is_64bit

def setup_ytdlp():
    """
    Set up yt-dlp executable and return its path.
    Creates system-specific subdirectories in res folder.
    Returns:
        str: Path to the yt-dlp executable
    """
    try:
        system, machine, is_64bit = get_system_info()
        
        print(f"Detected system: {system}")
        print(f"Detected machine architecture: {machine}")
        print(f"Is 64-bit: {is_64bit}")
        
        # Updated mapping based on actual GitHub release files
        download_patterns = {
            "windows": {
                "x86_64": "yt-dlp.exe",
                "i386": "yt-dlp_x86.exe",
                # Note: Windows ARM not available in current release
            },
            "darwin": {
                "x86_64": "yt-dlp_macos",
                "aarch64": "yt-dlp_macos",  # Same binary for both architectures
                "legacy": "yt-dlp_macos_legacy"  # For older macOS versions
            },
            "linux": {
                "x86_64": "yt-dlp_linux",
                "aarch64": "yt-dlp_linux_aarch64",
                "armv7l": "yt-dlp_linux_armv7l",
                "armv6l": "yt-dlp_linux_armv7l"  # Using armv7l for armv6l
            }
        }
        
        # Get the appropriate download pattern
        try:
            download_pattern = download_patterns[system][machine]
        except KeyError:
            raise Exception(f"Unsupported system/architecture combination: {system}/{machine}")
            
        print(f"Selected download pattern: {download_pattern}")
        
        # Create system-specific directory
        res_dir = Path('res') / system / machine
        res_dir.mkdir(parents=True, exist_ok=True)
        
        # Set executable name
        executable = "yt-dlp.exe" if system == "windows" else "yt-dlp"
        executable_path = res_dir / executable
        
        # Get latest release info with error handling
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
        
        # Download executable with error handling
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
