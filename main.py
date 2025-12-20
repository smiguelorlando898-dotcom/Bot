import os
import logging
import re
import time
from pathlib import Path

import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes
)

# ==================== CONFIGURACIÓN ====================
import config

TOKEN = config.TOKEN
DOWNLOAD_PATH = config.DOWNLOAD_PATH
MAX_FILE_SIZE = config.MAX_FILE_SIZE

# Crear directorio de descargas
Path(DOWNLOAD_PATH).mkdir(exist_ok=True)

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== FUNCIONES BÁSICAS ====================
def extraer_urls(texto: str):
    """Extrae URLs de un texto (simple y efectivo)"""
    patron = r'https?://\S+'
    return re.findall(patron, texto)

def obtener_info_video(url: str):
    """Obtiene información del video - VERSIÓN SIMPLIFICADA"""
    opciones = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
    }
    
    try:
        with yt_dlp.YoutubeDL(opciones) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception as e:
        logger.error(f"Error al obtener info: {e}")
        return None

def obtener_formatos_simples(info):
    """Obtiene formatos de manera simple"""
    formatos = {'video': [], 'audio': []}
    
    if 'formats' not in info:
        return formatos
    
    for fmt in info['formats']:
        # Video con audio
        if fmt.get('vcodec') != 'none' and fmt.get('acodec') != 'none':
            altura = fmt.get('height')
            if altura:
                formatos['video'].append({
                    'altura': altura,
                    'id': fmt['format_id'],
                    'texto': f"{altura}p"
                })
        
        # Solo audio
        elif fmt.get('acodec') != 'none' and fmt.get('vcodec') == 'none':
            bitrate = fmt.get('abr', 0)
            if bitrate:
                formatos['audio'].append({
                    'bitrate': bitrate,
                    'id': fmt['format_id'],
                    'texto': f"Audio {int(bitrate)}k"
                })
    
    # Ordenar y limitar
    formatos['video'].sort(key=lambda x: x['altura'], reverse=True)
    formatos['video'] = formatos['video'][:6]  # Máximo 6 opciones
    
    formatos['audio'].sort(key=lambda x: x['bitrate'], reverse=True)
    formatos['audio'] = formatos['audio'][:4]  # Máximo 4 opciones
    
    return formatos

# ==================== BOTONES SIMPLES ====================
def menu_principal():
    """Menú principal simple"""
    teclado = [
        [InlineKeyboardButton("📹 Video", callback_data="opcion_video")],
        [InlineKeyboardButton("🎵 Audio", callback_data="opcion_audio")]
    ]
    return InlineKeyboardMarkup(teclado)

def menu_calidades_video(formatos):
    """Menú de calidades para video"""
    teclado = []
    
    for fmt in formatos:
        teclado.append([InlineKeyboardButton(fmt['texto'], callback_data=f"video_{fmt['id']}")])
    
    teclado.append([InlineKeyboardButton("⬅️ Atrás", callback_data="volver")])
    return InlineKeyboardMarkup(teclado)

def menu_formatos_audio(formatos):
    """Menú de formatos para audio"""
    teclado = []
    
    for fmt in formatos:
        teclado.append([InlineKeyboardButton(fmt['texto'], callback_data=f"audio_{fmt['id']}")])
    
    teclado.append([InlineKeyboardButton("⬅️ Atrás", callback_data="volver")])
    return InlineKeyboardMarkup(teclado)

# ==================== COMANDOS ====================
async def comando_inicio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start - SUPER SIMPLE"""
    mensaje = (
        "👋 ¡Hola!\n\n"
        "📥 Envíame un enlace de video.\n"
        "📱 Elige si quieres video o audio.\n"
        "⬇️ Descarga y listo.\n\n"
        "✨ Simple y rápido."
    )
    await update.message.reply_text(mensaje)

async def comando_ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /ayuda - MINIMALISTA"""
    mensaje = (
        "📋 Cómo usar:\n"
        "1. Envía un enlace\n"
        "2. Elige Video o Audio\n"
        "3. Selecciona calidad\n"
        "4. Espera la descarga\n\n"
        "⚠️ Máximo 50MB por archivo."
    )
    await update.message.reply_text(mensaje)

