import os
import logging
import asyncio
import json
from pathlib import Path
from typing import Dict, Optional, Tuple, List
from datetime import datetime

import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler
)

# Configuración de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Estados de conversación
SELECTING_ACTION, SELECTING_QUALITY, SELECTING_FORMAT, DOWNLOADING = range(4)

# Configuración
TOKEN = "8530361444:AAFZ-yZIFzDC0CVUvX-W14kTZGVKFITGBCE"  # Reemplaza con tu token de bot
MAX_FILE_SIZE = 2000 * 1024 * 1024  # 2GB máximo (límite de Telegram)
DOWNLOAD_PATH = "downloads"

# Crear directorio de descargas si no existe
Path(DOWNLOAD_PATH).mkdir(exist_ok=True)

# Configuración de yt-dlp sin ffmpeg
YDL_OPTS_BASE = {
    'quiet': True,
    'no_warnings': True,
    'extract_flat': False,
    'force_generic_extractor': False,
}

# Opciones de calidad para video
VIDEO_QUALITIES = {
    "144p": {"height": 144, "format": "best[height<=144]"},
    "240p": {"height": 240, "format": "best[height<=240]"},
    "360p": {"height": 360, "format": "best[height<=360]"},
    "480p": {"height": 480, "format": "best[height<=480]"},
    "720p": {"height": 720, "format": "best[height<=720]"},
    "1080p": {"height": 1080, "format": "best[height<=1080]"},
    "Mejor calidad": {"height": 0, "format": "best"},
}

# Opciones de formato para audio
AUDIO_FORMATS = {
    "MP3 128k": {"format": "bestaudio[ext=mp3]/bestaudio", "ext": "mp3"},
    "MP3 192k": {"format": "bestaudio[abr<=192]/bestaudio", "ext": "mp3"},
    "MP3 320k": {"format": "bestaudio[abr<=320]/bestaudio", "ext": "mp3"},
    "M4A": {"format": "bestaudio[ext=m4a]/bestaudio", "ext": "m4a"},
    "AAC": {"format": "bestaudio[ext=aac]/bestaudio", "ext": "aac"},
    "OGG": {"format": "bestaudio[ext=ogg]/bestaudio", "ext": "ogg"},
    "WAV": {"format": "bestaudio[ext=wav]/bestaudio", "ext": "wav"},
}

# Clase para gestionar información del usuario
class UserData:
    def __init__(self):
        self.url = ""
        self.video_info = None
        self.download_type = ""
        self.quality = ""
        self.format = ""
        self.file_path = ""

# Diccionario para almacenar datos de usuario
user_sessions: Dict[int, UserData] = {}

