import time
import sqlite3
import os
import base64
import json
import logging
from flask import session, redirect
from functools import wraps
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import re
import requests
from mutagen import File as MutagenFile
from mutagen import  File
from ..helpers import time_helper
import random
from mutagen.flac import FLAC
from datetime import timedelta
import os
import platform
import requests
import stat
from pathlib import Path

from ytmusicapi import YTMusic
import secrets
import subprocess
import platform
from datetime import datetime
from flask import jsonify
from typing import List, Dict, Any
from dotenv import load_dotenv
from functools import  lru_cache
load_dotenv(dotenv_path=os.path.join(os.getcwd() , "config" , ".env"))
DB_PATH = os.path.join(os.getcwd() , "database_files" , "sangeet_database_main.db")

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def setup_ytdlp():
    """
    Set up yt-dlp executable and return its paths.
    Creates system-specific subdirectories in res folder.
    Checks existing version before downloading.
    
    Returns:
        tuple: (executable_path: str, version_path: str)
    """
    try:
        # Detect system
        system = platform.system().lower()
        machine = platform.machine().lower()
        
        print(f"Detected system: {system}")
        print(f"Detected machine architecture: {machine}")
        
        # More precise architecture mapping
        download_patterns = {
            'aarch64': 'yt-dlp_linux_aarch64',
            'armv7l': 'yt-dlp_linux_armv7l',
            'armv6l': 'yt-dlp_linux_armv7l',
            'x86_64': 'yt-dlp_linux',
            'amd64': 'yt-dlp_linux',
            'i386': 'yt-dlp_linux_x86',
            'i686': 'yt-dlp_linux_x86'
        }
        
        if system == "windows":
            download_pattern = "yt-dlp.exe"
        elif system == "darwin":
            download_pattern = "yt-dlp_macos"
        else:  # linux
            download_pattern = download_patterns.get(machine)
            if not download_pattern:
                raise Exception(f"Unsupported architecture: {machine}")
        
        print(f"Selected download pattern: {download_pattern}")
        
        # Create system-specific directory
        res_dir = Path('res') / system / machine
        res_dir.mkdir(parents=True, exist_ok=True)
        
        # Set paths
        executable = "yt-dlp.exe" if system == "windows" else "yt-dlp"
        executable_path = res_dir / executable
        version_path = res_dir / "version.txt"
        
        # Get latest release info
        api_url = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
        response = requests.get(api_url)
        release_data = response.json()
        latest_version = release_data['tag_name']
        
        # Check if version file exists and compare versions
        should_download = True
        if executable_path.exists() and version_path.exists():
            with open(version_path, 'r') as f:
                current_version = f.read().strip()
                if current_version == latest_version:
                    print(f"Current version {current_version} matches latest version. Skipping download.")
                    should_download = False
                else:
                    print(f"Update needed: Current version {current_version}, latest version {latest_version}")
        
        if should_download:
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
            response = requests.get(download_url)
            with open(executable_path, 'wb') as f:
                f.write(response.content)
            
            # Save version information
            with open(version_path, 'w') as f:
                f.write(latest_version)
            
            # Set executable permissions for non-Windows systems
            if system != "windows":
                executable_path.chmod(executable_path.stat().st_mode | stat.S_IEXEC)
                
            print(f"Successfully installed version {latest_version} to: {executable_path}")
        
        return str(executable_path), str(version_path)
    
    except Exception as e:
        print(f"Error setting up yt-dlp: {e}")
        return None, None


# Create the full path
YTDLP_PATH , version_path = setup_ytdlp()
MUSIC_DIR = os.getenv("music_path")

FFMPEG_BIN_DIR = os.path.join(os.getcwd(), "res", "ffmpeg", "bin")  # Path to ffmpeg binary

song_cache = {}


LOCAL_SONGS_PATHS = os.getenv("LOCAL_SONGS_PATHS", "")
ytmusic = YTMusic()

time_sync = time_helper.TimeSync()

CACHE_DURATION = 3600
search_cache = {}
song_cache = {}
lyrics_cache = {}
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))


def generate_session_id():
    """Generate a unique session ID for grouping played songs."""
    return f"session_{int(time.time())}"

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or 'session_token' not in session:
            return redirect('/login')
            
        # Verify session is still valid in database
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute("""
            SELECT 1 FROM active_sessions 
            WHERE user_id = ? AND session_token = ? 
            AND expires_at > CURRENT_TIMESTAMP
        """, (session['user_id'], session['session_token']))
        
        valid_session = c.fetchone()
        conn.close()
        
        if not valid_session:
            # Clear invalid session
            session.clear()
            return redirect("/login")
            
        return f(*args, **kwargs)
    return decorated_function
