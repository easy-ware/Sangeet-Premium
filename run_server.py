import sys
import os
import subprocess

def install_colorama():
    """
    Attempt to install colorama library with error handling
    and provide feedback about the installation process.
    """
    try:
        # Check if colorama is already installed
        import colorama
        print("Colorama is already installed.")
        return True
    except ImportError:
        try:
            # Attempt to install colorama using pip
            print("Colorama not found. Attempting to install...")
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'colorama'])
            print("Colorama successfully installed.")
            return True
        except subprocess.CalledProcessError:
            print("Error: Failed to install colorama.")
            return False
        except Exception as e:
            print(f"Unexpected error during installation: {e}")
            return False
install_colorama()
dependencies = [
    "Flask",
    "colorama",
    "python-dotenv",
    "ytmusicapi",
    "ntplib",
    "pytz",
    "yt-dlp",
    "bcrypt",
    "mutagen",
    "requests",
    "pyfiglet",
    "gunicorn",
    "tqdm",
    "termcolor"
]


if sys.platform.startswith("win"):
    dependencies.extend([
        "pywin32==308",
        "winshell==0.6"
    ])

with open(os.path.join(os.getcwd() , "requirements" , "req.txt"), "w") as f:
    f.write("\n".join(dependencies))



from sangeet_premium.utils import venv_create

venv_create.create_env("sangeet-premium-venv" , os.path.join(os.getcwd() , "requirements" , "req.txt"), os.path.join(os.getcwd() , "logs" , "venve-logs") , os.path.join(os.getcwd() , "sangeet_server.py"))
