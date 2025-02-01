from flask import Flask , request
from sangeet_premium.sangeet import playback
from sangeet_premium.utils import getffmpeg
import sys
from threading import Thread
import logging
import multiprocessing
import time
from time import strftime
import subprocess
from termcolor import colored
from logging.handlers import RotatingFileHandler
from sangeet_premium.database import database
from sangeet_premium.utils import cloudflarerun, util, download_cloudflare
from colorama import init, Fore, Style
import pyfiglet
import os
from datetime import timedelta, datetime
from dotenv import load_dotenv
import uuid
from flask import request, has_request_context, g
from logging.handlers import RotatingFileHandler
# Initialize colorama
init(autoreset=True)
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
load_dotenv(dotenv_path=os.path.join(os.getcwd(), "config", ".env"))

app = Flask(__name__)
app.secret_key = "mdkllnlfnlnlfll"
app.register_blueprint(playback.bp)
app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

def print_banner():
    # Create figlet text
    sangeet_text = pyfiglet.figlet_format("SANGEET", font='big')
    premium_text = pyfiglet.figlet_format("PREMIUM", font='big')
    
    # Print the banner with colors
    print(f"{Fore.MAGENTA}{sangeet_text}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{premium_text}{Style.RESET_ALL}")
    print(f"\n{Fore.YELLOW}♪ Premium Music Streaming Service ♪{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}Version: 1.0.0 | Made with ♥ by Sandesh Kumar{Style.RESET_ALL}")
    print(f"{Fore.GREEN}Starting server at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Style.RESET_ALL}")
    print("="*80)
def start_local_songs_refresh(app):
    """Start a background thread to refresh local songs every 20 seconds."""
    def refresh_loop():
        while True:
            try:
                # Create a new application context for each iteration
                with app.app_context():
                    playback.load_local_songs_from_file()
            except Exception as e:
                logger.error(f"Error refreshing local songs: {e}")
            time.sleep(20)  # Wait 20 seconds before next refresh
    
    # Start the refresh thread
    refresh_thread = Thread(target=refresh_loop, daemon=True)
    refresh_thread.start()
    logger.info("Started local songs refresh thread")

def init_app(app):
    """Initialize the blueprint with the main Flask app."""
    start_local_songs_refresh(app)