@login_required
def record_song(song_id, user_id):
    """Record song play with user association."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Get or create current session
        c.execute("""
            SELECT session_id, MAX(sequence_number)
            FROM user_history
            WHERE user_id = ? AND played_at >= datetime('now', '-1 hour')
            GROUP BY session_id
            ORDER BY played_at DESC
            LIMIT 1
        """, (user_id,))
        
        result = c.fetchone()
        if result:
            session_id, last_seq = result
            sequence_number = last_seq + 1
        else:
            session_id = generate_session_id()
            sequence_number = 1
        
        # Insert new play record
        c.execute("""
            INSERT INTO user_history (user_id, song_id, session_id, sequence_number)
            VALUES (?, ?, ?, ?)
        """, (user_id, song_id, session_id, sequence_number))
        
        # Update user stats
        c.execute("""
            INSERT INTO user_stats (user_id, total_plays, last_played)
            VALUES (?, 1, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                total_plays = total_plays + 1,
                last_played = CURRENT_TIMESTAMP
        """, (user_id,))
        
        conn.commit()
        
    except Exception as e:
        logger.error(f"Error recording song play: {e}")
        raise
    finally:
        conn.close()




@login_required
def get_recent_activity(c) :
    """Get recent activity with proper IST timestamps."""
    c.execute("""
        SELECT 
            title, artist, started_at, listened_duration, completion_rate
        FROM listening_history
        ORDER BY started_at DESC
        LIMIT 50
    """)
    
    activities = []
    for row in c.fetchall():
        try:
            # Parse the stored time
            started_at = time_sync.parse_datetime(row[2])
            
            activities.append({
                "title": row[0],
                "artist": row[1],
                "started_at": time_sync.format_time(started_at),
                "started_at_relative": time_sync.format_time(started_at, relative=True),
                "duration": row[3],
                "completion": row[4]
            })
        except Exception as e:
            logger.error(f"Error processing activity: {e}")
            continue
            
    return activities

@login_required
def record_download(video_id, title, artist, album, path, user_id):
    """Store a downloaded track with user association."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO user_downloads 
            (user_id, video_id, title, artist, album, path)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, video_id, title, artist, album, path))
        conn.commit()
    finally:
        conn.close()

