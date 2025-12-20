# config.py
import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Token del bot (OBLIGATORIO - obtener de @BotFather)
TOKEN = os.getenv("TOKEN", "TU_TOKEN_AQUÍ")

# Tu user_id como administrador (OBLIGATORIO)
# Para obtener tu user_id: envía /start a @userinfobot
ADMIN_ID = int(os.getenv("ADMIN_ID", 123456789))  # Reemplaza con tu ID real

# Configuración de descargas
DOWNLOAD_PATH = "downloads"
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB (límite de Telegram Bot API)

# Configuración de logs
ENABLE_LOGS = True
LOG_FILE = "bot_logs.log"

# Tiempo de espera entre actualizaciones de progreso (segundos)
UPDATE_INTERVAL = 3