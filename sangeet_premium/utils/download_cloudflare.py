import os
import platform
import requests

def get_cloudflared(base_dir=None):
    """
    Downloads, updates, and returns the path to cloudflared binary.
    Automatically handles system detection and version management.
    
    Args:
        base_dir (str, optional): Directory to store cloudflared. 
                                 Defaults to ./drivers if None
    
    Returns:
        str: Full path to the cloudflared binary
    """
    try:
        # Set default directory if none provided
        if base_dir is None:
            base_dir = os.path.join(os.getcwd(), "drivers")
        
        # Detect system info
        system = platform.system().lower()
        machine = platform.machine().lower()
        
        # Map architectures
        arch_map = {
            'x86_64': 'amd64',
            'aarch64': 'arm64',
            'armv7l': 'arm',
            'i386': '386'
        }
        arch = arch_map.get(machine, machine)
        
        # Set system name
        if system == 'darwin':
            system = 'darwin'
        elif system == 'windows':
            system = 'windows'
        else:
            system = 'linux'
            
        # Setup paths
        platform_dir = os.path.join(base_dir, f"{system}-{arch}")
        binary_name = 'cloudflared.exe' if system == 'windows' else 'cloudflared'
        binary_path = os.path.join(platform_dir, binary_name)
        version_file = os.path.join(platform_dir, 'version.txt')
        
        # Create directory
        os.makedirs(platform_dir, exist_ok=True)
        
        # Get latest release info
        headers = {'Accept': 'application/vnd.github.v3+json'}
        response = requests.get(
            "https://api.github.com/repos/cloudflare/cloudflared/releases/latest",
            headers=headers
        )
        release_data = response.json()
        latest_version = release_data['tag_name'].replace('v', '')
        
        # Check current version
        current_version = None
        if os.path.exists(version_file):
            with open(version_file, 'r') as f:
                current_version = f.read().strip()
        
        # Download if needed
        if current_version != latest_version:
            # Find correct asset
            asset_name = f"cloudflared-{system}-{arch}"
            if system == 'windows':
                asset_name += '.exe'
                
            download_url = None
            for asset in release_data['assets']:
                if asset['name'].lower() == asset_name.lower():
                    download_url = asset['browser_download_url']
                    break
                    
            if not download_url:
                raise Exception(f"No binary found for {system}-{arch}")
            
            # Download binary
            response = requests.get(download_url)
            response.raise_for_status()
            
            # Save binary
            with open(binary_path, 'wb') as f:
                f.write(response.content)
                
            # Make executable on Unix
            if system != 'windows':
                os.chmod(binary_path, 0o755)
                
            # Save version
            with open(version_file, 'w') as f:
                f.write(latest_version)
        
        return binary_path
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return None

# Example usage
if __name__ == "__main__":
    # Get with default directory
    path = get_cloudflared()
    print(f"Cloudflared path: {path}")
    
    # Get with custom directory
    custom_path = get_cloudflared("C:/my_drivers")
    print(f"Cloudflared custom path: {custom_path}")