@login_required
def get_play_history(user_id, limit=50):
    """Get user's play history."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute("""
            SELECT 
                h.song_id, 
                h.played_at, 
                h.session_id, 
                h.sequence_number,
                d.title,
                d.artist,
                d.path
            FROM user_history h
            LEFT JOIN user_downloads d 
                ON h.song_id = d.video_id 
                AND h.user_id = d.user_id
            WHERE h.user_id = ?
            ORDER BY h.played_at DESC
            LIMIT ?
        """, (user_id, limit))
        
        history = []
        for row in c.fetchall():
            song_id, played_at, session_id, seq_num, title, artist, path = row
            
            # Convert UTC to IST
            indian_time = time_sync.format_time(datetime.fromisoformat(played_at))
            
            if song_id.startswith("local-"):
                meta = local_songs.get(song_id)
                if meta:
                    history.append({
                        "id": song_id,
                        "title": meta["title"],
                        "artist": meta["artist"],
                        "thumbnail": meta.get("thumbnail", ""),
                        "played_at": indian_time,
                        "session_id": session_id,
                        "sequence_number": seq_num
                    })
            else:
                try:
                    if song_id not in song_cache:
                        data = ytmusic.get_song(song_id)
                        song_cache[song_id] = data
                    else:
                        data = song_cache[song_id]
                    
                    vd = data.get("videoDetails", {})
                    history.append({
                        "id": song_id,
                        "title": vd.get("title", "Unknown"),
                        "artist": vd.get("author", "Unknown Artist"),
                        "thumbnail": f"https://i.ytimg.com/vi/{song_id}/hqdefault.jpg",
                        "played_at": indian_time,
                        "session_id": session_id,
                        "sequence_number": seq_num
                    })
                except Exception as e:
                    logger.error(f"Error fetching song info: {e}")
                    continue
        
        conn.close()
        return history
        
    except Exception as e:
        logger.error(f"Error getting play history: {e}")
        return []
    
local_songs = {}

def load_local_songs():
    """Scan local directories for music files and extract metadata."""
    if not LOCAL_SONGS_PATHS:
        return
    dirs = [d.strip() for d in LOCAL_SONGS_PATHS.split(";") if d.strip()]
    logger.info(f"Loading local songs from: {dirs}")

    file_exts = {".mp3", ".flac", ".m4a", ".wav", ".ogg", ".wma", ".aac", ".aiff", ".alac"}
    counter = 0

    for d in dirs:
        if not os.path.isdir(d):
            logger.warning(f"Local path is not a directory: {d}")
            continue
        for root, _, files in os.walk(d):
            for fname in files:
                _, ext = os.path.splitext(fname)
                if ext.lower() not in file_exts:
                    continue
                full_path = os.path.join(root, fname)
                counter += 1
                local_id = f"local-{counter}"

                # Default metadata
                title = fname
                artist = "Unknown Artist"
                album = "Unknown Album"
                duration = 0
                thumbnail = ""

                try:
                    # Read audio file
                    audio = File(full_path, easy=True)
                    if audio and hasattr(audio, "info") and hasattr(audio.info, "length"):
                        duration = int(audio.info.length)

                    # Extract common metadata
                    if audio:
                        title = audio.get("title", [fname])[0]
                        artist = audio.get("artist", ["Unknown Artist"])[0]
                        album = audio.get("album", ["Unknown Album"])[0]

                    # Handle specific formats for additional data
                    if isinstance(audio, FLAC) or hasattr(audio, "pictures"):
                        pictures = getattr(audio, "pictures", [])
                        if pictures:
                            pic = pictures[0]
                            thumbnail = f"data:{pic.mime};base64,{base64.b64encode(pic.data).decode()}"
                    elif hasattr(audio, "tags"):
                        # ID3 tags for MP3 and similar formats
                        tags = audio.tags
                        if "APIC:" in tags:  # Attached picture (ID3)
                            pic = tags["APIC:"]
                            thumbnail = f"data:{pic.mime};base64,{base64.b64encode(pic.data).decode()}"

                except Exception as e:
                    logger.error(f"Error reading metadata from {fname}: {e}")

                # Add song to dictionary
                local_songs[local_id] = {
                    "id": local_id,
                    "title": title,
                    "artist": artist,
                    "album": album,
                    "path": full_path,
                    "thumbnail": thumbnail,
                    "duration": duration,
                }

    logger.info(f"Loaded {len(local_songs)} local songs with metadata.")

    # Save local_songs to a JSON file
    try:
        with open(os.path.join(os.getcwd() , "locals" , "local.json"), "w", encoding="utf-8") as json_file:
            json.dump(local_songs, json_file, ensure_ascii=False, indent=4)
        logger.info("Local songs saved to local_songs.json.")
    except Exception as e:
        logger.error(f"Error saving local songs to JSON file: {e}")

    return local_songs

def get_song_info(song_id):
    """Get song metadata with error handling."""
    try:
        info = ytmusic.get_song(song_id)
        if not info:
            return jsonify({"error": "Song not found"}), 404
            
        vd = info.get("videoDetails", {})
        return jsonify({
            "id": song_id,
            "title": vd.get("title", "Unknown"),
            "artist": vd.get("author", "Unknown Artist"),
            "thumbnail": f"https://i.ytimg.com/vi/{song_id}/hqdefault.jpg",
            "duration": int(vd.get("lengthSeconds", 0))
        })
    except Exception as e:
        logger.error(f"Song info error: {e}")
        return jsonify({"error": str(e)}), 500

def get_fallback_recommendations():
    """Get fallback recommendations when normal methods fail."""
    try:
        # Try popular music first
        results = ytmusic.search("popular music", filter="songs", limit=5)
        if not results:
            # Fallback to trending
            results = ytmusic.search("trending songs", filter="songs", limit=5)
            
        if not results:
            return jsonify([]), 404
            
        recs = []
        for track in results:
            if not track.get("videoId"):
                continue
                
            recs.append({
                "id": track["videoId"],
                "title": track["title"],
                "artist": track["artists"][0]["name"] if track.get("artists") else "Unknown",
                "thumbnail": f"https://i.ytimg.com/vi/{track['videoId']}/hqdefault.jpg"
            })
            
            if len(recs) >= 5:
                break
                
        return jsonify(recs)
        
    except Exception as e:
        logger.error(f"Fallback recommendations error: {e}")
        return jsonify([]), 500
def is_potential_video_id(filename: str) -> bool:
    """Check if a filename might be a YouTube video ID."""
    # Remove local- prefix if present
    if filename.startswith("local-"):
        filename = filename[6:]
    
    # YouTube video IDs are typically 11 characters
    # and contain alphanumeric chars plus - and _
    return bool(re.match(r'^[A-Za-z0-9_-]{11}$', filename))





def sanitize_filename(s: str) -> str:
    """Remove invalid characters from filename."""
    # Remove invalid chars
    s = re.sub(r'[<>:"/\\|?*]', '', s)
    # Limit length
    s = s[:200]
    # Remove leading/trailing spaces and dots
    s = s.strip('. ')
    # Replace remaining dots except last extension
    s = s.replace('.', '_')
    return s if s else 'unknown'

def process_description(description):
    """Process and clean artist description"""
    if isinstance(description, list):
        description = ' '.join(description)
    return description.strip() or 'No description available'

def get_best_thumbnail(thumbnails):
    """Get highest quality thumbnail URL"""
    try:
        if not thumbnails or not isinstance(thumbnails, list):
            return ''
        thumb = thumbnails[-1].get('url', '')
        if thumb.startswith('//'):
            return f"https:{thumb}"
        return thumb
    except:
        return ''

def process_genres(artist_data):
    """Extract and process genres"""
    try:
        if 'genres' not in artist_data:
            return []
            
        if isinstance(artist_data['genres'], list):
            return artist_data['genres']
        elif artist_data['genres']:
            return [artist_data['genres']]
        return []
    except:
        return []
@login_required
def get_artist_stats(artist_data):
    """Extract all artist statistics"""
    try:
        # Get monthly listeners with fallbacks
        monthly_listeners = get_monthly_listeners(artist_data)
        
        # Extract and format stats
        stats = {
            'subscribers': safe_format_count(artist_data.get('subscribers', '0')),
            'views': safe_format_count(artist_data.get('views', '0')),
            'monthlyListeners': safe_format_count(monthly_listeners)
        }
        
        # Try to get additional stats if available
        if 'stats' in artist_data and isinstance(artist_data['stats'], dict):
            extra_stats = artist_data['stats']
            if 'totalPlays' in extra_stats:
                stats['totalPlays'] = safe_format_count(extra_stats['totalPlays'])
            if 'avgDailyPlays' in extra_stats:
                stats['avgDailyPlays'] = safe_format_count(extra_stats['avgDailyPlays'])
                
        return stats
    except Exception as e:
        logger.warning(f"Error processing stats: {e}")
        return {
            'subscribers': '0',
            'views': '0',
            'monthlyListeners': '0'
        }

def get_monthly_listeners(artist_data):
    """Extract monthly listeners with multiple fallback methods"""
    try:
        # Try direct stats object first
        if 'stats' in artist_data:
            stats = artist_data['stats']
            if isinstance(stats, dict):
                for key in ['monthlyListeners', 'monthly_listeners', 'listeners']:
                    if key in stats and stats[key]:
                        return stats[key]

        # Try top level fields
        for key in ['monthlyListeners', 'monthly_listeners', 'listeners']:
            if key in artist_data and artist_data[key]:
                return artist_data[key]

        # Get from subscriptionButton if available
        if 'subscriptionButton' in artist_data:
            sub_text = artist_data['subscriptionButton'].get('text', '')
            if isinstance(sub_text, str):
                match = re.search(r'(\d[\d,.]*[KMB]?)\s*(?:monthly listeners|listeners)', 
                                sub_text, re.IGNORECASE)
                if match:
                    return match.group(1)

        # Try to extract from header or subscription count
        return (artist_data.get('header', {}).get('subscriberCount') or 
                artist_data.get('subscribers', '0'))

    except Exception as e:
        logger.warning(f"Error extracting monthly listeners: {e}")
        return '0'

def process_top_songs(artist_data):
    """Process and extract top songs information"""
    top_songs = []
    try:
        songs_data = artist_data.get('songs', [])
        if not isinstance(songs_data, list):
            return []

        for song in songs_data[:10]:  # Limit to top 10
            if not isinstance(song, dict):
                continue
                
            try:
                song_info = {
                    'title': song.get('title', 'Unknown'),
                    'videoId': song.get('videoId', ''),
                    'plays': safe_format_count(song.get('plays', '0')),
                    'duration': song.get('duration', ''),
                    'thumbnail': get_best_thumbnail(song.get('thumbnails', [])),
                    'album': (song.get('album', {}) or {}).get('name', ''),
                    'year': song.get('year', '')
                }
                
                if song_info['videoId']:  # Only add if we have a valid video ID
                    top_songs.append(song_info)
            except Exception as e:
                logger.warning(f"Error processing song: {e}")
                continue

    except Exception as e:
        logger.warning(f"Error processing top songs: {e}")
    
    return top_songs

def process_artist_links(artist_data, artist_id):
    """Process and extract all artist links"""
    links = {
        'youtube': f"https://music.youtube.com/channel/{artist_id}" if artist_id else None,
        'official': artist_data.get('officialWebsite')
    }

    # Add social media links if available
    try:
        if 'links' in artist_data:
            for link in artist_data['links']:
                if isinstance(link, dict):
                    link_type = link.get('type', '').lower()
                    if link_type in ['instagram', 'twitter', 'facebook']:
                        links[link_type] = link.get('url', '')
    except Exception as e:
        logger.warning(f"Error processing social links: {e}")

    return links
def extract_video_id(url):
    """Extract video ID from various YouTube/YouTube Music URL formats"""
    try:
        # Common YouTube URL patterns
        patterns = [
            r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|music\.youtube\.com/watch\?v=|music\.youtube\.com/playlist\?list=)([a-zA-Z0-9_-]{11})',
            r'(?:youtube\.com/shorts/)([a-zA-Z0-9_-]{11})',
            r'(?:youtube\.com/playlist\?list=)([a-zA-Z0-9_-]{34})',
            r'(?:music\.youtube\.com/browse/)([a-zA-Z0-9_-]{11})'
        ]
        
        # Try each pattern
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        return None
    except:
        return None
def extract_year(artist_data):
    """Extract artist's formation/debut year"""
    try:
        # Try direct year field
        if 'yearFormed' in artist_data:
            return str(artist_data['yearFormed'])

        # Try years active
        if 'years_active' in artist_data:
            years = artist_data['years_active']
            if isinstance(years, list) and years:
                return str(years[0])

        # Try to find year in description
        if 'description' in artist_data:
            desc = str(artist_data['description'])
            match = re.search(r'\b(19|20)\d{2}\b', desc)
            if match:
                return match.group(0)

        return None
    except Exception as e:
        logger.warning(f"Error extracting year: {e}")
        return None