if __name__ == '__main__':
    try:
        print_banner()
    except Exception as e:
        print(f"Banner display error: {e}")
        print("Continuing with server startup...")
    getffmpeg.main()

    database.init_db()
    database.init_auth_db()

    # Load local songs from disk
    util.load_local_songs()

    # Make sure music dir exists
    os.makedirs(os.getenv("music_path"), exist_ok=True)

    # Run Flask
    playback.load_local_songs_from_file()
    util.download_default_songs()
    init_app(app)


    # Calculate optimal workers
   

    cloudflarerun.run_cloudflare(os.getenv('port'), download_cloudflare.get_cloudflared(os.path.join(os.getcwd(), "cloudflare_driver_latest")))

    directories = [
        "cloudflare_driver_latest", "assets", "data", "database_files",
        "extension", "locals", "logs", os.getenv("music_path"), "tests",
        "payloads", "res", "sangeet_premium", "static", "templates",
        "requirements", "config"
    ]

    for directory in directories:
        try:
            os.makedirs(directory, exist_ok=True)
            print(f"Directory '{directory}' created successfully or already exists.")
        except Exception as e:
            print(f"Error creating directory '{directory}': {e}")
    

 

    def setup_logging(app, log_level=logging.INFO):
        """
        Setup enhanced Flask server logging with clear request/response tracking
        and proper output formatting
        """
        init()  # Initialize colorama
        
        # Create logs directory
        os.makedirs('logs', exist_ok=True)
        log_file = f"logs/flask_server_{datetime.now():%Y%m%d_%H%M}.log"
        
        class ServerLogFormatter(logging.Formatter):
            COLORS = {
                'DEBUG': Fore.CYAN,
                'INFO': Fore.GREEN,
                'WARNING': Fore.YELLOW,
                'ERROR': Fore.RED,
                'CRITICAL': Fore.RED + Style.BRIGHT
            }
            
            def __init__(self, use_colors=False):
                super().__init__()
                self.use_colors = use_colors
            
            def format_level(self, level_name):
                if self.use_colors:
                    color = self.COLORS.get(level_name, '')
                    return f"{color}{level_name:8}{Style.RESET_ALL}"
                return f"{level_name:8}"
            
            def format(self, record):
                try:
                    if has_request_context():
                        # Generate request ID if not present
                        if not hasattr(g, 'request_id'):
                            g.request_id = str(uuid.uuid4())[:6]
                        
                        # Calculate request duration
                        duration = ''
                        if hasattr(g, 'start_time'):
                            duration = f" ({int((datetime.now() - g.start_time).total_seconds() * 1000)}ms)"
                        
                        # Format the log message
                        msg = (f"{self.format_level(record.levelname)} "
                            f"[{g.request_id}] {request.method} {request.path} "
                            f"→ {getattr(record, 'status_code', '')}{duration}")
                        
                        # Add request data for non-GET requests
                        if request.method != 'GET' and hasattr(record, 'request_data'):
                            msg += f"\n    Request: {record.request_data}"
                        
                        # Add response data if available
                        if hasattr(record, 'response_data'):
                            msg += f"\n    Response: {record.response_data}"
                        
                        return msg
                    else:
                        # Non-request logs (server events)
                        return f"{self.format_level(record.levelname)} {record.getMessage()}"
                except Exception as e:
                    return f"Logging Error: {str(e)} | Original: {record.getMessage()}"
        
        # Setup handlers
        handlers = []
        
        # Console handler (with colors)
        console = logging.StreamHandler()
        console.setFormatter(ServerLogFormatter(use_colors=True))
        handlers.append(console)
        
        # File handler (no colors)
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=5_000_000,  # 5MB
            backupCount=3,
            encoding='utf-8'
        )
        file_handler.setFormatter(ServerLogFormatter(use_colors=False))
        handlers.append(file_handler)
        
        # Configure Flask logger
        app.logger.handlers.clear()
        app.logger.setLevel(log_level)
        for handler in handlers:
            app.logger.addHandler(handler)
        
        # Request tracking
        @app.before_request
        def track_request():
            g.start_time = datetime.now()
            if request.method != 'GET':
                g.request_data = request.get_data(as_text=True)
        
        @app.after_request
        def log_request(response):
            try:
                # Skip logging for static files and health checks
                if not request.path.startswith(('/static/', '/favicon.ico', '/health')):
                    record = logging.LogRecord(
                        name=app.logger.name,
                        level=logging.INFO,
                        pathname='',
                        lineno=0,
                        msg='',
                        args=(),
                        exc_info=None
                    )
                    
                    # Add response info
                    record.status_code = response.status_code
                    if response.is_json:
                        record.response_data = response.get_data(as_text=True)[:200]  # Limit length
                    
                    # Add request data for non-GET requests
                    if request.method != 'GET':
                        record.request_data = getattr(g, 'request_data', '')[:200]  # Limit length
                    
                    app.logger.handle(record)
            except Exception as e:
                app.logger.error(f"Logging error: {str(e)}")
            return response
        
        # Error logging
        @app.errorhandler(Exception)
        def log_error(error):
            app.logger.error(f"Server Error: {str(error)}", exc_info=True)
            return "Internal Server Error", 500
        
        app.logger.info("Flask server logging initialized")
        return app.logger
    def run_production_server(app, port=8000):
        """Run server with proper logging"""
        host = '0.0.0.0'
        
        # Setup logging first
        setup_logging(app)
        
        # Check if system is Windows
        is_windows = sys.platform.startswith('win')
        if is_windows:
            app.logger.warning(colored(
                "Using Flask's built-in server (not recommended for production)",
                'yellow'
            ))
            app.run(
                host=host,
                port=port,
                debug=False,
                threaded=True
            )
        
        try:
            if is_windows:
                raise ImportError("Windows not supported by Gunicorn")
                
            import gunicorn
            workers = (multiprocessing.cpu_count() * 2) + 1
            try:
                subprocess.Popen(f"chmod -R 777 '{os.getcwd()}'" , shell = True)
            except:
                print("give permissions by adding chmod -R 777 /path/to/directory")
            app.logger.info(colored(
                f"Starting Gunicorn server on {host}:{port} with {workers} workers",
                'green'
            ))
            
            import gunicorn.app.base
            
            class GunicornServer(gunicorn.app.base.BaseApplication):
                def __init__(self, app, options=None):
                    self.options = options or {}
                    self.application = app
                    super().__init__()

                def load_config(self):
                    for key, value in self.options.items():
                        self.cfg.set(key, value)

                def load(self):
                    return self.application
            
            options = {
                'bind': f'{host}:{port}',
                'workers': workers,
                'timeout': 30,
                'keepalive': 5,
                'worker_class': 'sync',
                'accesslog': 'logs/gunicorn_access.log',
                'errorlog': 'logs/gunicorn_error.log',
                'loglevel': 'info'
            }
            
            GunicornServer(app, options).run()
            
        except ImportError:
            app.logger.warning(colored(
                "Using Flask's built-in server (not recommended for production)",
                'yellow'
            ))
            app.run(
                host=host,
                port=port,
                debug=False,
                threaded=True
            )
    

    run_production_server(app , port = os.getenv("port"))
