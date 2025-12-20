# main.py
import os
import logging
import json
import re
import time
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

import yt_dlp
from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
    MessageEntity
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    TypeHandler,
    ApplicationHandlerStop
)

import config

# ==================== CONFIGURACIÓN ====================
TOKEN = config.TOKEN
ADMIN_ID = config.ADMIN_ID
DOWNLOAD_PATH = config.DOWNLOAD_PATH
MAX_FILE_SIZE = config.MAX_FILE_SIZE

# Crear directorio de descargas
Path(DOWNLOAD_PATH).mkdir(exist_ok=True)

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler(config.LOG_FILE) if config.ENABLE_LOGS else logging.StreamHandler(),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==================== GESTIÓN DE USUARIOS ====================
class UserManager:
    """Gestiona usuarios permitidos."""
    
    def __init__(self, file_path: str = "allowed_users.json"):
        self.file_path = file_path
        self.allowed_users: Set[int] = set()
        self.load_users()
    
    def load_users(self):
        """Carga usuarios permitidos desde archivo JSON."""
        try:
            if os.path.exists(self.file_path):
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.allowed_users = set(data.get('allowed_users', []))
                    logger.info(f"Usuarios cargados: {len(self.allowed_users)}")
            else:
                self.save_users()
        except Exception as e:
            logger.error(f"Error cargando usuarios: {e}")
            self.allowed_users = set()
    
    def save_users(self):
        """Guarda usuarios permitidos en archivo JSON."""
        try:
            data = {
                'allowed_users': list(self.allowed_users),
                'last_updated': datetime.now().isoformat()
            }
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error guardando usuarios: {e}")
    
    def add_user(self, user_id: int) -> bool:
        """Agrega un usuario a la lista."""
        if user_id not in self.allowed_users:
            self.allowed_users.add(user_id)
            self.save_users()
            logger.info(f"Usuario agregado: {user_id}")
            return True
        return False
    
    def remove_user(self, user_id: int) -> bool:
        """Remueve un usuario de la lista."""
        if user_id in self.allowed_users:
            self.allowed_users.remove(user_id)
            self.save_users()
            logger.info(f"Usuario removido: {user_id}")
            return True
        return False
    
    def is_allowed(self, user_id: int) -> bool:
        """Verifica si un usuario tiene permiso."""
        return user_id in self.allowed_users or user_id == ADMIN_ID
    
    def list_users(self) -> List[int]:
        """Retorna lista de usuarios permitidos."""
        return sorted(list(self.allowed_users))
    
    def count_users(self) -> int:
        """Retorna cantidad de usuarios permitidos."""
        return len(self.allowed_users)

# Instancia global
user_manager = UserManager()