def safe_format_count(count):
    """Safely format numerical counts with K/M/B suffixes"""
    try:
        if not count or str(count).strip() in ['0', '', 'None', 'null']:
            return '0'
            
        # Remove any commas and spaces
        count_str = str(count).replace(',', '').replace(' ', '')
        
        # Handle if count is already formatted
        if any(suffix in count_str.upper() for suffix in ['K', 'M', 'B']):
            return count_str.upper()  # Normalize suffix to uppercase
            
        num = float(count_str)
        if num >= 1_000_000_000:
            return f"{num/1_000_000_000:.1f}B"
        if num >= 1_000_000:
            return f"{num/1_000_000:.1f}M"
        if num >= 1_000:
            return f"{num/1_000:.1f}K"
        return str(int(num))
    except Exception as e:
        logger.warning(f"Error formatting count {count}: {e}")
        return str(count)
def get_download_info(video_id):
    """Return file path if already downloaded, else None."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT path FROM downloads WHERE video_id = ?", (video_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def get_recent_plays(limit=10):
    """Get user's recent play history for context."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT DISTINCT song_id 
        FROM history 
        ORDER BY played_at DESC 
        LIMIT ?
    """, (limit,))
    recent = [row[0] for row in c.fetchall()]
    conn.close()
    return recent




def filter_local_songs(query: str):
    """Return deduplicated local songs with title/artist matching the query."""
    qlow = query.lower()
    seen_titles = set()  # Track seen title+artist combinations
    out = []
    
    for sid, meta in local_songs.items():
        title_artist = (meta["title"].lower(), meta["artist"].lower())
        
        if (qlow in meta["title"].lower() or qlow in meta["artist"].lower()) and \
           title_artist not in seen_titles:
            out.append(meta)
            seen_titles.add(title_artist)
    
    return out

@lru_cache(maxsize=100)
def search_songs(query: str):
    """YTMusic search (songs) with deduplication, cached for 1 hour."""
    now_ts = datetime.now().timestamp()
    if query in search_cache:
        old_data, old_ts = search_cache[query]
        if now_ts - old_ts < CACHE_DURATION:
            return old_data
            
    try:
        raw = ytmusic.search(query, filter="songs")
        seen_titles = set()  # Track seen title+artist combinations
        results = []
        
        for item in raw:
            vid = item.get("videoId")
            if not vid:
                continue
                
            artist = "Unknown Artist"
            if item.get("artists"):
                artist = item["artists"][0].get("name", "Unknown Artist")
                
            title = item.get("title", "Unknown")
            title_artist = (title.lower(), artist.lower())
            
            # Skip if we've seen this title+artist combination
            if title_artist in seen_titles:
                continue
                
            dur = item.get("duration_seconds", 0)
            thumb = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
            
            results.append({
                "id": vid,
                "title": title,
                "artist": artist,
                "album": "",
                "duration": dur,
                "thumbnail": thumb
            })
            
            seen_titles.add(title_artist)
            
        search_cache[query] = (results, now_ts)
        return results
        
    except Exception as e:
        logger.error(f"search_songs error: {e}")
        return []

def fallback_recommendations():
    """Simplified fallback using search instead of unavailable methods."""
    try:
        categories = [
            "top hits",
            "popular music",
            "trending songs",
            "new releases",
            "viral hits"
        ]
        
        recommendations = []
        seen_songs = set()
        
        # Try 2 random categories
        selected_cats = random.sample(categories, 2)
        
        for query in selected_cats:
            results = ytmusic.search(query, filter="songs", limit=10)
            if results:
                selected = random.sample(results, min(3, len(results)))
                for track in selected:
                    add_recommendation(track, recommendations, seen_songs)
                    if len(recommendations) >= 5:
                        break
        
        random.shuffle(recommendations)
        return jsonify(recommendations[:5])
        
    except Exception as e:
        logger.error(f"Fallback recommendations error: {e}")
        return jsonify([])


def get_local_song_recommendations(local_song_id):
    """Get recommendations for local songs using title/artist search."""
    try:
        local_meta = local_songs.get(local_song_id)
        if not local_meta:
            return fallback_recommendations()
            
        recommendations = []
        seen_songs = set()
        
        # Search using song title and artist
        query = f"{local_meta['title']} {local_meta['artist']}"
        search_results = ytmusic.search(query, filter="songs", limit=15)
        
        for track in search_results:
            if add_recommendation(track, recommendations, seen_songs):
                if len(recommendations) >= 5:
                    break
                    
        # If we need more, add some popular songs
        if len(recommendations) < 5:
            popular = ytmusic.search("popular music", filter="songs", limit=10)
            for track in popular:
                if add_recommendation(track, recommendations, seen_songs):
                    if len(recommendations) >= 5:
                        break
                        
        random.shuffle(recommendations)
        return jsonify(recommendations[:5])
        
    except Exception as e:
        logger.error(f"Local recommendations error: {e}")
        return fallback_recommendations()
def add_recommendation(track, recommendations, seen_songs, current_song_id=None):
    """Enhanced track processing with better validation."""
    try:
        video_id = track.get("videoId")
        if not video_id:
            return False

        # Skip if song is current or recently played
        if video_id in seen_songs or video_id == current_song_id:
            return False

        # Skip unavailable or private videos
        if track.get("isAvailable") == False or track.get("isPrivate") == True:
            return False

        # Get track details with validation
        title = track.get("title", "").strip()
        if not title or title == "Unknown":
            return False

        artist = "Unknown Artist"
        if "artists" in track and track["artists"]:
            artist = track["artists"][0].get("name", "").strip()
        elif track.get("artist"):
            artist = track["artist"].strip()

        # Skip if we couldn't get valid title/artist
        if not title or not artist or artist == "Unknown Artist":
            return False

        album = ""
        if "album" in track and isinstance(track["album"], dict):
            album = track["album"].get("name", "").strip()

        thumb = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
        duration = int(track.get("duration_seconds", 0))

        # Skip very short or very long tracks
        if duration < 30 or duration > 1800:  # Between 30s and 30m
            return False

        # Add to recommendations and mark as seen
        recommendations.append({
            "id": video_id,
            "title": title,
            "artist": artist,
            "album": album,
            "thumbnail": thumb,
            "duration": duration
        })
        seen_songs.add(video_id)
        return True

    except Exception as e:
        logger.warning(f"Error processing track: {e}")
        return False
def cleanup_expired_sessions():
    """Remove expired sessions from database"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM active_sessions WHERE expires_at <= CURRENT_TIMESTAMP")
    conn.commit()
    conn.close()


