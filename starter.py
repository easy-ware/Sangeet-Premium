import requests
import time
import subprocess
import signal
import os
import sys
import logging
import platform
from datetime import datetime
import threading
import shlex

# Setup logging
try:
    log_path = '/tmp/server_monitor.log'
    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    # Add a console handler as well for immediate feedback
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    logging.getLogger('').addHandler(console)
except Exception as e:
    print(f"Failed to set up logging: {e}")
    sys.exit(1)

# Configuration
ENDPOINT_URL = "http://localhost/health"  # Health check endpoint
CHECK_INTERVAL = 5  # Seconds between checks
SERVER_PORT = 80
SERVER_SCRIPT_PATH = os.path.join(os.getcwd(), "run_server.py")
SERVER_START_COMMAND = f"python3 {SERVER_SCRIPT_PATH}"
KILL_FILE = "kill.txt"  # File that signals the script to terminate
WORKING_DIR = os.getcwd()  # Remember the current working directory

def is_server_running():
    """Check if the server is running by making a request to the health endpoint"""
    try:
        response = requests.get(ENDPOINT_URL, timeout=3)
        if response.status_code == 200:
            logging.info(f"Server health check successful: {response.text[:50]}")
            return True
        else:
            logging.warning(f"Server returned status code {response.status_code}")
            return False
    except requests.RequestException as e:
        logging.warning(f"Server health check failed: {e}")
        return False
    except Exception as e:
        logging.error(f"Unexpected error during health check: {e}")
        return False

def kill_processes_on_port():
    """Kill all processes running on the configured port (cross-platform)"""
    try:
        system = platform.system().lower()
        
        if system == "linux" or system == "darwin":  # Linux or macOS
            logging.info(f"Killing processes on port {SERVER_PORT} (Linux/macOS)")
            # First try with fuser which is more direct
            try:
                subprocess.run(f"fuser -k {SERVER_PORT}/tcp", shell=True)
                logging.info("Used fuser to kill processes")
            except Exception as e:
                logging.warning(f"fuser command failed: {e}")
            
            # Then try with lsof as backup
            try:
                # Find process IDs using the port
                cmd = f"lsof -i :{SERVER_PORT} -t"
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                
                if result.returncode == 0 and result.stdout:
                    pids = result.stdout.strip().split('\n')
                    logging.info(f"Found processes using port {SERVER_PORT}: {pids}")
                    
                    # Kill each process
                    for pid in pids:
                        try:
                            kill_cmd = f"kill -9 {pid}"
                            subprocess.run(kill_cmd, shell=True, check=True)
                            logging.info(f"Killed process {pid}")
                        except subprocess.SubprocessError as e:
                            logging.error(f"Failed to kill process {pid}: {e}")
                else:
                    logging.info(f"No processes found using port {SERVER_PORT}")
            except Exception as e:
                logging.error(f"lsof command failed: {e}")
                
        elif system == "windows":
            # Windows version
            logging.info(f"Killing processes on port {SERVER_PORT} (Windows)")
            cmd = f"for /f \"tokens=5\" %a in ('netstat -aon ^| findstr :{SERVER_PORT}') do taskkill /F /PID %a"
            subprocess.run(cmd, shell=True)
        else:
            logging.warning(f"Unsupported platform: {system}")
            
    except Exception as e:
        logging.error(f"Error killing processes on port {SERVER_PORT}: {e}")

def start_server():
    """Start the server using the configured command"""
    try:
        # Verify script exists
        if not os.path.exists(SERVER_SCRIPT_PATH):
            logging.error(f"Server script not found at {SERVER_SCRIPT_PATH}")
            return False
            
        # CD to the working directory first
        os.chdir(WORKING_DIR)
        logging.info(f"Changed to working directory: {WORKING_DIR}")
        
        # Build the command with nohup to keep it running
        if platform.system().lower() == "windows":
            # For Windows, use start command
            command = f"start /b {SERVER_START_COMMAND}"
        else:
            # For Linux/macOS use nohup
            command = f"nohup {SERVER_START_COMMAND} > /tmp/server.out 2> /tmp/server.err &"
        
        logging.info(f"Starting server with command: {command}")
        
        # Run the command
        subprocess.run(command, shell=True, check=True)
        
        # Give the server a moment to start
        time.sleep(2)
        
        # Verify it's actually running
        for i in range(3):  # Try a few times
            if is_server_running():
                logging.info("Server started successfully!")
                return True
            logging.info(f"Waiting for server to start (attempt {i+1}/3)...")
            time.sleep(2)
        
        logging.warning("Server might not have started properly after 3 checks")
        return False
        
    except subprocess.SubprocessError as e:
        logging.error(f"Failed to start server: {e}")
        return False
    except Exception as e:
        logging.error(f"Unexpected error starting server: {e}")
        return False

