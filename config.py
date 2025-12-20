# config.py - CONFIGURACIÓN SIMPLIFICADA
import os

# Token del bot (obtener de @BotFather)
TOKEN = "8530361444:AAFZ-yZIFzDC0CVUvX-W14kTZGVKFITGBCE"

# Configuración de descargas
DOWNLOAD_PATH = "downloads"
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB límite de Telegram

# Cache settings
CACHE_ENABLED = True
CACHE_TTL_MINUTES = 60  # 1 hora
CACHE_DIR = "cache"

# Thumbnail settings
GENERATE_THUMBNAILS = True
THUMBNAIL_WIDTH = 320

# Retry settings
MAX_RETRIES = 3
RETRY_DELAY = 2  # segundos

# Progress update interval (seconds)
PROGRESS_UPDATE_INTERVAL = 3