# ==================== VALIDACIÓN DE URLS ====================
def extract_urls(text: str) -> List[str]:
    """Extrae todas las URLs de un texto."""
    url_pattern = r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[/\w\.\-?=&%+#@!]*'
    return re.findall(url_pattern, text)

def validate_url(url: str) -> Tuple[bool, Optional[str]]:
    """Valida una URL y detecta la plataforma."""
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return False, None
        
        # Detectar plataforma
        domain = parsed.netloc.lower()
        if 'youtube.com' in domain or 'youtu.be' in domain:
            return True, 'YouTube'
        elif 'tiktok.com' in domain:
            return True, 'TikTok'
        elif 'instagram.com' in domain:
            return True, 'Instagram'
        elif 'twitter.com' in domain or 'x.com' in domain:
            return True, 'Twitter/X'
        elif 'facebook.com' in domain or 'fb.com' in domain:
            return True, 'Facebook'
        elif 'reddit.com' in domain:
            return True, 'Reddit'
        else:
            return True, 'Otro'
    
    except Exception:
        return False, None

# ==================== FUNCIONES DE yt-dlp ====================
def get_video_info(url: str) -> Optional[Dict]:
    """Obtiene información del video usando yt-dlp."""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info
    except Exception as e:
        logger.error(f"Error obteniendo info de {url}: {e}")
        return None

def get_available_formats(video_info: Dict) -> Dict:
    """Extrae formatos disponibles del video."""
    formats = {'video': [], 'audio': []}
    
    if 'formats' not in video_info:
        return formats
    
    # Procesar formatos de video
    video_formats_seen = set()
    for fmt in video_info['formats']:
        # Formato de video (tiene video y audio)
        if fmt.get('vcodec') != 'none' and fmt.get('acodec') != 'none':
            height = fmt.get('height', 0)
            ext = fmt.get('ext', 'mp4')
            format_note = fmt.get('format_note', '')
            
            if height > 0:
                key = f"{height}p-{ext}"
                if key not in video_formats_seen:
                    video_formats_seen.add(key)
                    formats['video'].append({
                        'height': height,
                        'ext': ext,
                        'format_note': format_note,
                        'format_id': fmt['format_id'],
                        'filesize': fmt.get('filesize', 0),
                        'quality_label': f"{height}p" + (f" ({format_note})" if format_note else "")
                    })
        
        # Formato de audio (solo audio)
        elif fmt.get('acodec') != 'none' and fmt.get('vcodec') == 'none':
            abr = fmt.get('abr', 0)
            ext = fmt.get('ext', 'mp3')
            
            if abr > 0:
                formats['audio'].append({
                    'abr': abr,
                    'ext': ext,
                    'format_id': fmt['format_id'],
                    'filesize': fmt.get('filesize', 0),
                    'quality_label': f"{ext.upper()} {abr}kbps"
                })
    
    # Ordenar formatos
    formats['video'].sort(key=lambda x: x['height'], reverse=True)
    formats['audio'].sort(key=lambda x: x['abr'], reverse=True)
    
    return formats

# ==================== CREACIÓN DE BOTONES ====================
def create_main_menu() -> InlineKeyboardMarkup:
    """Crea el menú principal."""
    keyboard = [
        [InlineKeyboardButton("🎬 Descargar Video", callback_data="menu_video")],
        [InlineKeyboardButton("🎵 Descargar Solo Audio", callback_data="menu_audio")],
        [InlineKeyboardButton("📊 Ver Formatos Disponibles", callback_data="menu_formats")],
        [InlineKeyboardButton("❓ Ayuda", callback_data="menu_help")]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_video_quality_menu(formats: List[Dict]) -> InlineKeyboardMarkup:
    """Crea menú de calidades de video."""
    keyboard = []
    
    # Agrupar en filas de 2 botones
    for i in range(0, len(formats), 2):
        row = []
        for j in range(2):
            if i + j < len(formats):
                fmt = formats[i + j]
                quality = fmt['quality_label']
                row.append(InlineKeyboardButton(quality, callback_data=f"dl_video_{fmt['format_id']}"))
        if row:
            keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("⬅️ Volver al Menú", callback_data="back_to_main")])
    return InlineKeyboardMarkup(keyboard)

def create_audio_format_menu(formats: List[Dict]) -> InlineKeyboardMarkup:
    """Crea menú de formatos de audio."""
    keyboard = []
    
    for i in range(0, len(formats), 2):
        row = []
        for j in range(2):
            if i + j < len(formats):
                fmt = formats[i + j]
                quality = fmt['quality_label']
                row.append(InlineKeyboardButton(quality, callback_data=f"dl_audio_{fmt['format_id']}"))
        if row:
            keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("⬅️ Volver al Menú", callback_data="back_to_main")])
    return InlineKeyboardMarkup(keyboard)