def daemonize():
    """Daemonize the process to run in background even after SSH disconnect"""
    # Skip daemonization on Windows
    if platform.system().lower() == "windows":
        logging.info("Running on Windows - skipping daemonization")
        return
    
    try:
        # First fork
        try:
            pid = os.fork()
            if pid > 0:
                # Exit first parent
                sys.exit(0)
        except OSError as e:
            logging.error(f"Fork #1 failed: {e}")
            sys.exit(1)
        
        # Decouple from parent environment
        os.chdir('/')
        os.setsid()
        os.umask(0)
        
        # Second fork
        try:
            pid = os.fork()
            if pid > 0:
                # Exit second parent
                sys.exit(0)
        except OSError as e:
            logging.error(f"Fork #2 failed: {e}")
            sys.exit(1)
        
        # Redirect standard file descriptors
        sys.stdout.flush()
        sys.stderr.flush()
        
        with open('/dev/null', 'r') as f:
            os.dup2(f.fileno(), sys.stdin.fileno())
        with open('/tmp/server_monitor.out', 'a+') as f:
            os.dup2(f.fileno(), sys.stdout.fileno())
        with open('/tmp/server_monitor.err', 'a+') as f:
            os.dup2(f.fileno(), sys.stderr.fileno())
    
    except Exception as e:
        logging.error(f"Unexpected error during daemonization: {e}")
        sys.exit(1)
    
    # Write pid file
    try:
        with open('/tmp/server_monitor.pid', 'w') as f:
            f.write(str(os.getpid()))
    except Exception as e:
        logging.error(f"Failed to write PID file: {e}")

def check_for_kill_file():
    """Check if kill.txt file exists in the working directory"""
    try:
        kill_file_path = os.path.join(WORKING_DIR, KILL_FILE)
        if os.path.exists(kill_file_path):
            logging.info(f"Kill file '{KILL_FILE}' detected. Stopping monitor.")
            try:
                # Attempt to delete the kill file
                os.remove(kill_file_path)
                logging.info("Kill file removed.")
            except Exception as e:
                logging.warning(f"Could not remove kill file: {e}")
            return True
        return False
    except Exception as e:
        logging.error(f"Error checking for kill file: {e}")
        return False

def main_loop():
    """Main monitoring loop"""
    logging.info("Server monitor started")
    logging.info(f"Working directory: {WORKING_DIR}")
    logging.info(f"Server script path: {SERVER_SCRIPT_PATH}")
    
    error_count = 0
    max_consecutive_errors = 5
    
    # Initial server start
    if not is_server_running():
        logging.info("Server not running at startup, attempting to start it...")
        kill_processes_on_port()
        time.sleep(1)
        start_server()
    
    while True:
        try:
            # Check for kill file first
            if check_for_kill_file():
                logging.info("Shutting down server monitor")
                sys.exit(0)
            
            logging.info("Checking server status...")
            
            if is_server_running():
                logging.info("Server is running correctly")
                error_count = 0  # Reset error counter on success
            else:
                logging.warning("Server is down, restarting...")
                kill_processes_on_port()
                time.sleep(1)  # Brief pause to ensure port is released
                success = start_server()
                
                if not success:
                    error_count += 1
                    logging.warning(f"Server restart attempt failed. Error count: {error_count}/{max_consecutive_errors}")
                    
                    if error_count >= max_consecutive_errors:
                        logging.error(f"Maximum consecutive errors ({max_consecutive_errors}) reached. Sleeping for 60 seconds before retrying.")
                        time.sleep(60)  # Longer pause after multiple failures
                        error_count = 0  # Reset counter after pause
            
            time.sleep(CHECK_INTERVAL)
            
        except KeyboardInterrupt:
            logging.info("Keyboard interrupt detected. Shutting down.")
            break
        except Exception as e:
            logging.error(f"Unexpected error in main loop: {e}")
            error_count += 1
            
            if error_count >= max_consecutive_errors:
                logging.error(f"Too many consecutive errors ({error_count}). Sleeping for 60 seconds.")
                time.sleep(60)
                error_count = 0

if __name__ == "__main__":
    try:
        # Ensure we have the absolute path to the script
        SERVER_SCRIPT_PATH = os.path.abspath(SERVER_SCRIPT_PATH)
        logging.info(f"Monitoring server at: {SERVER_SCRIPT_PATH}")
        
        # Run as daemon if not already
        if len(sys.argv) > 1 and sys.argv[1] == '--daemon':
            # Save current working directory before starting main loop
            WORKING_DIR = os.getcwd()
            logging.info(f"Running in daemon mode with working directory: {WORKING_DIR}")
            main_loop()  # Call main_loop directly when in daemon mode
        else:
            print(f"Starting server monitor as daemon at {datetime.now()}")
            print(f"Logs will be written to {log_path}")
            print(f"Working directory: {WORKING_DIR}")
            print(f"Server script: {SERVER_SCRIPT_PATH}")
            logging.info("Daemonizing process")
            
            # Save current working directory before daemonization
            WORKING_DIR = os.getcwd()
            
            daemonize()
            
            # After daemonization, directly call main_loop instead of re-executing
            logging.info("Daemon process started, beginning main loop")
            main_loop()  # This is the key fix - call main_loop directly after daemonizing
            
    except Exception as e:
        logging.error(f"Fatal error starting monitor: {e}")
        print(f"Error starting monitor: {e}")
        sys.exit(1)