# ==================== MANEJO DE URLS ====================
async def manejar_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja URLs - VERSIÓN SIMPLIFICADA"""
    texto = update.message.text or update.message.caption or ""
    urls = extraer_urls(texto)
    
    if not urls:
        await update.message.reply_text("❌ No encontré un enlace válido.")
        return
    
    url = urls[0]
    
    # Mensaje simple de procesamiento
    mensaje = await update.message.reply_text("🔍 Buscando video...")
    
    # Obtener información
    info = obtener_info_video(url)
    
    if not info:
        await mensaje.edit_text("❌ No se pudo obtener el video.")
        return
    
    # Guardar datos simples
    context.user_data['url_actual'] = url
    context.user_data['info_video'] = info
    context.user_data['formatos'] = obtener_formatos_simples(info)
    
    # Mostrar título y opciones
    titulo = info.get('title', 'Video')
    if len(titulo) > 50:
        titulo = titulo[:47] + "..."
    
    await mensaje.edit_text(
        f"✅ {titulo}\n\nElige una opción:",
        reply_markup=menu_principal()
    )

# ==================== MANEJO DE BOTONES ====================
async def manejar_botones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja los botones - SIMPLE"""
    query = update.callback_query
    await query.answer()
    
    datos = query.data
    
    if datos == "opcion_video":
        formatos = context.user_data.get('formatos', {}).get('video', [])
        
        if not formatos:
            await query.edit_message_text("❌ No hay opciones de video disponibles.")
            return
        
        await query.edit_message_text(
            "📹 Elige calidad:",
            reply_markup=menu_calidades_video(formatos)
        )
    
    elif datos == "opcion_audio":
        formatos = context.user_data.get('formatos', {}).get('audio', [])
        
        if not formatos:
            await query.edit_message_text("❌ No hay opciones de audio disponibles.")
            return
        
        await query.edit_message_text(
            "🎵 Elige calidad:",
            reply_markup=menu_formatos_audio(formatos)
        )
    
    elif datos == "volver":
        info = context.user_data.get('info_video', {})
        titulo = info.get('title', 'Video')
        if len(titulo) > 50:
            titulo = titulo[:47] + "..."
        
        await query.edit_message_text(
            f"✅ {titulo}\n\nElige una opción:",
            reply_markup=menu_principal()
        )
    
    elif datos.startswith("video_") or datos.startswith("audio_"):
        # Iniciar descarga
        await query.edit_message_text("⬇️ Descargando...")
        await descargar_contenido(query, context, datos)

# ==================== DESCARGAS SIMPLIFICADAS ====================
async def descargar_contenido(query, context, datos_opcion):
    """Descarga y envía el contenido - VERSIÓN SIMPLE"""
    try:
        url = context.user_data.get('url_actual')
        if not url:
            await query.edit_message_text("❌ Error: URL no encontrada.")
            return
        
        # Configurar opciones según tipo
        es_video = datos_opcion.startswith("video_")
        id_formato = datos_opcion.split("_", 1)[1]
        
        opciones = {
            'format': id_formato,
            'outtmpl': f'{DOWNLOAD_PATH}/%(id)s.%(ext)s',
            'quiet': True,
        }
        
        if not es_video:
            opciones.update({
                'format': 'bestaudio',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                }]
            })
        
        # Descargar
        with yt_dlp.YoutubeDL(opciones) as ydl:
            info = ydl.extract_info(url, download=True)
            archivo = ydl.prepare_filename(info)
            
            if not es_video:
                archivo = os.path.splitext(archivo)[0] + '.mp3'
            
            # Verificar tamaño
            tamaño = os.path.getsize(archivo)
            if tamaño > MAX_FILE_SIZE:
                os.remove(archivo)
                await query.edit_message_text(
                    f"❌ Archivo muy grande ({tamaño/1024/1024:.1f}MB)\n"
                    f"Límite: {MAX_FILE_SIZE/1024/1024:.0f}MB"
                )
                return
            
            # Enviar archivo
            await query.edit_message_text("📤 Enviando...")
            
            if es_video:
                with open(archivo, 'rb') as f:
                    await context.bot.send_video(
                        chat_id=query.message.chat_id,
                        video=f,
                        caption="✅ Video descargado",
                        supports_streaming=True
                    )
            else:
                with open(archivo, 'rb') as f:
                    await context.bot.send_audio(
                        chat_id=query.message.chat_id,
                        audio=f,
                        caption="✅ Audio descargado"
                    )
            
            # Limpiar
            os.remove(archivo)
            
            # Mensaje final
            await query.edit_message_text(
                "✅ ¡Listo!\n\n"
                "¿Otro video? Envía otro enlace."
            )
    
    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        if "Facebook" in error_msg:
            mensaje = "❌ Facebook requiere configuración adicional."
        elif "Unsupported" in error_msg:
            mensaje = "❌ Enlace no soportado."
        else:
            mensaje = f"❌ Error: {error_msg[:100]}"
        
        await query.edit_message_text(mensaje)
    
    except Exception as e:
        logger.error(f"Error en descarga: {e}")
        await query.edit_message_text("❌ Ocurrió un error inesperado.")

# ==================== CONFIGURACIÓN FINAL ====================
def configurar_bot():
    """Configura el bot simplificado"""
    app = Application.builder().token(TOKEN).build()
    
    # Comandos
    app.add_handler(CommandHandler("start", comando_inicio))
    app.add_handler(CommandHandler("help", comando_ayuda))
    app.add_handler(CommandHandler("ayuda", comando_ayuda))
    
    # Botones
    app.add_handler(CallbackQueryHandler(manejar_botones))
    
    # URLs
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        manejar_url
    ))
    
    return app

# ==================== INICIAR BOT ====================
def main():
    """Función principal simplificada"""
    print("🤖 Bot iniciando...")
    
    if TOKEN == "TU_TOKEN_AQUÍ":
        print("❌ ERROR: Configura el TOKEN en config.py")
        return
    
    try:
        app = configurar_bot()
        app.run_polling()
    except KeyboardInterrupt:
        print("\n⏹️ Bot detenido")

if __name__ == "__main__":
    main()