def create_help_keyboard() -> InlineKeyboardMarkup:
    """Crea teclado para ayuda."""
    keyboard = [
        [InlineKeyboardButton("📋 Ver mi Información", callback_data="my_info")],
        [InlineKeyboardButton("⬅️ Volver al Menú", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ==================== MIDDLEWARE DE PERMISOS ====================
async def check_permission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verifica permisos del usuario."""
    user_id = update.effective_user.id
    
    # Permitir comandos públicos siempre
    if update.message and update.message.text:
        text = update.message.text.lower()
        if text.startswith(('/start', '/myinfo', '/ayuda')):
            return
    
    # Verificar si el usuario tiene permiso
    if not user_manager.is_allowed(user_id):
        # Crear mensaje informativo
        user = update.effective_user
        info_text = (
            f"❌ *No tienes permiso para usar este bot*\n\n"
            f"📝 *Para solicitar acceso:*\n"
            f"Envía tu información al administrador @landitho9\n\n"
            f"📋 *Tu información:*\n"
            f"• User ID: `{user.id}`\n"
            f"• Nombre: {user.first_name}\n"
            f"• Username: @{user.username if user.username else 'No disponible'}\n\n"
            f"Usa /myinfo para copiar esta información fácilmente."
        )
        
        # Enviar mensaje y detener procesamiento
        if update.message:
            await update.message.reply_text(info_text, parse_mode='Markdown')
        elif update.callback_query:
            await update.callback_query.message.reply_text(info_text, parse_mode='Markdown')
        
        raise ApplicationHandlerStop

# ==================== COMANDOS PÚBLICOS ====================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start - Para todos los usuarios."""
    user = update.effective_user
    
    # Verificar si tiene permiso
    has_access = user_manager.is_allowed(user.id)
    
    if has_access:
        welcome_text = (
            f"👋 ¡Hola {user.first_name}!\n\n"
            f"✅ *Tienes acceso al bot*\n\n"
            f"📥 *Cómo usar:*\n"
            f"1. Envíame un enlace de video\n"
            f"2. Selecciona una opción del menú\n"
            f"3. Elige calidad/formato\n"
            f"4. Espera la descarga\n\n"
            f"🔗 *Soporto:* YouTube, TikTok, Instagram, Twitter/X, Facebook, Reddit, etc.\n\n"
            f"Usa /ayuda para más información."
        )
        
        await update.message.reply_text(welcome_text, parse_mode='Markdown')
    
    else:
        # Usuario sin permiso
        keyboard = [
            [
                InlineKeyboardButton(
                    "📋 Copiar mi User ID",
                    callback_data=f"copy_id_{user.id}"
                )
            ]
        ]
        
        if user.username:
            keyboard[0].append(
                InlineKeyboardButton(
                    "📋 Copiar mi @username",
                    callback_data=f"copy_user_{user.username}"
                )
            )
        
        keyboard.append([
            InlineKeyboardButton(
                "📋 Copiar toda mi información",
                callback_data=f"copy_all_{user.id}_{user.username or 'sin_username'}"
            )
        ])
        
        welcome_text = (
            f"👋 ¡Hola {user.first_name}!\n\n"
            f"🤖 *Bot Descargador de Videos*\n\n"
            f"⚠️ *No tienes permiso para usar este bot*\n\n"
            f"📝 *Para solicitar acceso:*\n"
            f"1. Copia tu información usando los botones abajo\n"
            f"2. Envíala al administrador @landitho9\n"
            f"3. Espera a que te agregue a la lista\n\n"
            f"✅ Una vez agregado, podrás usar todas las funciones."
        )
        
        await update.message.reply_text(
            welcome_text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def myinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /myinfo - Muestra información del usuario."""
    user = update.effective_user
    has_access = user_manager.is_allowed(user.id)
    
    info_text = (
        f"📋 *Tu información:*\n\n"
        f"🆔 *User ID:* `{user.id}`\n"
        f"👤 *Nombre:* {user.first_name}\n"
        f"📛 *Username:* @{user.username if user.username else 'No disponible'}\n"
        f"✅ *Estado:* {'PERMITIDO ✅' if has_access else 'NO PERMITIDO ❌'}\n\n"
        f"📝 *Para solicitar acceso:*\n"
        f"Envía esta información a @landitho9"
    )
    
    keyboard = [[
        InlineKeyboardButton("📋 Copiar toda mi info", callback_data=f"copy_all_{user.id}_{user.username or 'sin_username'}")
    ]]
    
    await update.message.reply_text(
        info_text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def ayuda_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /ayuda - Muestra ayuda."""
    help_text = (
        "📚 *Ayuda - Bot Descargador*\n\n"
        "📥 *Cómo usar:*\n"
        "1. Envía un enlace de video\n"
        "2. Selecciona 'Descargar Video' o 'Descargar Audio'\n"
        "3. Elige la calidad/formato\n"
        "4. Espera a que se complete\n\n"
        "🔗 *Sitios soportados:*\n"
        "• YouTube\n• TikTok\n• Instagram\n• Twitter/X\n"
        "• Facebook\n• Reddit\n• Vimeo\n• Dailymotion\n"
        "• SoundCloud\n• Spotify\n• y muchos más\n\n"
        "⚠️ *Limitaciones:*\n"
        "• Máximo 50MB por archivo\n"
        "• Algunos videos pueden tener restricciones\n"
        "• Calidades dependen del video original\n\n"
        "🛠️ *Comandos disponibles:*\n"
        "/start - Iniciar el bot\n"
        "/myinfo - Ver tu información\n"
        "/ayuda - Esta ayuda\n\n"
        "👑 *Solicitar acceso:*\n"
        "Usa /myinfo para ver tu información y envíala a @landitho9"
    )
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

# ==================== COMANDOS DE ADMINISTRACIÓN ====================
async def admin_add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /adduser - Agrega un usuario (solo admin)."""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Solo el administrador puede usar este comando.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "📋 *Uso:* `/adduser <user_id>`\n\n"
            "Ejemplo: `/adduser 123456789`",
            parse_mode='Markdown'
        )
        return
    
    try:
        target_id = int(context.args[0])
        
        # No permitir agregarse a sí mismo (ya es admin)
        if target_id == ADMIN_ID:
            await update.message.reply_text("⚠️ El administrador ya tiene acceso completo.")
            return
        
        if user_manager.add_user(target_id):
            await update.message.reply_text(f"✅ Usuario `{target_id}` agregado correctamente.", parse_mode='Markdown')
            
            # Intentar notificar al usuario
            try:
                await context.bot.send_message(
                    chat_id=target_id,
                    text="🎉 ¡Felicidades!\n\n"
                         "✅ Has sido agregado a la lista de usuarios permitidos.\n"
                         "Ahora puedes usar el bot para descargar videos.\n\n"
                         "Envía /start para comenzar."
                )
            except:
                logger.warning(f"No se pudo notificar al usuario {target_id}")
        
        else:
            await update.message.reply_text(f"⚠️ El usuario `{target_id}` ya estaba en la lista.", parse_mode='Markdown')
    
    except ValueError:
        await update.message.reply_text("❌ El user_id debe ser un número.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def admin_remove_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /removeuser - Remueve un usuario (solo admin)."""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Solo el administrador puede usar este comando.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "📋 *Uso:* `/removeuser <user_id>`\n\n"
            "Ejemplo: `/removeuser 123456789`",
            parse_mode='Markdown'
        )
        return
    
    try:
        target_id = int(context.args[0])
        
        if user_manager.remove_user(target_id):
            await update.message.reply_text(f"✅ Usuario `{target_id}` removido correctamente.", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"⚠️ El usuario `{target_id}` no estaba en la lista.", parse_mode='Markdown')
    
    except ValueError:
        await update.message.reply_text("❌ El user_id debe ser un número.")

async def admin_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /listusers - Lista usuarios permitidos (solo admin)."""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Solo el administrador puede usar este comando.")
        return
    
    users = user_manager.list_users()
    
    if not users:
        await update.message.reply_text("📭 No hay usuarios en la lista.")
        return
    
    user_list = "\n".join([f"• `{uid}`" for uid in users])
    
    await update.message.reply_text(
        f"👥 *Usuarios permitidos:* ({len(users)})\n\n{user_list}",
        parse_mode='Markdown'
    )

async def admin_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /stats - Estadísticas del bot (solo admin)."""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Solo el administrador puede usar este comando.")
        return
    
    users_count = user_manager.count_users()
    
    stats_text = (
        f"📊 *Estadísticas del Bot*\n\n"
        f"👥 Usuarios permitidos: `{users_count}`\n"
        f"👑 Administrador: `{ADMIN_ID}` (@landitho9)\n"
        f"🕐 Última actualización: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"🔧 *Comandos de administración:*\n"
        f"• /adduser <id> - Agregar usuario\n"
        f"• /removeuser <id> - Remover usuario\n"
        f"• /listusers - Listar usuarios\n"
        f"• /stats - Ver estadísticas"
    )
    
    await update.message.reply_text(stats_text, parse_mode='Markdown')

# ==================== MANEJO DE URLS ====================
async def handle_url_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja mensajes que contienen URLs."""
    user_id = update.effective_user.id
    
    # Verificar permisos
    if not user_manager.is_allowed(user_id):
        return  # Ya fue manejado por el middleware
    
    # Extraer URLs del mensaje
    text = update.message.text or update.message.caption or ""
    urls = extract_urls(text)
    
    if not urls:
        await update.message.reply_text("No encontré URLs en tu mensaje.")
        return
    
    # Tomar la primera URL
    url = urls[0]
    
    # Validar URL
    is_valid, platform = validate_url(url)
    if not is_valid:
        await update.message.reply_text("❌ URL inválida. Asegúrate de que sea un enlace completo (con http:// o https://).")
        return
    
    # Mensaje de procesamiento
    processing_msg = await update.message.reply_text(
        f"🔍 *Analizando enlace...*\n\n"
        f"🌐 Plataforma: {platform}\n"
        f"⏳ Por favor espera...",
        parse_mode='Markdown'
    )
    
    # Obtener información del video
    video_info = get_video_info(url)
    
    if not video_info:
        await processing_msg.edit_text(
            "❌ *No se pudo obtener información*\n\n"
            "Posibles causas:\n"
            "• El video no existe\n"
            "• Está privado/eliminado\n"
            "• Requiere inicio de sesión\n"
            "• La plataforma no está soportada",
            parse_mode='Markdown'
        )
        return
    
    # Guardar información en context.user_data
    context.user_data['current_url'] = url
    context.user_data['video_info'] = video_info
    context.user_data['formats'] = get_available_formats(video_info)
    
    # Mostrar información y menú
    title = video_info.get('title', 'Sin título')
    duration = video_info.get('duration', 0)
    duration_str = f"{int(duration) // 60}:{int(duration) % 60:02d}" if duration > 0 else "Desconocida"
    uploader = video_info.get('uploader', 'Desconocido')
    
    info_text = (
        f"✅ *Información obtenida*\n\n"
        f"📹 *Título:* {title[:100]}...\n"
        f"⏱️ *Duración:* {duration_str}\n"
        f"👤 *Subido por:* {uploader}\n"
        f"🌐 *Plataforma:* {platform}\n\n"
        f"🎯 *Selecciona una opción:*"
    )
    
    await processing_msg.edit_text(
        info_text,
        parse_mode='Markdown',
        reply_markup=create_main_menu()
    )

# ==================== MANEJO DE CALLBACKS ====================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja todos los callbacks de botones."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    
    # Verificar permisos
    if not user_manager.is_allowed(user_id):
        await query.edit_message_text(
            "❌ *Sesión expirada o sin permisos*\n\n"
            "Usa /start para ver tu estado.",
            parse_mode='Markdown'
        )
        return
    
    # Menú principal
    if data == "back_to_main":
        if 'video_info' in context.user_data:
            video_info = context.user_data['video_info']
            title = video_info.get('title', 'Video')
            
            await query.edit_message_text(
                f"📹 *{title[:50]}...*\n\n"
                f"Selecciona una opción de descarga:",
                parse_mode='Markdown',
                reply_markup=create_main_menu()
            )
        else:
            await query.edit_message_text(
                "🎯 *Menú Principal*\n\n"
                "Envía un enlace para comenzar.",
                parse_mode='Markdown',
                reply_markup=create_main_menu()
            )
    
    elif data == "menu_video":
        if 'formats' not in context.user_data or not context.user_data['formats']['video']:
            await query.edit_message_text(
                "❌ No hay formatos de video disponibles.\n"
                "Intenta con otro enlace.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬅️ Volver", callback_data="back_to_main")
                ]])
            )
            return
        
        formats = context.user_data['formats']['video']
        await query.edit_message_text(
            "🎬 *Selecciona calidad de video:*\n\n"
            "Las opciones dependen del video original.",
            parse_mode='Markdown',
            reply_markup=create_video_quality_menu(formats)
        )
    
    elif data == "menu_audio":
        if 'formats' not in context.user_data or not context.user_data['formats']['audio']:
            await query.edit_message_text(
                "❌ No hay formatos de audio disponibles.\n"
                "Intenta con otro enlace.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬅️ Volver", callback_data="back_to_main")
                ]])
            )
            return
        
        formats = context.user_data['formats']['audio']
        await query.edit_message_text(
            "🎵 *Selecciona formato de audio:*\n\n"
            "Las opciones dependen del video original.",
            parse_mode='Markdown',
            reply_markup=create_audio_format_menu(formats)
        )
    
    elif data == "menu_formats":
        if 'formats' not in context.user_data:
            await query.edit_message_text(
                "❌ No hay información de formatos.\n"
                "Envía un enlace primero.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬅️ Volver", callback_data="back_to_main")
                ]])
            )
            return
        
        formats = context.user_data['formats']
        video_count = len(formats['video'])
        audio_count = len(formats['audio'])
        
        format_text = "📊 *Formatos disponibles:*\n\n"
        
        if video_count > 0:
            format_text += "🎬 *Video:*\n"
            for fmt in formats['video'][:5]:  # Mostrar solo primeros 5
                quality = fmt['quality_label']
                size = fmt['filesize']
                size_str = f"{size/1024/1024:.1f}MB" if size else "¿?"
                format_text += f"• {quality} ({size_str})\n"
            if video_count > 5:
                format_text += f"• ... y {video_count-5} más\n"
        
        if audio_count > 0:
            format_text += "\n🎵 *Audio:*\n"
            for fmt in formats['audio'][:5]:
                quality = fmt['quality_label']
                size = fmt['filesize']
                size_str = f"{size/1024/1024:.1f}MB" if size else "¿?"
                format_text += f"• {quality} ({size_str})\n"
            if audio_count > 5:
                format_text += f"• ... y {audio_count-5} más\n"
        
        await query.edit_message_text(
            format_text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Volver", callback_data="back_to_main")
            ]])
        )
    
    elif data == "menu_help":
        help_text = (
            "❓ *Ayuda Rápida*\n\n"
            "🎯 *Cómo descargar:*\n"
            "1. Selecciona 'Descargar Video' o 'Descargar Audio'\n"
            "2. Elige la calidad/formato\n"
            "3. Espera la descarga\n\n"
            "⚠️ *Notas:*\n"
            "• Tamaño máximo: 50MB\n"
            "• Calidades dependen del video original\n"
            "• Algunos videos pueden fallar\n\n"
            "📞 *Soporte:*\n"
            "Contacta a @landitho9 si tienes problemas."
        )
        
        await query.edit_message_text(
            help_text,
            parse_mode='Markdown',
            reply_markup=create_help_keyboard()
        )
    
    elif data == "my_info":
        user = query.from_user
        has_access = user_manager.is_allowed(user.id)
        
        info_text = (
            f"📋 *Tu información:*\n\n"
            f"🆔 User ID: `{user.id}`\n"
            f"👤 Nombre: {user.first_name}\n"
            f"📛 Username: @{user.username if user.username else 'No disponible'}\n"
            f"✅ Estado: {'PERMITIDO ✅' if has_access else 'NO PERMITIDO ❌'}\n\n"
            f"📝 *Para solicitar acceso:*\n"
            f"Envía esta información a @landitho9"
        )
        
        keyboard = [[
            InlineKeyboardButton("📋 Copiar toda mi info", callback_data=f"copy_all_{user.id}_{user.username or 'sin_username'}")
        ], [
            InlineKeyboardButton("⬅️ Volver", callback_data="back_to_main")
        ]]
        
        await query.edit_message_text(
            info_text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    # Callbacks para copiar información (usuarios sin acceso)
    elif data.startswith("copy_id_"):
        uid = data.replace("copy_id_", "")
        await query.edit_message_text(
            f"✅ *User ID copiado:* `{uid}`\n\n"
            f"📤 Envía este número a @landitho9 para solicitar acceso.",
            parse_mode='Markdown'
        )
    
    elif data.startswith("copy_user_"):
        username = data.replace("copy_user_", "")
        await query.edit_message_text(
            f"✅ *Username copiado:* @{username}\n\n"
            f"📤 Envía este @username a @landitho9 para solicitar acceso.",
            parse_mode='Markdown'
        )
    
    elif data.startswith("copy_all_"):
        parts = data.replace("copy_all_", "").split("_")
        uid = parts[0]
        username = parts[1] if len(parts) > 1 else "sin_username"
        
        info_text = f"User ID: {uid}\nUsername: @{username}"
        
        await query.edit_message_text(
            f"✅ *Información copiada:*\n```\n{info_text}\n```\n\n"
            f"📤 Envía esta información a @landitho9 para solicitar acceso.",
            parse_mode='Markdown'
        )
    
    # Callbacks para descarga
    elif data.startswith("dl_video_"):
        format_id = data.replace("dl_video_", "")
        await start_download(query, context, format_id, is_video=True)
    
    elif data.startswith("dl_audio_"):
        format_id = data.replace("dl_audio_", "")
        await start_download(query, context, format_id, is_video=False)

# ==================== DESCARGAS ====================
async def start_download(query, context, format_id: str, is_video: bool = True):
    """Inicia el proceso de descarga."""
    if 'current_url' not in context.user_data:
        await query.edit_message_text(
            "❌ Sesión expirada. Envía el enlace de nuevo.",
            parse_mode='Markdown'
        )
        return
    
    url = context.user_data['current_url']
    video_info = context.user_data.get('video_info', {})
    
    await query.edit_message_text(
        "⬇️ *Iniciando descarga...*\n\n"
        "⏳ Esto puede tomar unos minutos.\n"
        "Te avisaré cuando esté listo.",
        parse_mode='Markdown'
    )
    
    # Iniciar descarga en segundo plano
    asyncio.create_task(
        download_and_send(
            context,
            query.message.chat_id,
            query.message.message_id,
            url,
            format_id,
            is_video,
            video_info
        )
    )

async def download_and_send(context, chat_id: int, message_id: int, 
                          url: str, format_id: str, is_video: bool, 
                          video_info: Dict):
    """Descarga y envía el archivo."""
    try:
        # Actualizar mensaje
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="⬇️ *Descargando...* 0%\n\n⏳ Por favor espera.",
            parse_mode='Markdown'
        )
        
        # Variables para progreso
        last_update = time.time()
        progress_data = {'last_percent': 0}
        
        def progress_hook(d):
            """Hook para mostrar progreso."""
            if d['status'] == 'downloading':
                if 'total_bytes' in d and d['total_bytes']:
                    percent = (d['downloaded_bytes'] / d['total_bytes']) * 100
                    current_time = time.time()
                    
                    # Actualizar cada 3 segundos o si cambió mucho el porcentaje
                    if (current_time - last_update > config.UPDATE_INTERVAL or 
                        abs(percent - progress_data['last_percent']) > 5):
                        
                        progress_data['last_percent'] = percent
                        
                        # Actualizar en segundo plano (no usar await aquí)
                        asyncio.create_task(
                            update_progress(context, chat_id, message_id, percent)
                        )
        
        # Configurar opciones de yt-dlp
        ydl_opts = {
            'format': format_id,
            'outtmpl': f'{DOWNLOAD_PATH}/%(id)s.%(ext)s',
            'progress_hooks': [progress_hook],
            'quiet': True,
            'no_warnings': True,
        }
        
        if not is_video:
            # Para audio
            ydl_opts.update({
                'format': 'bestaudio',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                }]
            })
        
        # Descargar
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            if not is_video:
                filename = os.path.splitext(filename)[0] + '.mp3'
            
            # Verificar tamaño
            file_size = os.path.getsize(filename)
            if file_size > MAX_FILE_SIZE:
                os.remove(filename)
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=f"❌ *Archivo demasiado grande*\n\n"
                         f"Tamaño: {file_size/1024/1024:.1f}MB\n"
                         f"Límite: {MAX_FILE_SIZE/1024/1024:.0f}MB\n\n"
                         f"Intenta con una calidad más baja.",
                    parse_mode='Markdown'
                )
                return
            
            # Actualizar mensaje
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="📤 *Enviando a Telegram...*\n\n⏳ Un momento por favor.",
                parse_mode='Markdown'
            )
            
            # Enviar archivo
            file_size_mb = file_size / 1024 / 1024
            
            if is_video:
                caption = (
                    f"✅ *Video descargado*\n\n"
                    f"📹 {video_info.get('title', 'Video')[:50]}...\n"
                    f"📦 Tamaño: {file_size_mb:.1f}MB\n"
                    f"🎬 Calidad: {format_id}\n\n"
                    f"👤 Descargado por @{context.bot.username}"
                )
                
                with open(filename, 'rb') as video_file:
                    await context.bot.send_video(
                        chat_id=chat_id,
                        video=video_file,
                        caption=caption,
                        parse_mode='Markdown',
                        supports_streaming=True
                    )
            
            else:
                caption = (
                    f"✅ *Audio descargado*\n\n"
                    f"🎵 {video_info.get('title', 'Audio')[:50]}...\n"
                    f"📦 Tamaño: {file_size_mb:.1f}MB\n"
                    f"🎧 Formato: MP3\n\n"
                    f"👤 Descargado por @{context.bot.username}"
                )
                
                with open(filename, 'rb') as audio_file:
                    await context.bot.send_audio(
                        chat_id=chat_id,
                        audio=audio_file,
                        caption=caption,
                        parse_mode='Markdown',
                        title=video_info.get('title', 'Audio')[:50]
                    )
            
            # Eliminar archivo temporal
            os.remove(filename)
            
            # Mensaje final
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="✅ *Descarga completada exitosamente!*\n\n"
                     "El archivo ha sido enviado.\n\n"
                     "¿Quieres descargar otro video? Envía un nuevo enlace.",
                parse_mode='Markdown'
            )
    
    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        if "requested format is not available" in error_msg:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="❌ *Formato no disponible*\n\n"
                     "El formato seleccionado no está disponible en este video.\n"
                     "Intenta con otra calidad.",
                parse_mode='Markdown'
            )
        else:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=f"❌ *Error en la descarga*\n\n"
                     f"Detalles: {error_msg[:200]}\n\n"
                     f"Intenta con otro enlace o formato.",
                parse_mode='Markdown'
            )
        logger.error(f"DownloadError: {e}")
    
    except Exception as e:
        logger.error(f"Error en download_and_send: {e}")
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=f"❌ *Error inesperado*\n\n"
                 f"Detalles: {str(e)[:200]}\n\n"
                 f"Intenta de nuevo o contacta a @landitho9",
            parse_mode='Markdown'
        )
    
    finally:
        # Limpiar archivos temporales
        clean_temp_files()

async def update_progress(context, chat_id: int, message_id: int, percent: float):
    """Actualiza el mensaje con el progreso."""
    try:
        # Crear barra de progreso simple
        bars = 10
        filled = int(percent / 100 * bars)
        bar = "█" * filled + "░" * (bars - filled)
        
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=f"⬇️ *Descargando...* {percent:.1f}%\n\n{bar}\n\n⏳ Por favor espera.",
            parse_mode='Markdown'
        )
    except Exception as e:
        # Ignorar errores de edición (mensaje muy similar, etc.)
        pass

def clean_temp_files():
    """Limpia archivos temporales en la carpeta de descargas."""
    try:
        for file in os.listdir(DOWNLOAD_PATH):
            file_path = os.path.join(DOWNLOAD_PATH, file)
            # Eliminar archivos más viejos de 1 hora
            if os.path.isfile(file_path):
                file_age = time.time() - os.path.getmtime(file_path)
                if file_age > 3600:  # 1 hora
                    os.remove(file_path)
                    logger.debug(f"Archivo temporal eliminado: {file}")
    except Exception as e:
        logger.error(f"Error limpiando archivos temporales: {e}")

# ==================== CONFIGURACIÓN DEL BOT ====================
def setup_application() -> Application:
    """Configura y retorna la aplicación del bot."""
    # Crear aplicación con persistence opcional
    application = Application.builder().token(TOKEN).build()
    
    # Añadir middleware de permisos (se ejecuta primero)
    application.add_handler(TypeHandler(Update, check_permission), -1)
    
    # Comandos públicos (disponibles para todos)
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("myinfo", myinfo_command))
    application.add_handler(CommandHandler("ayuda", ayuda_command))
    
    # Comandos de administración (solo para admin)
    application.add_handler(CommandHandler("adduser", admin_add_command))
    application.add_handler(CommandHandler("removeuser", admin_remove_command))
    application.add_handler(CommandHandler("listusers", admin_list_command))
    application.add_handler(CommandHandler("stats", admin_stats_command))
    
    # Handler para callbacks (botones)
    application.add_handler(CallbackQueryHandler(callback_handler))
    
    # Handler para mensajes con URLs
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_url_message
    ))
    
    return application

# ==================== INICIALIZACIÓN ====================
def main():
    """Función principal para iniciar el bot."""
    print("=" * 50)
    print("🤖 BOT DESCARGADOR DE VIDEOS")
    print("=" * 50)
    
    # Verificar configuración
    if TOKEN == "TU_TOKEN_AQUÍ":
        print("❌ ERROR: Debes configurar el TOKEN en config.py")
        print("   Obtén uno de @BotFather en Telegram")
        return
    
    if ADMIN_ID == 123456789:
        print("⚠️ ADVERTENCIA: ADMIN_ID no configurado")
        print("   Usa @userinfobot para obtener tu user_id")
        print("   y actualiza config.py")
    
    print(f"👑 Administrador: {ADMIN_ID} (@landitho9)")
    print(f"👥 Usuarios permitidos: {user_manager.count_users()}")
    print(f"📁 Carpeta de descargas: {DOWNLOAD_PATH}")
    print(f"📏 Tamaño máximo: {MAX_FILE_SIZE/1024/1024:.0f}MB")
    print("=" * 50)
    print("🟢 Iniciando bot... (Ctrl+C para detener)")
    print("=" * 50)
    
    try:
        # Configurar y ejecutar bot
        application = setup_application()
        application.run_polling(drop_pending_updates=True)
    
    except KeyboardInterrupt:
        print("\n⏹️ Bot detenido por el usuario")
    
    except Exception as e:
        logger.error(f"Error fatal: {e}")
        print(f"❌ Error fatal: {e}")

if __name__ == "__main__":
    main()