# Funciones de utilidad
def format_file_size(size_bytes: int) -> str:
    """Formatea el tamaño del archivo en unidades legibles."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"

def get_video_info(url: str) -> Optional[Dict]:
    """Obtiene información del video usando yt-dlp."""
    ydl_opts = YDL_OPTS_BASE.copy()
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info
    except Exception as e:
        logger.error(f"Error al obtener información: {e}")
        return None

def create_main_menu() -> InlineKeyboardMarkup:
    """Crea el menú principal con botones atractivos."""
    keyboard = [
        [InlineKeyboardButton("🎬 Descargar Video", callback_data="download_video")],
        [InlineKeyboardButton("🎵 Descargar Audio", callback_data="download_audio")],
        [InlineKeyboardButton("📊 Información del video", callback_data="video_info")],
        [InlineKeyboardButton("❓ Ayuda", callback_data="help")]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_quality_menu() -> InlineKeyboardMarkup:
    """Crea el menú de calidades de video."""
    keyboard = []
    row = []
    
    for i, (quality, _) in enumerate(VIDEO_QUALITIES.items()):
        row.append(InlineKeyboardButton(quality, callback_data=f"quality_{quality}"))
        if len(row) == 2 or i == len(VIDEO_QUALITIES) - 1:
            keyboard.append(row)
            row = []
    
    keyboard.append([InlineKeyboardButton("⬅️ Volver", callback_data="back_to_main")])
    return InlineKeyboardMarkup(keyboard)

def create_format_menu() -> InlineKeyboardMarkup:
    """Crea el menú de formatos de audio."""
    keyboard = []
    row = []
    
    for i, (format_name, _) in enumerate(AUDIO_FORMATS.items()):
        row.append(InlineKeyboardButton(format_name, callback_data=f"format_{format_name}"))
        if len(row) == 2 or i == len(AUDIO_FORMATS) - 1:
            keyboard.append(row)
            row = []
    
    keyboard.append([InlineKeyboardButton("⬅️ Volver", callback_data="back_to_main")])
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Maneja el comando /start."""
    user_id = update.effective_user.id
    
    if user_id not in user_sessions:
        user_sessions[user_id] = UserData()
    
    welcome_message = (
        "🤖 *Bienvenido al Descargador Multimedia* 🤖\n\n"
        "Soy un bot que puede descargar videos y audio de diversas plataformas:\n"
        "• YouTube\n• TikTok\n• Instagram\n• Twitter/X\n• Facebook\n• y muchas más\n\n"
        "📥 *Envía un enlace* para comenzar la descarga\n\n"
        "✨ *Características:*\n"
        "• Descarga de video y audio\n"
        "• Múltiples calidades y formatos\n"
        "• Sin necesidad de ffmpeg\n"
        "• Interfaz con botones interactivos"
    )
    
    await update.message.reply_text(
        welcome_message,
        parse_mode='Markdown',
        reply_markup=create_main_menu()
    )
    
    return SELECTING_ACTION

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Maneja el enlace enviado por el usuario."""
    user_id = update.effective_user.id
    url = update.message.text.strip()
    
    if user_id not in user_sessions:
        user_sessions[user_id] = UserData()
    
    # Verificar si es un enlace válido
    if not (url.startswith('http://') or url.startswith('https://')):
        await update.message.reply_text(
            "❌ Por favor, envía un enlace válido que comience con http:// o https://"
        )
        return SELECTING_ACTION
    
    # Procesando mensaje
    processing_msg = await update.message.reply_text(
        "🔍 *Analizando enlace...*\n\n"
        "Estoy obteniendo información del contenido...",
        parse_mode='Markdown'
    )
    
    # Obtener información del video
    video_info = get_video_info(url)
    
    if not video_info:
        await processing_msg.edit_text(
            "❌ *Error al obtener información*\n\n"
            "No pude obtener información del enlace proporcionado.\n"
            "Verifica que el enlace sea válido y esté accesible.",
            parse_mode='Markdown'
        )
        return SELECTING_ACTION
    
    # Guardar información en la sesión del usuario
    user_sessions[user_id].url = url
    user_sessions[user_id].video_info = video_info
    
    # Mostrar información del video
    title = video_info.get('title', 'Sin título')
    duration = video_info.get('duration', 0)
    duration_str = f"{duration // 60}:{duration % 60:02d}" if duration else "Desconocida"
    uploader = video_info.get('uploader', 'Desconocido')
    
    info_message = (
        f"✅ *Información obtenida correctamente*\n\n"
        f"📹 *Título:* {title}\n"
        f"⏱️ *Duración:* {duration_str}\n"
        f"👤 *Subido por:* {uploader}\n\n"
        f"🎯 *Selecciona una opción de descarga:*"
    )
    
    await processing_msg.edit_text(
        info_message,
        parse_mode='Markdown',
        reply_markup=create_main_menu()
    )
    
    return SELECTING_ACTION

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Maneja las pulsaciones de botones."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if user_id not in user_sessions:
        await query.edit_message_text(
            "❌ *Sesión expirada*\n\n"
            "Por favor, envía el enlace nuevamente.",
            parse_mode='Markdown'
        )
        return SELECTING_ACTION
    
    user_data = user_sessions[user_id]
    
    if data == "download_video":
        # Descargar video
        user_data.download_type = "video"
        await query.edit_message_text(
            "🎬 *Descarga de Video*\n\n"
            "Selecciona la calidad del video:",
            parse_mode='Markdown',
            reply_markup=create_quality_menu()
        )
        return SELECTING_QUALITY
    
    elif data == "download_audio":
        # Descargar audio
        user_data.download_type = "audio"
        await query.edit_message_text(
            "🎵 *Descarga de Audio*\n\n"
            "Selecciona el formato de audio:",
            parse_mode='Markdown',
            reply_markup=create_format_menu()
        )
        return SELECTING_FORMAT
    
    elif data == "video_info":
        # Mostrar información detallada del video
        if user_data.video_info:
            info = user_data.video_info
            title = info.get('title', 'Sin título')
            duration = info.get('duration', 0)
            duration_str = f"{duration // 60}:{duration % 60:02d}" if duration else "Desconocida"
            uploader = info.get('uploader', 'Desconocido')
            views = info.get('view_count', 'Desconocidas')
            
            info_message = (
                f"📊 *Información detallada*\n\n"
                f"📹 *Título:* {title}\n"
                f"⏱️ *Duración:* {duration_str}\n"
                f"👤 *Subido por:* {uploader}\n"
                f"👁️ *Vistas:* {views}\n"
                f"🔗 *URL:* {user_data.url}\n\n"
                f"Selecciona una opción de descarga:"
            )
            
            await query.edit_message_text(
                info_message,
                parse_mode='Markdown',
                reply_markup=create_main_menu()
            )
        else:
            await query.edit_message_text(
                "❌ *No hay información disponible*\n\n"
                "Por favor, envía un enlace primero.",
                parse_mode='Markdown',
                reply_markup=create_main_menu()
            )
        return SELECTING_ACTION
    
    elif data == "help":
        # Mostrar ayuda
        help_message = (
            "❓ *Ayuda - Descargador Multimedia*\n\n"
            "📥 *Cómo usar:*\n"
            "1. Envía un enlace de video\n"
            "2. Selecciona 'Descargar Video' o 'Descargar Audio'\n"
            "3. Elige la calidad/formato\n"
            "4. Espera a que se complete la descarga\n\n"
            "⚠️ *Limitaciones:*\n"
            "• Tamaño máximo: 2GB\n"
            "• Algunos sitios pueden requerir cookies\n"
            "• No todos los formatos están disponibles\n\n"
            "📋 *Sitios soportados:*\n"
            "YouTube, TikTok, Instagram, Twitter/X,\n"
            "Facebook, Reddit, Vimeo, Dailymotion,\n"
            "SoundCloud, Spotify y muchos más.\n\n"
            "💡 *Consejo:* Para mejor calidad de audio,\n"
            "selecciona 'MP3 320k' o 'WAV'."
        )
        await query.edit_message_text(
            help_message,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Volver", callback_data="back_to_main")]])
        )
        return SELECTING_ACTION
    
    elif data == "back_to_main":
        # Volver al menú principal
        await query.edit_message_text(
            "🔙 *Menú Principal*\n\n"
            "Selecciona una opción:",
            parse_mode='Markdown',
            reply_markup=create_main_menu()
        )
        return SELECTING_ACTION
    
    elif data.startswith("quality_"):
        # Seleccionar calidad de video
        quality = data.replace("quality_", "")
        user_data.quality = quality
        
        await query.edit_message_text(
            f"🎬 *Configuración de Video*\n\n"
            f"• Tipo: Video\n"
            f"• Calidad: {quality}\n"
            f"• URL: {user_data.url[:50]}...\n\n"
            f"⚠️ *Iniciando descarga...*\n"
            f"Esto puede tomar unos momentos...",
            parse_mode='Markdown'
        )
        
        # Iniciar descarga
        return await download_content(update, context)
    
    elif data.startswith("format_"):
        # Seleccionar formato de audio
        format_name = data.replace("format_", "")
        user_data.format = format_name
        
        await query.edit_message_text(
            f"🎵 *Configuración de Audio*\n\n"
            f"• Tipo: Audio\n"
            f"• Formato: {format_name}\n"
            f"• URL: {user_data.url[:50]}...\n\n"
            f"⚠️ *Iniciando descarga...*\n"
            f"Esto puede tomar unos momentos...",
            parse_mode='Markdown'
        )
        
        # Iniciar descarga
        return await download_content(update, context)
    
    return SELECTING_ACTION

async def download_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Descarga el contenido según las opciones seleccionadas."""
    query = update.callback_query
    user_id = query.from_user.id if query else update.effective_user.id
    user_data = user_sessions[user_id]
    
    # Configurar opciones de yt-dlp según el tipo de descarga
    ydl_opts = YDL_OPTS_BASE.copy()
    
    if user_data.download_type == "video":
        # Configuración para video
        quality_config = VIDEO_QUALITIES[user_data.quality]
        ydl_opts.update({
            'format': quality_config["format"],
            'outtmpl': f'{DOWNLOAD_PATH}/%(id)s_%(title)s.%(ext)s',
            'no_post_overwrites': True,
        })
    else:
        # Configuración para audio
        format_config = AUDIO_FORMATS[user_data.format]
        ydl_opts.update({
            'format': format_config["format"],
            'outtmpl': f'{DOWNLOAD_PATH}/%(id)s_%(title)s.%(ext)s',
            'extractaudio': True,
            'audioformat': format_config["ext"],
            'postprocessors': [],
        })
    
    try:
        # Descargar el contenido
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(user_data.url, download=True)
            downloaded_file = ydl.prepare_filename(info)
            
            # Si es audio, cambiar extensión si es necesario
            if user_data.download_type == "audio":
                ext = AUDIO_FORMATS[user_data.format]["ext"]
                downloaded_file = os.path.splitext(downloaded_file)[0] + f'.{ext}'
            
            user_data.file_path = downloaded_file
            
            # Verificar tamaño del archivo
            file_size = os.path.getsize(downloaded_file)
            
            if file_size > MAX_FILE_SIZE:
                os.remove(downloaded_file)
                if query:
                    await query.edit_message_text(
                        f"❌ *Archivo demasiado grande*\n\n"
                        f"Tamaño: {format_file_size(file_size)}\n"
                        f"Límite: {format_file_size(MAX_FILE_SIZE)}\n\n"
                        f"Intenta con una calidad más baja.",
                        parse_mode='Markdown'
                    )
                else:
                    await update.message.reply_text(
                        f"❌ *Archivo demasiado grande*\n\n"
                        f"Tamaño: {format_file_size(file_size)}\n"
                        f"Límite: {format_file_size(MAX_FILE_SIZE)}\n\n"
                        f"Intenta con una calidad más baja.",
                        parse_mode='Markdown'
                    )
                return SELECTING_ACTION
            
            # Enviar el archivo al usuario
            file_size_str = format_file_size(file_size)
            
            if user_data.download_type == "video":
                caption = f"🎬 *Video descargado*\n\n• Calidad: {user_data.quality}\n• Tamaño: {file_size_str}"
                await context.bot.send_video(
                    chat_id=user_id,
                    video=open(downloaded_file, 'rb'),
                    caption=caption,
                    parse_mode='Markdown'
                )
            else:
                caption = f"🎵 *Audio descargado*\n\n• Formato: {user_data.format}\n• Tamaño: {file_size_str}"
                await context.bot.send_audio(
                    chat_id=user_id,
                    audio=open(downloaded_file, 'rb'),
                    caption=caption,
                    parse_mode='Markdown'
                )
            
            # Limpiar archivo después de enviar
            os.remove(downloaded_file)
            
            # Mensaje de confirmación
            success_message = (
                f"✅ *Descarga completada exitosamente!*\n\n"
                f"📁 *Archivo enviado*\n"
                f"• Tipo: {'Video' if user_data.download_type == 'video' else 'Audio'}\n"
                f"• Tamaño: {file_size_str}\n\n"
                f"🔄 *¿Descargar otro contenido?*"
            )
            
            if query:
                await query.edit_message_text(
                    success_message,
                    parse_mode='Markdown',
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("📥 Nuevo enlace", callback_data="back_to_main"),
                        InlineKeyboardButton("❌ Cerrar", callback_data="close")
                    ]])
                )
            else:
                await update.message.reply_text(
                    success_message,
                    parse_mode='Markdown',
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("📥 Nuevo enlace", callback_data="back_to_main"),
                        InlineKeyboardButton("❌ Cerrar", callback_data="close")
                    ]])
                )
            
            # Limpiar sesión del usuario
            user_sessions[user_id] = UserData()
            
    except Exception as e:
        logger.error(f"Error en la descarga: {e}")
        
        error_message = (
            f"❌ *Error en la descarga*\n\n"
            f"Detalles: {str(e)[:200]}\n\n"
            f"Intenta de nuevo o selecciona otra opción."
        )
        
        if query:
            await query.edit_message_text(
                error_message,
                parse_mode='Markdown',
                reply_markup=create_main_menu()
            )
        else:
            await update.message.reply_text(
                error_message,
                parse_mode='Markdown',
                reply_markup=create_main_menu()
            )
    
    return SELECTING_ACTION

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela la conversación."""
    user_id = update.effective_user.id
    
    if user_id in user_sessions:
        # Limpiar archivos temporales si existen
        if os.path.exists(user_sessions[user_id].file_path):
            os.remove(user_sessions[user_id].file_path)
        del user_sessions[user_id]
    
    await update.message.reply_text(
        "❌ *Operación cancelada*\n\n"
        "Puedes comenzar de nuevo enviando /start",
        parse_mode='Markdown'
    )
    return ConversationHandler.END

async def close_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cierra el menú actual."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "👋 *Sesión finalizada*\n\n"
        "Usa /start para comenzar de nuevo.",
        parse_mode='Markdown'
    )
    return ConversationHandler.END

def main():
    """Función principal para iniciar el bot."""
    # Crear la aplicación
    application = Application.builder().token(TOKEN).build()
    
    # Configurar handlers de conversación
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url)
        ],
        states={
            SELECTING_ACTION: [
                CallbackQueryHandler(button_callback),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url)
            ],
            SELECTING_QUALITY: [CallbackQueryHandler(button_callback)],
            SELECTING_FORMAT: [CallbackQueryHandler(button_callback)],
            DOWNLOADING: [CallbackQueryHandler(download_content)]
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            CallbackQueryHandler(close_menu, pattern='^close$')
        ],
        allow_reentry=True
    )
    
    # Añadir handlers
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('start', start))
    
    # Iniciar el bot
    print("🤖 Bot iniciado. Presiona Ctrl+C para detener.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()