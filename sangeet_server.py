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
        Enhanced Flask logging with Unicode support, better error handling,
        and improved organization while maintaining original functionality
        """
        init()
        os.makedirs('logs', exist_ok=True)
        log_file = f"logs/{datetime.now():%Y%m%d_%H%M}.log"

        class EnhancedRequestFormatter(logging.Formatter):
            COLORS = {
                'DEBUG': Fore.BLUE,
                'INFO': Fore.GREEN,
                'WARNING': Fore.YELLOW,
                'ERROR': Fore.RED,
                'CRITICAL': Fore.RED + Style.BRIGHT
            }

            SKIP_PATHS = {
                '/favicon.ico', 
                '/audioworklet/qualityProcessor.js',
                '/data/download/icons/',
                '/api/session-status',  # Add common status checks
                '/static/',  # Skip static file requests
                '/design/'   # Skip design file requests
            }

            def __init__(self, *args, use_color=False, **kwargs):
                super().__init__(*args, **kwargs)
                self.use_color = use_color

            def colorize(self, level_name):
                if self.use_color:
                    color = self.COLORS.get(level_name, '')
                    return f"{color}{level_name:8}{Style.RESET_ALL}"
                return f"{level_name:8}"

            def should_log_path(self, path):
                return not any(path.startswith(skip) for skip in self.SKIP_PATHS)

            def format(self, record):
                try:
                    if has_request_context():
                        # Add request ID if not present
                        if not hasattr(g, 'request_id'):
                            g.request_id = str(uuid.uuid4())[:8]
                        record.request_id = g.request_id

                        # Clean and format the URL
                        path = request.path
                        if not self.should_log_path(path):
                            return None

                        # Add timing information
                        if hasattr(g, 'request_start'):
                            duration = datetime.now() - g.request_start
                            duration_ms = int(duration.total_seconds() * 1000)
                        else:
                            duration_ms = 0

                        # Format message based on type
                        if hasattr(record, 'response_included'):
                            msg = (f"{self.colorize(record.levelname)} [{record.request_id}] "
                                f"{request.method} {path} → {record.response_status} ({duration_ms}ms)")
                            
                            # Add response size if available
                            if hasattr(record, 'response_size'):
                                msg += f" [{self.format_size(record.response_size)}]"
                                
                            # Add body for non-GET requests with content
                            if record.body and record.body != "b''" and request.method != 'GET':
                                msg += f"\n    Body: {record.body}"
                            return msg
                    else:
                        # Non-request logs
                        return f"{self.colorize(record.levelname)} {record.getMessage()}"

                    return None
                except Exception as e:
                    # Fallback formatting if there's an error
                    return f"[LOGGING ERROR: {str(e)}] {record.getMessage()}"

            def format_size(self, size):
                """Format response size in human readable format"""
                for unit in ['B', 'KB', 'MB', 'GB']:
                    if size < 1024:
                        return f"{size:.1f}{unit}"
                    size /= 1024
                return f"{size:.1f}TB"

        class UTFRotatingFileHandler(RotatingFileHandler):
            """Enhanced RotatingFileHandler with proper UTF-8 handling"""
            def emit(self, record):
                try:
                    msg = self.format(record)
                    if msg:  # Only write if there's a message
                        # Ensure proper UTF-8 encoding
                        if isinstance(msg, str):
                            msg = msg.encode('utf-8')
                        stream = self.stream
                        stream.write(msg)
                        stream.write(self.terminator.encode('utf-8') if isinstance(self.terminator, str) else self.terminator)
                        self.flush()
                except Exception:
                    self.handleError(record)

        # Configure handlers
        handlers = []
        
        # Console handler with colors
        console = logging.StreamHandler()
        console.setFormatter(EnhancedRequestFormatter(use_color=True))
        console.addFilter(lambda record: record.levelno >= log_level)
        handlers.append(console)
        
        # File handler with rotation (10MB files, keep 5 backups)
        file_handler = UTFRotatingFileHandler(
            log_file,
            maxBytes=10_000_000,
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setFormatter(EnhancedRequestFormatter(use_color=False))
        handlers.append(file_handler)

        # Clear existing handlers and configure logger
        app.logger.handlers.clear()
        app.logger.setLevel(log_level)
        for handler in handlers:
            app.logger.addHandler(handler)
        app.logger.propagate = False

        # Request/response handling
        @app.before_request
        def before_request():
            g.request_start = datetime.now()
            # Skip logging for ignored paths
            if EnhancedRequestFormatter.should_log_path(EnhancedRequestFormatter(), request.path):
                g.log_request = True
                # Only store body for non-GET requests
                if request.method != 'GET':
                    g.request_body = request.get_data()

        @app.after_request
        def after_request(response):
            try:
                if hasattr(g, 'log_request'):
                    # Combine request and response info into a single log entry
                    record = logging.LogRecord(
                        name=app.logger.name,
                        level=logging.INFO,
                        pathname='',
                        lineno=0,
                        msg='',
                        args=(),
                        exc_info=None
                    )
                    record.response_included = True
                    record.response_status = response.status
                    record.response_size = len(response.get_data())
                    record.body = str(getattr(g, 'request_body', None)) if request.method != 'GET' else None
                    app.logger.handle(record)
            except Exception as e:
                app.logger.error(f"Logging error: {e}")
            return response

        @app.errorhandler(Exception)
        def log_exception(e):
            app.logger.error(f"Unhandled exception: {str(e)}", exc_info=True)
            return "Internal Server Error", 500

        app.logger.info("Enhanced logging initialized")
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
