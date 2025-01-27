
from datetime import datetime , timedelta , timezone
import logging
import ntplib
import pytz



logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)




class TimeConverter:
    """Handles time conversion between UTC and Indian Standard Time (IST)."""
    
    # IST offset from UTC is +5:30
    IST_OFFSET_HOURS = 5
    IST_OFFSET_MINUTES = 30
    
    @classmethod
    def utc_to_ist(cls, utc_dt):
        """Convert UTC datetime to IST datetime."""
        if not utc_dt:
            return None
            
        try:
            # Add IST offset
            ist_hours = utc_dt.hour + cls.IST_OFFSET_HOURS
            ist_minutes = utc_dt.minute + cls.IST_OFFSET_MINUTES
            
            # Handle minute overflow
            if ist_minutes >= 60:
                ist_hours += 1
                ist_minutes -= 60
            
            # Handle hour overflow
            if ist_hours >= 24:
                next_day = True
                ist_hours -= 24
            else:
                next_day = False
                
            # Create new datetime with IST values
            ist_dt = utc_dt.replace(hour=ist_hours, minute=ist_minutes)
            
            # Adjust date if needed
            if next_day:
                ist_dt = ist_dt + timedelta(days=1)
                
            return ist_dt
            
        except Exception as e:
            logger.error(f"UTC to IST conversion error: {e}")
            return utc_dt
    
    @classmethod
    def format_ist_timestamp(cls, dt, include_timezone=True):
        """Format datetime in IST format."""
        if not dt:
            return "Invalid Date"
            
        try:
            # Convert to IST if not already
            ist_dt = cls.utc_to_ist(dt)
            
            # Format with timezone indicator
            formatted = ist_dt.strftime('%Y-%m-%d %I:%M:%S %p')
            if include_timezone:
                formatted += " IST"
                
            return formatted
            
        except Exception as e:
            logger.error(f"IST formatting error: {e}")
            return "Invalid Date"
    
    @classmethod
    def format_relative_time(cls, dt):
        """Format time as relative (e.g., '2 hours ago')."""
        if not dt:
            return "Unknown time"
            
        try:
            now = datetime.now()
            ist_dt = cls.utc_to_ist(dt)
            diff = now - ist_dt
            
            seconds = diff.total_seconds()
            
            if seconds < 60:
                return "just now"
            elif seconds < 3600:
                minutes = int(seconds / 60)
                return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
            elif seconds < 86400:
                hours = int(seconds / 3600)
                return f"{hours} hour{'s' if hours != 1 else ''} ago"
            elif seconds < 604800:
                days = int(seconds / 86400)
                return f"{days} day{'s' if days != 1 else ''} ago"
            else:
                return ist_dt.strftime('%d %b %Y')
                
        except Exception as e:
            logger.error(f"Relative time formatting error: {e}")
            return "Unknown time"






class TimeSync:
    """Enhanced NTP time synchronization with robust error handling."""
    
    def __init__(self):
        self.ntp_client = ntplib.NTPClient()
        # Use more reliable NTP servers
        self.ntp_servers = [
            'time1.google.com',
            'time2.google.com', 
            'time3.google.com',
            'time.nist.gov',
            'pool.ntp.org',
            'asia.pool.ntp.org'
        ]
        self.time_offset = 0
        self.last_sync = None
        self.ist_timezone = pytz.timezone('Asia/Kolkata')
        
    def sync_time(self):
        """Sync with NTP servers with improved error handling."""
        for server in self.ntp_servers:
            try:
                # Set shorter timeout for faster fallback
                response = self.ntp_client.request(server, timeout=2)
                self.time_offset = response.offset
                self.last_sync = datetime.now(timezone.utc)
                logger.info(f"Time synced with {server}, offset: {self.time_offset:.3f}s")
                return True
            except Exception as e:
                logger.warning(f"Failed to sync with {server}: {e}")
                continue
        return False
        
    def get_current_time(self):
        """Get current time with NTP correction and IST conversion."""
        # Resync if needed (every hour)
        if not self.last_sync or (datetime.now(timezone.utc) - self.last_sync).total_seconds() > 3600:
            self.sync_time()
            
        # Get current UTC time with NTP offset
        current_utc = datetime.now(timezone.utc) + timedelta(seconds=self.time_offset)
        
        # Convert to IST
        return current_utc.astimezone(self.ist_timezone)
        
    def format_time(self, dt, include_timezone=True, relative=False):
        """Format time in 12-hour clock with IST."""
        if not dt:
            return "Invalid Date"
            
        try:
            # Ensure datetime is timezone-aware
            if dt.tzinfo is None:
                dt = pytz.UTC.localize(dt)
                
            # Convert to IST
            ist_dt = dt.astimezone(self.ist_timezone)
            
            if relative:
                return self._format_relative(ist_dt)
            
            # Format in 12-hour clock
            formatted = ist_dt.strftime('%Y-%m-%d %I:%M:%S %p')
            if include_timezone:
                formatted += " IST"
                
            return formatted
            
        except Exception as e:
            logger.error(f"Time formatting error: {e}")
            return "Invalid Date"
            
    def _format_relative(self, dt):
        """Format relative time (e.g., '2 hours ago')."""
        try:
            now = self.get_current_time()
            diff = now - dt
            
            seconds = diff.total_seconds()
            
            if seconds < 60:
                return "just now"
            elif seconds < 3600:
                minutes = int(seconds / 60)
                return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
            elif seconds < 86400:
                hours = int(seconds / 3600)
                return f"{hours} hour{'s' if hours != 1 else ''} ago"
            elif seconds < 604800:
                days = int(seconds / 86400)
                return f"{days} day{'s' if days != 1 else ''} ago"
            else:
                return dt.strftime('%d %b %Y %I:%M %p IST')
                
        except Exception as e:
            logger.error(f"Relative time formatting error: {e}")
            return "Unknown time"
            
    def parse_datetime(self, date_str):
        """Parse datetime string to timezone-aware datetime."""
        try:
            # Parse string to datetime
            dt = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
            
            # Make timezone-aware as UTC
            dt = pytz.UTC.localize(dt)
            
            # Convert to IST
            return dt.astimezone(self.ist_timezone)
            
        except Exception as e:
            logger.error(f"DateTime parsing error: {e}")
            return None