def get_fallback_tracks(seen_songs):
    """Get fallback tracks from trending/popular songs or charts."""
    try:
        fallback_tracks = []

        # Try trending
        trending = ytmusic.get_trending_music()
        if trending:
            for track in trending:
                add_recommendation(track, fallback_tracks, seen_songs)

        # If still need more, use charts
        if len(fallback_tracks) < 5:
            charts = ytmusic.get_charts()
            if charts and "items" in charts:
                for track in charts["items"]:
                    add_recommendation(track, fallback_tracks, seen_songs)
        return fallback_tracks
    except Exception as e:
        logger.warning(f"Fallback tracks error: {e}")
        return []


@lru_cache(maxsize=1000)
@login_required
def fetch_image(url):
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return response.content, response.headers.get('Content-Type', 'image/jpeg')
    except Exception as e:
        logger.error(f"Error fetching image {url}: {e}")
    return None, None

def get_listening_patterns(c) -> Dict[str, Any]:
    """Analyze listening patterns with proper data validation."""
    try:
        # Initialize patterns with zeros
        hourly_pattern = {str(h).zfill(2): 0 for h in range(24)}
        daily_pattern = {str(d): 0 for d in range(7)}
        
        # Get hourly stats
        c.execute("""
            SELECT 
                strftime('%H', started_at) as hour,
                COUNT(*) as plays
            FROM listening_history
            WHERE started_at IS NOT NULL
            GROUP BY hour
            ORDER BY hour
        """)
        
        for hour, plays in c.fetchall():
            if hour in hourly_pattern:
                hourly_pattern[hour] = plays
        
        # Get daily stats
        c.execute("""
            SELECT 
                strftime('%w', started_at) as day,
                COUNT(*) as plays
            FROM listening_history
            WHERE started_at IS NOT NULL
            GROUP BY day
            ORDER BY day
        """)
        
        for day, plays in c.fetchall():
            if day in daily_pattern:
                daily_pattern[day] = plays
        
        return {
            "hourly": hourly_pattern,
            "daily": daily_pattern
        }
        
    except Exception as e:
        logger.error(f"Error getting listening patterns: {e}")
        return {
            "hourly": {str(h).zfill(2): 0 for h in range(24)},
            "daily": {str(d): 0 for d in range(7)}
        }
    
