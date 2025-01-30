# Sangeet Premium 🎵
<p align="center">
  <img src="promo/logo.png" alt="Sangeet Premium Logo" width="600" height="560"/>
</p>

A modern, open-source music player with a stunning user interface, smart recommendations, and high-quality audio streaming - completely free forever.

## 🌟 Why Sangeet Premium?
In today's digital music landscape, listeners face several challenges:
- Major streaming platforms charge premium fees for high-quality audio
- Expensive subscription models with restrictive features
- Limited control over music organization and playback
- Closed ecosystems that lock users into specific platforms
- Algorithmic recommendations that often prioritize promoted content

Sangeet Premium solves these issues by providing:
- Completely free, high-quality audio streaming
- Beautiful, responsive user interface
- Advanced music recommendation system
- Full control over your music library
- No ads, no subscriptions, no limitations

## 🚀 Quick Start Guide



### 1. Installation Steps
```bash
# Clone the repository
git clone https://github.com/easy-ware/Sangeet-Premium.git
cd Sangeet-Premium
```
### 2. Setup Environment
First, create a `/config/.env` file in the root directory with the following configuration:
```env
# Flask Configuration
SECRET_KEY=ff257edd0e5b03a53a3868b41985cad5fc0814636e82aeec3321bba47e7f97bb

# AES Key Configuration
AES_KEY=UTaXsZbx-H1CA2JEy6mKlpX1jd2AfiMQKxp4u8uWlK0=

# SMTP Configuration
SMTP_USER=your.email@gmail.com
SMTP_PASSWORD="your-app-password"
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587

# Music Paths Configuration
LOCAL_SONGS_PATHS="path/to/songs1;path/to/songs2;music"
music_path="music"  # Directory where downloaded audio will be saved

# Server Configuration
sangeet_backend=http://127.0.0.1:7800
port=7800
```

### 3. Setup Environment

Also install the depedencies like ffmpeg , cloudflared for your system if termux or arm..


# Run the application
```
python run_server.py
# or
python3 run_server.py
```
# If got issues then simply
```
pip install -r requirements/req.txt
python sangeet_server.py
# or
python3 sangeet_server.py
```
## ✨ Features
- **Stunning UI/UX**: Modern, intuitive interface with smooth animations
- **Smart Recommendations**: AI-powered music suggestions based on your taste
- **High-Quality Audio**: Crystal clear audio streaming with no compromises
- **Library Management**: Organize your music collection effortlessly
- **Cross-Platform**: Available on Windows, macOS, and Linux
- **Offline Mode**: Download your favorite tracks for offline listening
- **Last.fm Integration**: Scrobble your listening history
- **Customizable Themes**: Personalize your player's appearance
- **Lyrics Support**: Real-time synchronized lyrics
- **Smart Login System**: Real-time login system

## 🛠️ Tech Stack
- Python 3.11+
- Flask for backend
- HTML, CSS, JavaScript
- SQLite for database
- FFmpeg for audio processing
- Yt-Dlp for media handling
## Warning
Only accesa the sangeet on other devices via the generated cloudflared .trycloudflare.com tunnel else local ips like 192.168.0.1 like not work..
## 🤝 Contributing
We welcome contributions! Please feel free to submit pull requests.

## 📜 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments
- All the open-source libraries and tools used in this project

## 📧 Contact
- GitHub: [Easy Ware](https://github.com/easy-ware)

---
<p align="center">
  Made with ❤️ by the Sangeet Premium Owner easy-ware
</p>