def safe_int(value, default=0):
    """Safely convert value to int."""
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default

# Modify get_completion_rates to handle missing data gracefully
def get_completion_rates(c) -> Dict[str, Any]:
    """Analyze song completion rates with better error handling."""
    try:
        # Get completion distribution
        c.execute("""
            SELECT 
                COALESCE(listen_type, 'partial') as type,
                COUNT(*) as count
            FROM listening_history
            WHERE listen_type IS NOT NULL
            GROUP BY listen_type
            ORDER BY count DESC
        """)
        
        completion_stats = {
            'full': 0,
            'partial': 0,
            'skip': 0
        }
        
        rows = c.fetchall()
        if rows:
            for listen_type, count in rows:
                if listen_type in completion_stats:
                    completion_stats[listen_type] = count
        
        # Get average completion rate
        c.execute("""
            SELECT AVG(completion_rate)
            FROM listening_history
            WHERE completion_rate IS NOT NULL
            AND completion_rate BETWEEN 0 AND 100
        """)
        
        avg_completion = c.fetchone()[0]
        avg_completion = round(float(avg_completion) if avg_completion is not None else 0, 2)
        
        return {
            "completion_distribution": completion_stats,
            "average_completion": avg_completion
        }
        
    except Exception as e:
        logger.error(f"Error getting completion rates: {e}")
        return {
            "completion_distribution": {'full': 0, 'partial': 0, 'skip': 0},
            "average_completion": 0
        }



def get_overview_stats(c) -> Dict[str, Any]:
    """Get overall listening statistics."""
    # Total listening time
    c.execute("SELECT SUM(listened_duration) FROM listening_history")
    total_time = c.fetchone()[0] or 0
    
    # Total songs played
    c.execute("SELECT COUNT(*) FROM listening_history")
    total_songs = c.fetchone()[0] or 0
    
    # Unique artists
    c.execute("SELECT COUNT(DISTINCT artist) FROM listening_history")
    unique_artists = c.fetchone()[0] or 0
    
    return {
        "total_time": total_time,
        "total_songs": total_songs,
        "unique_artists": unique_artists,
        "average_daily": total_songs / max(1, (datetime.now() - datetime.strptime(get_first_listen_date(c), '%Y-%m-%d')).days)
    }

def get_top_artists(c) -> List[Dict[str, Any]]:
    """Get top artists by listening time."""
    c.execute("""
        SELECT 
            artist,
            total_plays,
            total_time,
            first_played,
            last_played
        FROM artist_stats
        ORDER BY total_time DESC
        LIMIT 10
    """)
    
    return [{
        "name": row[0],
        "plays": row[1],
        "time": row[2],
        "first_played": row[3],
        "last_played": row[4]
    } for row in c.fetchall()]



def get_completion_rates(c) -> Dict[str, Any]:
    """Analyze song completion rates."""
    c.execute("""
        SELECT 
            listen_type,
            COUNT(*) as count
        FROM listening_history
        GROUP BY listen_type
    """)
    
    completion_stats = dict(c.fetchall())
    
    return {
        "completion_distribution": completion_stats,
        "average_completion": get_average_completion(c)
    }

def get_first_listen_date(c) -> str:
    """Get the date of first listen."""
    c.execute("SELECT MIN(date) FROM daily_stats")
    return c.fetchone()[0] or datetime.now().strftime('%Y-%m-%d')

def get_average_completion(c) -> float:
    """Calculate average completion rate."""
    c.execute("SELECT AVG(completion_rate) FROM listening_history")
    return round(c.fetchone()[0] or 0, 2)


def record_listen_end(listen_id: int, duration: int, listened_duration: int):
    """Record the end of a song listen with analytics."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    try:
        # Handle null/invalid duration
        try:
            duration = int(float(duration or 0))
            listened_duration = int(float(listened_duration or 0))
        except (TypeError, ValueError):
            duration = 0
            listened_duration = 0
        
        # Ensure we don't divide by zero
        completion_rate = (listened_duration / duration) * 100 if duration > 0 else 0
        listen_type = 'full' if completion_rate >= 85 else 'skip' if completion_rate <= 20 else 'partial'
        
        c.execute("""
            UPDATE listening_history
            SET ended_at = CURRENT_TIMESTAMP,
                duration = ?,
                listened_duration = ?,
                completion_rate = ?,
                listen_type = ?
            WHERE id = ?
        """, (duration, listened_duration, completion_rate, listen_type, listen_id))
        
        # Update daily stats
        update_daily_stats(c, duration, listened_duration)
        
        # Update artist stats
        c.execute("SELECT artist FROM listening_history WHERE id = ?", (listen_id,))
        artist = c.fetchone()[0]
        update_artist_stats(c, artist, duration, listened_duration)
        
        conn.commit()
    finally:
        conn.close()

def record_listen_start(song_id: str, title: str, artist: str, session_id: str) -> int:
    """Record listen start with accurate IST timestamp."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    try:
        # Get current IST time
        current_time = time_sync.get_current_time()
        
        # Ensure all strings are stripped
        song_id = str(song_id).strip()
        title = str(title).strip()
        artist = str(artist).strip()
        session_id = str(session_id).strip()
        
        c.execute("""
            INSERT INTO listening_history 
            (song_id, title, artist, session_id, started_at)
            VALUES (?, ?, ?, ?, ?)
        """, (song_id, title, artist, session_id, current_time.strftime('%Y-%m-%d %H:%M:%S')))
        
        listen_id = c.lastrowid
        conn.commit()
        return listen_id
    finally:
        conn.close()


@login_required
def update_artist_stats(c, artist: str, duration: int, listened_duration: int):
    """Update artist listening statistics."""
    c.execute("""
        INSERT INTO artist_stats (
            artist, total_plays, total_time, first_played, last_played
        )
        VALUES (?, 1, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(artist) DO UPDATE SET
            total_plays = total_plays + 1,
            total_time = total_time + ?,
            last_played = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
    """, (artist, listened_duration, listened_duration))
@login_required
def update_daily_stats(c, duration: int, listened_duration: int):
    """Update aggregated daily statistics."""
    today = datetime.now().strftime('%Y-%m-%d')
    
    c.execute("""
        INSERT INTO daily_stats (date, total_songs, total_time)
        VALUES (?, 1, ?)
        ON CONFLICT(date) DO UPDATE SET
            total_songs = total_songs + 1,
            total_time = total_time + ?,
            updated_at = CURRENT_TIMESTAMP
    """, (today, listened_duration, listened_duration))


def generate_otp():
    """Generate a 6-digit OTP"""
    return ''.join([str(secrets.randbelow(10)) for _ in range(6)])
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def store_otp(email, otp, purpose):
    """Store OTP in database"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    expires_at = datetime.now() + timedelta(minutes=10)
    
    # Clear any existing OTPs for this email/purpose
    c.execute("""
        DELETE FROM pending_otps 
        WHERE email = ? AND purpose = ?
    """, (email, purpose))
    
    c.execute("""
        INSERT INTO pending_otps (email, otp, purpose, expires_at)
        VALUES (?, ?, ?, ?)
    """, (email, otp, purpose, expires_at))
    
    conn.commit()
    conn.close()

def verify_otp(email, otp, purpose):
    """Verify OTP from database"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("""
        SELECT otp FROM pending_otps
        WHERE email = ? AND purpose = ?
        AND expires_at > CURRENT_TIMESTAMP
        ORDER BY created_at DESC LIMIT 1
    """, (email, purpose))
    
    row = c.fetchone()
    valid = row and row[0] == otp
    
    if valid:
        c.execute("""
            DELETE FROM pending_otps
            WHERE email = ? AND purpose = ?
        """, (email, purpose))
        
    conn.commit()
    conn.close()
    return valid


def download_default_songs():
    default_songs = ["dQw4w9WgXcQ", "kJQP7kiw5Fk", "9bZkp7q19f0"]
    for song_id in default_songs:
        flac_path = os.path.join(MUSIC_DIR, f"{song_id}.flac")
        if not os.path.exists(flac_path):
            download_flac_init(song_id)



def send_email(to_email, subject, body):
    """Send HTML email using SMTP"""
    try:
        msg = MIMEMultipart('alternative')
        msg['From'] = SMTP_USER
        msg['To'] = to_email
        msg['Subject'] = subject
        html_part = MIMEText(body, 'html')
        msg.attach(html_part)
        
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False
    

from yt_dlp import YoutubeDL
import subprocess
import platform
import sqlite3
import os
import logging

logger = logging.getLogger(__name__)

def download_flac(video_id: str, user_id: int) -> str:
    """
    Download song with metadata and thumbnail using yt-dlp.exe with fallback to yt-dlp module.
    
    Args:
        video_id: str - The YouTube video ID
        user_id: int - The ID of the user downloading the song
        
    Returns:
        str: Path to the FLAC file if successful or existing, None if failed
    """
    try:
        # Check for existing download
        existing_path = get_download_info(video_id)
        if existing_path:
            if os.path.exists(existing_path):
                logger.info(f"Using existing download for {video_id}")
                load_local_songs()
                return existing_path
            else:
                # Clean up DB if file is missing
                load_local_songs()
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("DELETE FROM downloads WHERE video_id = ?", (video_id,))
                conn.commit()
                conn.close()

        flac_path = os.path.join(MUSIC_DIR, f"{video_id}.flac")
        
        if os.path.exists(flac_path):
            return flac_path

        logger.info(f"Downloading new song: {video_id}")
        yt_music_url = f"https://music.youtube.com/watch?v={video_id}"

        # Try executable first
        try:
            return download_with_executable(video_id, user_id, yt_music_url, flac_path, is_init=False)
        except Exception as exe_error:
            logger.warning(f"Executable download failed, falling back to module: {str(exe_error)}")
            return download_with_module(video_id, user_id, yt_music_url, flac_path, is_init=False)

    except Exception as e:
        logger.error(f"Error downloading song {video_id}: {str(e)}")
        return None

def download_flac_init(video_id: str) -> str:
    """
    Version of download_flac that works during initialization with fallback to yt-dlp module.
    
    Args:
        video_id: str - The YouTube video ID
        
    Returns:
        str: Path to the FLAC file if successful or existing, None if failed
    """
    try:
        # Check for existing download
        existing_path = get_download_info(video_id)
        if existing_path and os.path.exists(existing_path):
            logger.info(f"Using existing download for {video_id}")
            return existing_path

        flac_path = os.path.join(MUSIC_DIR, f"{video_id}.flac")
        
        if os.path.exists(flac_path):
            return flac_path

        logger.info(f"Downloading new song during initialization: {video_id}")
        yt_music_url = f"https://music.youtube.com/watch?v={video_id}"

        # Try executable first
        try:
            return download_with_executable(video_id, None, yt_music_url, flac_path, is_init=True)
        except Exception as exe_error:
            logger.warning(f"Executable download failed during init, falling back to module: {str(exe_error)}")
            return download_with_module(video_id, None, yt_music_url, flac_path, is_init=True)

    except Exception as e:
        logger.error(f"Error downloading song {video_id} during initialization: {str(e)}")
        return None

def download_with_executable(video_id: str, user_id: int | None, url: str, flac_path: str, is_init: bool) -> str:
    """Helper function to download using yt-dlp executable"""
    # Get metadata first
    result = subprocess.run([
        YTDLP_PATH,
        "--quiet",
        "--print", "%(title)s",
        "--print", "%(artist)s",
        "--print", "%(album)s",
        url
    ], capture_output=True, text=True)
    
    if result.returncode != 0:
        raise Exception(f"Metadata extraction failed: {result.stderr}")
        
    title, artist, album = result.stdout.strip().split("\n")

    command = [
        YTDLP_PATH,
        "--quiet",
        "--no-warnings",
        "--extract-audio",
        "--audio-format", "flac",
        "--audio-quality", "0",
        "--embed-metadata",
        "--embed-thumbnail",
        "-o", os.path.join(MUSIC_DIR, "%(id)s.%(ext)s"),
    ]
    
    # Only add ffmpeg path on Windows
    if platform.system() == "Windows":
        command.extend(["--ffmpeg-location", FFMPEG_BIN_DIR])
    
    command.append(url)
    
    download_result = subprocess.run(command)

    if download_result.returncode == 0 and os.path.exists(flac_path):
        if not is_init:
            record_download(video_id, title, artist, album, flac_path, user_id)
            load_local_songs()
        logger.info(f"Successfully downloaded {video_id} using executable")
        return flac_path
        
    raise Exception(f"Executable download failed with code {download_result.returncode}")

def download_with_module(video_id: str, user_id: int | None, url: str, flac_path: str, is_init: bool) -> str:
    """Helper function to download using yt-dlp Python module with optimized settings"""
    ydl_opts = {
        # Basic options
        'format': 'bestaudio/best',  # Get best quality audio
        'outtmpl': os.path.join(MUSIC_DIR, '%(id)s.%(ext)s'),
        
        # Audio processing
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'flac',
            'preferredquality': '0',  # Best quality
            'nopostoverwrites': False,  # Allow overwriting postprocessed files
        }, {
            # Add metadata
            'key': 'FFmpegMetadata',
            'add_metadata': True,
            'add_chapters': True,
        }, {
            # Add thumbnail
            'key': 'EmbedThumbnail',
            'already_have_thumbnail': False,
        }],
        
        # Additional options
        'writethumbnail': True,  # Write thumbnail to disk before embedding
        'embedthumbnail': True,  # Embed thumbnail in audio file
        'addmetadata': True,     # Write metadata to file
        'prefer_ffmpeg': True,   # Prefer ffmpeg for post-processing
        
        # Quality settings
        'audioformat': 'flac',   # Force FLAC format
        'audioquality': '0',     # Best quality
        
        # Optimization settings
        'concurrent_fragment_downloads': 1,  # Download fragments concurrently
        'retries': 10,           # Retry on download errors
        'fragment_retries': 10,  # Retry on fragment download errors
        
        # Output settings
        'extract_flat': False,   # Extract audio
        'keepvideo': False,      # Don't keep video file after extraction
        'clean_infojson': True,  # Remove info json after download
        
        # Progress settings
        'progress_hooks': [],    # Can add progress tracking if needed
        'postprocessor_hooks': [], # Can add post-processing tracking
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            # Extract metadata first
            info = ydl.extract_info(url, download=False)
            title = info.get('title', '')
            artist = info.get('artist', '')
            album = info.get('album', '')
            
            # Get additional metadata if available
            track = info.get('track', '')
            release_year = info.get('release_year', '')
            release_date = info.get('release_date', '')
            genre = info.get('genre', '')
            
            # Download and process the file
            ydl.download([url])
            
            if os.path.exists(flac_path):
                if not is_init:
                    # Record download with extended metadata
                    record_download(
                        video_id=video_id,
                        title=title or track or "Unknown Title",
                        artist=artist or "Unknown Artist",
                        album=album or "Unknown Album",
                        path=flac_path,
                        user_id=user_id
                    )
                    load_local_songs()
                logger.info(f"Successfully downloaded {video_id} using module")
                return flac_path
                
            raise Exception("Module download failed - file not found")
            
    except Exception as e:
        logger.error(f"Download error for {video_id}: {str(e)}")
        raise Exception(f"Download failed: {str(e)}")
