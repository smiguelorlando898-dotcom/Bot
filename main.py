import os
import logging
import re
import time
import json
import hashlib
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import yt_dlp
import requests
from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
    InputFile
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes
)

# ==================== CONFIGURACIÓN ====================
# Usar variable de entorno o valor por defecto
TOKEN = os.getenv("TOKEN", "8530361444:AAFZ-yZIFzDC0CVUvX-W14kTZGVKFITGBCE")

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

# Crear directorios necesarios
Path(DOWNLOAD_PATH).mkdir(exist_ok=True)
if CACHE_ENABLED:
    Path(CACHE_DIR).mkdir(exist_ok=True)

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== SISTEMA DE CACHE ====================
class VideoCache:
    """Cache inteligente para información de videos"""
    
    def __init__(self):
        self.cache_dir = Path(CACHE_DIR)
        self.cache_dir.mkdir(exist_ok=True)
    
    def get_cache_key(self, url: str) -> str:
        """Genera clave única para la URL"""
        return hashlib.md5(url.encode()).hexdigest()[:16]
    
    def save_info(self, url: str, video_info: Dict) -> bool:
        """Guarda información del video en cache"""
        if not CACHE_ENABLED:
            return False
        
        try:
            cache_key = self.get_cache_key(url)
            cache_file = self.cache_dir / f"{cache_key}.json"
            
            cache_data = {
                'url': url,
                'video_info': video_info,
                'timestamp': datetime.now().isoformat(),
                'expires': (datetime.now() + timedelta(minutes=CACHE_TTL_MINUTES)).isoformat()
            }
            
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"✓ Cache guardado: {url[:50]}...")
            return True
        except Exception as e:
            logger.warning(f"✗ Error guardando cache: {e}")
            return False
    
    def load_info(self, url: str) -> Optional[Dict]:
        """Carga información del video desde cache"""
        if not CACHE_ENABLED:
            return None
        
        try:
            cache_key = self.get_cache_key(url)
            cache_file = self.cache_dir / f"{cache_key}.json"
            
            if not cache_file.exists():
                return None
            
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # Verificar expiración
            expires = datetime.fromisoformat(cache_data['expires'])
            if datetime.now() > expires:
                cache_file.unlink()  # Eliminar cache expirado
                return None
            
            logger.info(f"✓ Cache cargado: {url[:50]}...")
            return cache_data['video_info']
        except Exception as e:
            logger.warning(f"✗ Error cargando cache: {e}")
            return None
    
    def clear_expired(self):
        """Limpia cache expirado"""
        try:
            expired_count = 0
            for cache_file in self.cache_dir.glob("*.json"):
                try:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        cache_data = json.load(f)
                    
                    expires = datetime.fromisoformat(cache_data.get('expires', '2000-01-01'))
                    if datetime.now() > expires:
                        cache_file.unlink()
                        expired_count += 1
                except:
                    cache_file.unlink()  # Si hay error, eliminar archivo corrupto
            
            if expired_count:
                logger.info(f"✓ Cache expirado limpiado: {expired_count} archivos")
        except Exception as e:
            logger.warning(f"✗ Error limpiando cache: {e}")

# Instancia global del cache
video_cache = VideoCache()

# ==================== FUNCIONES BÁSICAS MEJORADAS ====================
def extraer_urls(texto: str) -> List[str]:
    """Extrae URLs de un texto de manera robusta"""
    patron = r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[/\w\.\-?=&%+#@!]*'
    urls = re.findall(patron, texto)
    
    # Filtrar URLs válidas
    urls_validas = []
    for url in urls:
        try:
            parsed = urlparse(url)
            if parsed.scheme and parsed.netloc:
                urls_validas.append(url)
        except:
            continue
    
    return list(set(urls_validas))  # Eliminar duplicados

def detectar_plataforma(url: str) -> str:
    """Detecta la plataforma del video"""
    dominio = urlparse(url).netloc.lower()
    
    if 'youtube.com' in dominio or 'youtu.be' in dominio:
        return 'YouTube'
    elif 'tiktok.com' in dominio:
        return 'TikTok'
    elif 'instagram.com' in dominio:
        return 'Instagram'
    elif 'twitter.com' in dominio or 'x.com' in dominio:
        return 'Twitter/X'
    elif 'facebook.com' in dominio or 'fb.com' in dominio:
        return 'Facebook'
    elif 'reddit.com' in dominio:
        return 'Reddit'
    elif 'vimeo.com' in dominio:
        return 'Vimeo'
    else:
        return 'Otro'

def es_contenido_corto(url: str) -> bool:
    """Detecta si es contenido corto (Shorts, Reels, TikTok)"""
    url_lower = url.lower()
    return any(x in url_lower for x in [
        'youtube.com/shorts/',
        '/shorts/',
        'tiktok.com',
        'instagram.com/reel'
    ])

async def obtener_info_video_mejorado(url: str) -> Optional[Dict]:
    """Obtiene información del video con cache y manejo de errores"""
    
    # 1. Intentar desde cache primero
    if CACHE_ENABLED:
        cached_info = video_cache.load_info(url)
        if cached_info:
            logger.info(f"✓ Info desde cache: {url[:50]}...")
            return cached_info
    
    # 2. Configurar opciones optimizadas
    opciones = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'socket_timeout': 30,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web'],
                'skip': ['hls', 'dash'],
            }
        },
    }
    
    # 3. Intentar con diferentes configuraciones
    intentos = [
        opciones,  # Configuración estándar
        {**opciones, 'extractor_args': {'facebook': {'skip': False}}},  # Para Facebook
        {**opciones, 'headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}},
    ]
    
    for intento, config_intento in enumerate(intentos, 1):
        try:
            logger.info(f"Intento {intento} para: {url[:50]}...")
            
            with yt_dlp.YoutubeDL(config_intento) as ydl:
                info = ydl.extract_info(url, download=False)
                
                # Guardar en cache si está habilitado
                if CACHE_ENABLED and info:
                    video_cache.save_info(url, info)
                
                return info
                
        except yt_dlp.utils.DownloadError as e:
            error_msg = str(e).lower()
            
            # Intentar métodos alternativos para Facebook/Instagram
            if 'facebook' in error_msg or 'instagram' in error_msg:
                logger.warning(f"Error con {detectar_plataforma(url)}: {error_msg[:100]}")
                
                if intento < len(intentos):
                    continue  # Probar siguiente configuración
                else:
                    # Último recurso: intentar sin opciones especiales
                    try:
                        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                            return ydl.extract_info(url, download=False)
                    except:
                        return None
            
            elif 'unsupported url' in error_msg or 'private video' in error_msg:
                logger.warning(f"URL no soportada o video privado: {url}")
                return None
            
            else:
                logger.error(f"Error yt-dlp: {e}")
                if intento < len(intentos):
                    continue
                return None
                
        except Exception as e:
            logger.error(f"Error inesperado: {e}")
            if intento < len(intentos):
                time.sleep(1)  # Pequeña pausa entre intentos
                continue
            return None
    
    return None

def extraer_formatos_inteligentes(info: Dict) -> Dict:
    """Extrae formatos disponibles de manera inteligente"""
    formatos = {'video': [], 'audio': []}
    
    if 'formats' not in info:
        return formatos
    
    # Diccionario para agrupar por calidad
    grupos_calidad = {}
    
    for fmt in info['formats']:
        # Video con audio (formato completo)
        if fmt.get('vcodec') != 'none' and fmt.get('acodec') != 'none':
            altura = fmt.get('height', 0)
            extension = fmt.get('ext', 'mp4').lower()
            codec = fmt.get('vcodec', '').lower()
            filesize = fmt.get('filesize', fmt.get('filesize_approx', 0))
            
            if altura > 0:
                # Agrupar por altura y codec similar
                clave = f"{altura}p"
                
                # Preferir codec AVC/H.264 para mejor compatibilidad
                es_codec_preferido = 'avc' in codec or 'h264' in codec
                
                if clave not in grupos_calidad:
                    grupos_calidad[clave] = {
                        'altura': altura,
                        'extension': extension,
                        'codec': codec,
                        'filesize': filesize,
                        'format_id': fmt['format_id'],
                        'es_preferido': es_codec_preferido
                    }
                else:
                    # Mantener el formato preferido o de mayor calidad
                    actual = grupos_calidad[clave]
                    
                    # Preferir codec AVC/H.264
                    if es_codec_preferido and not actual['es_preferido']:
                        grupos_calidad[clave] = {
                            'altura': altura,
                            'extension': extension,
                            'codec': codec,
                            'filesize': filesize,
                            'format_id': fmt['format_id'],
                            'es_preferido': es_codec_preferido
                        }
                    # Si mismo codec, mantener mayor calidad/filesize
                    elif es_codec_preferido == actual['es_preferido']:
                        if filesize > actual['filesize']:
                            grupos_calidad[clave] = {
                                'altura': altura,
                                'extension': extension,
                                'codec': codec,
                                'filesize': filesize,
                                'format_id': fmt['format_id'],
                                'es_preferido': es_codec_preferido
                            }
        
        # Solo audio
        elif fmt.get('acodec') != 'none' and fmt.get('vcodec') == 'none':
            bitrate = fmt.get('abr', 0)
            extension = fmt.get('ext', 'mp3').lower()
            
            if bitrate > 0:
                formatos['audio'].append({
                    'bitrate': int(bitrate),
                    'extension': extension,
                    'format_id': fmt['format_id'],
                    'texto': f"Audio {int(bitrate)}kbps"
                })
    
    # Convertir grupos a lista de formatos de video
    for calidad, datos in sorted(grupos_calidad.items(), 
                                 key=lambda x: x[1]['altura'], 
                                 reverse=True):
        texto = f"{datos['altura']}p"
        if datos['extension'] != 'mp4':
            texto += f" {datos['extension'].upper()}"
        
        # Añadir emoji indicador
        if datos['es_preferido']:
            texto = f"🎯 {texto}"
        elif datos['altura'] >= 1080:
            texto = f"🔥 {texto}"
        elif datos['altura'] >= 720:
            texto = f"⚡ {texto}"
        
        # Añadir tamaño aproximado si está disponible
        if datos['filesize']:
            tamano_mb = datos['filesize'] / (1024 * 1024)
            if tamano_mb > 0:
                texto += f" ({tamano_mb:.1f}MB)"
        
        formatos['video'].append({
            'altura': datos['altura'],
            'extension': datos['extension'],
            'format_id': datos['format_id'],
            'texto': texto,
            'tamano': datos['filesize']
        })
    
    # Limitar y ordenar audio
    if formatos['audio']:
        # Eliminar duplicados por bitrate
        audio_unicos = {}
        for audio in formatos['audio']:
            if audio['bitrate'] not in audio_unicos:
                audio_unicos[audio['bitrate']] = audio
        
        formatos['audio'] = list(audio_unicos.values())
        formatos['audio'].sort(key=lambda x: x['bitrate'], reverse=True)
        formatos['audio'] = formatos['audio'][:4]  # Máximo 4 opciones
    
    # Limitar video a 8 opciones máximo
    formatos['video'] = formatos['video'][:8]
    
    return formatos

# ==================== MANEJO DE ARCHIVOS TEMPORALES ====================
def crear_directorio_seguro(url: str, user_id: int) -> str:
    """Crea directorio seguro para descargas temporales"""
    import re
    
    # Extraer nombre de dominio
    dominio_match = re.search(r'https?://([^/]+)', url)
    if dominio_match:
        dominio = dominio_match.group(1)
        # Limpiar dominio
        dominio = dominio.replace('www.', '').split('.')[0]
    else:
        dominio = "video"
    
    # Generar hash corto de la URL
    url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
    
    # Crear nombre seguro
    nombre_seguro = f"{dominio}_{url_hash}"
    nombre_seguro = re.sub(r'[^\w\-]', '_', nombre_seguro)
    
    # Crear path completo
    carpeta_usuario = Path(DOWNLOAD_PATH) / str(user_id)
    carpeta_descarga = carpeta_usuario / nombre_seguro
    
    # Crear directorios
    carpeta_descarga.mkdir(parents=True, exist_ok=True)
    
    return str(carpeta_descarga)

def limpiar_archivos_temporales(dias=1):
    """Limpia archivos temporales antiguos"""
    from datetime import datetime, timedelta
    
    try:
        limite = datetime.now() - timedelta(days=dias)
        directorio = Path(DOWNLOAD_PATH)
        
        if not directorio.exists():
            return
        
        for usuario_dir in directorio.iterdir():
            if usuario_dir.is_dir():
                for item in usuario_dir.rglob("*"):
                    if item.is_file():
                        try:
                            mtime = datetime.fromtimestamp(item.stat().st_mtime)
                            if mtime < limite:
                                item.unlink()
                        except:
                            continue
        
        logger.info("✓ Archivos temporales limpiados")
    except Exception as e:
        logger.warning(f"✗ Error limpiando temporales: {e}")

# ==================== GENERACIÓN DE THUMBNAILS ====================
async def generar_thumbnail(video_path: str, output_path: str) -> bool:
    """Genera thumbnail desde el punto medio del video"""
    if not GENERATE_THUMBNAILS:
        return False
    
    try:
        # Obtener duración del video usando yt-dlp
        ydl_opts = {'quiet': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_path, download=False)
            duration = info.get('duration', 0)
        
        # Calcular punto medio
        punto_medio = max(1, duration // 2) if duration > 0 else 1
        
        # Usar ffmpeg si está disponible
        import subprocess
        
        cmd = [
            'ffmpeg', '-y',
            '-ss', str(punto_medio),
            '-i', video_path,
            '-vframes', '1',
            '-vf', f'scale={config.THUMBNAIL_WIDTH}:-1',
            '-q:v', '2',
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        
        if result.returncode == 0 and os.path.exists(output_path):
            logger.info(f"✓ Thumbnail generado: {output_path}")
            return True
        else:
            logger.warning(f"✗ Error generando thumbnail: {result.stderr}")
            return False
            
    except Exception as e:
        logger.warning(f"✗ Error en generar_thumbnail: {e}")
        return False

async def descargar_thumbnail_url(url_video: str, output_path: str) -> bool:
    """Descarga thumbnail desde URL si está disponible"""
    try:
        # Primero obtener info del video
        info = await obtener_info_video_mejorado(url_video)
        if not info:
            return False
        
        # Verificar si tiene thumbnail
        thumbnail_url = info.get('thumbnail')
        if not thumbnail_url:
            return False
        
        # Descargar thumbnail
        response = requests.get(thumbnail_url, timeout=10)
        if response.status_code == 200:
            with open(output_path, 'wb') as f:
                f.write(response.content)
            
            # Verificar que el archivo sea válido
            if os.path.getsize(output_path) > 0:
                logger.info(f"✓ Thumbnail descargado: {thumbnail_url}")
                return True
        
        return False
    except Exception as e:
        logger.warning(f"✗ Error descargando thumbnail: {e}")
        return False

# ==================== BOTONES INTERACTIVOS ====================
def crear_menu_principal() -> InlineKeyboardMarkup:
    """Crea el menú principal simplificado"""
    teclado = [
        [InlineKeyboardButton("🎬 Descargar Video", callback_data="opcion_video")],
        [InlineKeyboardButton("🎵 Solo Audio (MP3)", callback_data="opcion_audio")],
        [InlineKeyboardButton("❓ Ayuda", callback_data="menu_ayuda")]
    ]
    return InlineKeyboardMarkup(teclado)

def crear_menu_calidades(formatos_video: List[Dict]) -> InlineKeyboardMarkup:
    """Crea menú de calidades de video"""
    teclado = []
    
    # Organizar en filas de 2 botones
    for i in range(0, len(formatos_video), 2):
        fila = []
        for j in range(2):
            if i + j < len(formatos_video):
                fmt = formatos_video[i + j]
                fila.append(InlineKeyboardButton(
                    fmt['texto'],
                    callback_data=f"descargar_video_{fmt['format_id']}"
                ))
        if fila:
            teclado.append(fila)
    
    # Botones de navegación
    teclado.append([
        InlineKeyboardButton("⬅️ Atrás", callback_data="volver_menu"),
        InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")
    ])
    
    return InlineKeyboardMarkup(teclado)

def crear_menu_audio(formatos_audio: List[Dict]) -> InlineKeyboardMarkup:
    """Crea menú de formatos de audio"""
    teclado = []
    
    for fmt in formatos_audio:
        teclado.append([InlineKeyboardButton(
            fmt['texto'],
            callback_data=f"descargar_audio_{fmt['format_id']}"
        )])
    
    # Botones de navegación
    teclado.append([
        InlineKeyboardButton("⬅️ Atrás", callback_data="volver_menu"),
        InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")
    ])
    
    return InlineKeyboardMarkup(teclado)

def crear_menu_ayuda() -> InlineKeyboardMarkup:
    """Crea menú de ayuda"""
    teclado = [
        [InlineKeyboardButton("📋 Cómo usar", callback_data="ayuda_uso")],
        [InlineKeyboardButton("🌐 Sitios soportados", callback_data="ayuda_sitios")],
        [InlineKeyboardButton("⚠️ Limitaciones", callback_data="ayuda_limites")],
        [InlineKeyboardButton("⬅️ Volver al Menú", callback_data="volver_menu")]
    ]
    return InlineKeyboardMarkup(teclado)

# ==================== COMANDOS DEL BOT ====================
async def comando_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start - Bienvenida simple"""
    mensaje = (
        "🤖 *Bot Descargador de Videos*\n\n"
        "📥 Envíame un enlace de video y elige la calidad.\n"
        "⚡ Rápido y sencillo.\n\n"
        "🔗 *Soporto:* YouTube, TikTok, Instagram, Facebook, Twitter/X, Reddit, etc.\n\n"
        "✨ ¡Comienza enviando un enlace!"
    )
    
    await update.message.reply_text(mensaje, parse_mode='Markdown')

async def comando_ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /ayuda - Información completa"""
    mensaje = (
        "📚 *Ayuda - Bot Descargador*\n\n"
        "🎯 *Cómo usar:*\n"
        "1. Envía un enlace de video\n"
        "2. Elige 'Descargar Video' o 'Solo Audio'\n"
        "3. Selecciona la calidad\n"
        "4. Espera la descarga\n\n"
        "🌐 *Sitios soportados:*\n"
        "• YouTube (videos, shorts)\n"
        "• TikTok\n• Instagram (reels, posts)\n"
        "• Twitter/X\n• Facebook\n• Reddit\n"
        "• Vimeo\n• Dailymotion\n• SoundCloud\n\n"
        "⚠️ *Limitaciones:*\n"
        "• Máximo 50MB por archivo\n"
        "• Algunos videos pueden tener restricciones\n"
        "• Videos privados no funcionan\n\n"
        "🚀 *Consejos:*\n"
        "• Para mejor calidad, elige 720p o 1080p\n"
        "• Para ahorrar datos, elige 360p o 480p\n"
        "• El audio se descarga como MP3\n\n"
        "❓ ¿Problemas? Intenta con otro enlace."
    )
    
    await update.message.reply_text(mensaje, parse_mode='Markdown')

async def comando_limpiar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /limpiar - Limpia archivos temporales"""
    try:
        limpiar_archivos_temporales()
        await update.message.reply_text("✅ Archivos temporales limpiados correctamente.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error al limpiar: {str(e)[:100]}")

# ==================== MANEJO DE URLS ====================
async def manejar_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja URLs enviadas por el usuario"""
    # Limpiar cache expirado periódicamente
    video_cache.clear_expired()
    
    # Extraer URL del mensaje
    texto = update.message.text or update.message.caption or ""
    urls = extraer_urls(texto)
    
    if not urls:
        await update.message.reply_text(
            "❌ No encontré un enlace válido en tu mensaje.\n\n"
            "Envíame un enlace como: https://www.youtube.com/watch?v=..."
        )
        return
    
    url = urls[0]
    user_id = update.effective_user.id
    
    # Verificar URL básica
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            await update.message.reply_text("❌ El enlace no es válido. Debe comenzar con http:// o https://")
            return
    except:
        await update.message.reply_text("❌ El enlace no es válido.")
        return
    
    # Detectar plataforma
    plataforma = detectar_plataforma(url)
    
    # Mensaje informativo
    mensaje_proceso = await update.message.reply_text(
        f"🔍 *Analizando enlace...*\n\n"
        f"🌐 Plataforma: {plataforma}\n"
        f"⏳ Obteniendo información...",
        parse_mode='Markdown'
    )
    
    # Obtener información del video
    info_video = await obtener_info_video_mejorado(url)
    
    if not info_video:
        await mensaje_proceso.edit_text(
            "❌ *No se pudo obtener información del video*\n\n"
            "Posibles causas:\n"
            "• El video no existe o fue eliminado\n"
            "• Es privado o requiere inicio de sesión\n"
            "• La plataforma no está soportada\n"
            "• Problema temporal con el servidor\n\n"
            "Intenta con otro enlace.",
            parse_mode='Markdown'
        )
        return
    
    # Extraer información básica
    titulo = info_video.get('title', 'Video sin título')
    duracion = info_video.get('duration', 0)
    duracion_str = f"{duracion // 60}:{duracion % 60:02d}" if duracion > 0 else "Desconocida"
    
    # Acortar título si es muy largo
    if len(titulo) > 100:
        titulo_mostrar = titulo[:97] + "..."
    else:
        titulo_mostrar = titulo
    
    # Guardar información en context para uso posterior
    context.user_data['url_actual'] = url
    context.user_data['info_video'] = info_video
    context.user_data['titulo'] = titulo
    
    # Extraer formatos disponibles
    formatos = extraer_formatos_inteligentes(info_video)
    
    # Verificar si hay formatos disponibles
    if not formatos['video'] and not formatos['audio']:
        await mensaje_proceso.edit_text(
            "❌ *No hay formatos disponibles para descargar*\n\n"
            "Este video no tiene formatos compatibles o están restringidos.",
            parse_mode='Markdown'
        )
        return
    
    # Guardar formatos en context
    context.user_data['formatos'] = formatos
    
    # Crear mensaje informativo
    mensaje_info = (
        f"✅ *{titulo_mostrar}*\n\n"
        f"⏱️ Duración: {duracion_str}\n"
        f"🌐 Plataforma: {plataforma}\n\n"
    )
    
    # Añadir información de formatos disponibles
    if formatos['video']:
        mejor_video = formatos['video'][0]
        mensaje_info += f"🎬 Mejor calidad: {mejor_video['texto']}\n"
    
    if formatos['audio']:
        mejor_audio = formatos['audio'][0]
        mensaje_info += f"🎵 Mejor audio: {mejor_audio['texto']}\n"
    
    mensaje_info += "\n👇 *Elige una opción:*"
    
    # Mostrar menú principal
    await mensaje_proceso.edit_text(
        mensaje_info,
        parse_mode='Markdown',
        reply_markup=crear_menu_principal()
    )

# ==================== MANEJO DE CALLBACKS ====================
async def manejar_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja todos los callbacks de botones"""
    query = update.callback_query
    await query.answer()
    
    datos = query.data
    user_id = query.from_user.id
    
    # Volver al menú principal
    if datos == "volver_menu":
        if 'info_video' in context.user_data:
            info = context.user_data['info_video']
            titulo = info.get('title', 'Video')
            if len(titulo) > 100:
                titulo = titulo[:97] + "..."
            
            await query.edit_message_text(
                f"✅ *{titulo}*\n\n👇 Elige una opción de descarga:",
                parse_mode='Markdown',
                reply_markup=crear_menu_principal()
            )
        else:
            await query.edit_message_text(
                "🎯 *Menú Principal*\n\nEnvía un enlace para comenzar.",
                parse_mode='Markdown',
                reply_markup=crear_menu_principal()
            )
        return
    
    # Cancelar operación
    elif datos == "cancelar":
        await query.edit_message_text(
            "❌ Operación cancelada.\n\nEnvía otro enlace si quieres descargar algo más.",
            parse_mode='Markdown'
        )
        # Limpiar datos de usuario
        if user_id in context.user_data:
            context.user_data.clear()
        return
    
    # Menú de ayuda
    elif datos == "menu_ayuda":
        await query.edit_message_text(
            "📚 *Ayuda Rápida*\n\nSelecciona una opción:",
            parse_mode='Markdown',
            reply_markup=crear_menu_ayuda()
        )
        return
    
    elif datos == "ayuda_uso":
        await query.edit_message_text(
            "🎯 *Cómo usar:*\n\n"
            "1. Envía un enlace de video\n"
            "2. Elige 'Descargar Video' o 'Solo Audio'\n"
            "3. Selecciona la calidad\n"
            "4. Espera la descarga\n\n"
            "✨ Simple y rápido.",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Volver a Ayuda", callback_data="menu_ayuda")
            ]])
        )
        return
    
    elif datos == "ayuda_sitios":
        await query.edit_message_text(
            "🌐 *Sitios soportados:*\n\n"
            "• YouTube (videos, shorts)\n"
            "• TikTok\n• Instagram (reels, posts)\n"
            "• Twitter/X\n• Facebook\n• Reddit\n"
            "• Vimeo\n• Dailymotion\n• SoundCloud\n"
            "• Y muchos más...\n\n"
            "⚠️ Algunos sitios pueden tener limitaciones.",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Volver a Ayuda", callback_data="menu_ayuda")
            ]])
        )
        return
    
    elif datos == "ayuda_limites":
        await query.edit_message_text(
            "⚠️ *Limitaciones:*\n\n"
            "• Máximo 50MB por archivo\n"
            "• Videos privados no funcionan\n"
            "• Algunos sitios requieren login\n"
            "• Calidades dependen del video original\n"
            "• Puede fallar con videos muy largos\n\n"
            "🎯 Para mejores resultados, usa enlaces públicos.",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Volver a Ayuda", callback_data="menu_ayuda")
            ]])
        )
        return
    
    # Opción: Descargar Video
    elif datos == "opcion_video":
        if 'formatos' not in context.user_data or not context.user_data['formatos']['video']:
            await query.edit_message_text(
                "❌ No hay formatos de video disponibles.\n"
                "Intenta con otro enlace.",
                parse_mode='Markdown'
            )
            return
        
        formatos_video = context.user_data['formatos']['video']
        
        await query.edit_message_text(
            "🎬 *Selecciona calidad de video:*\n\n"
            "Las opciones dependen del video original.",
            parse_mode='Markdown',
            reply_markup=crear_menu_calidades(formatos_video)
        )
        return
    
    # Opción: Descargar Audio
    elif datos == "opcion_audio":
        if 'formatos' not in context.user_data or not context.user_data['formatos']['audio']:
            await query.edit_message_text(
                "❌ No hay formatos de audio disponibles.\n"
                "Intenta con otro enlace.",
                parse_mode='Markdown'
            )
            return
        
        formatos_audio = context.user_data['formatos']['audio']
        
        await query.edit_message_text(
            "🎵 *Selecciona calidad de audio:*\n\n"
            "El audio se descargará en formato MP3.",
            parse_mode='Markdown',
            reply_markup=crear_menu_audio(formatos_audio)
        )
        return
    
    # Descargar video específico
    elif datos.startswith("descargar_video_"):
        formato_id = datos.replace("descargar_video_", "")
        await iniciar_descarga(query, context, formato_id, es_video=True)
        return
    
    # Descargar audio específico
    elif datos.startswith("descargar_audio_"):
        formato_id = datos.replace("descargar_audio_", "")
        await iniciar_descarga(query, context, formato_id, es_video=False)
        return

# ==================== SISTEMA DE DESCARGA MEJORADO ====================
async def iniciar_descarga(query, context, formato_id: str, es_video: bool = True):
    """Inicia el proceso de descarga"""
    user_id = query.from_user.id
    
    # Verificar datos necesarios
    if 'url_actual' not in context.user_data:
        await query.edit_message_text(
            "❌ Sesión expirada. Envía el enlace de nuevo.",
            parse_mode='Markdown'
        )
        return
    
    url = context.user_data['url_actual']
    info_video = context.user_data.get('info_video', {})
    titulo = context.user_data.get('titulo', 'Video')
    
    # Crear directorio seguro para esta descarga
    directorio_descarga = crear_directorio_seguro(url, user_id)
    
    # Actualizar mensaje
    tipo_descarga = "video" if es_video else "audio"
    await query.edit_message_text(
        f"⬇️ *Iniciando descarga de {tipo_descarga}...*\n\n"
        f"📦 Preparando...",
        parse_mode='Markdown'
    )
    
    # Iniciar descarga en segundo plano
    asyncio.create_task(
        descargar_y_enviar(
            context,
            query.message.chat_id,
            query.message.message_id,
            url,
            formato_id,
            es_video,
            info_video,
            titulo,
            directorio_descarga
        )
    )

async def descargar_y_enviar(context, chat_id: int, message_id: int, url: str,
                           formato_id: str, es_video: bool, info_video: Dict,
                           titulo: str, directorio_descarga: str):
    """Descarga y envía el archivo con manejo de errores mejorado"""
    archivo_final = None
    thumbnail_path = None
    
    try:
        # Paso 1: Actualizar estado
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="⬇️ *Descargando...* 0%\n\n⏳ Por favor espera.",
            parse_mode='Markdown'
        )
        
        # Variables para progreso
        ultima_actualizacion = time.time()
        progreso_data = {'porcentaje_anterior': 0}
        
        def hook_progreso(d):
            """Hook para mostrar progreso de descarga"""
            if d['status'] == 'downloading':
                if 'total_bytes' in d and d['total_bytes']:
                    porcentaje = (d['downloaded_bytes'] / d['total_bytes']) * 100
                    tiempo_actual = time.time()
                    
                    # Actualizar cada 3 segundos o si cambió mucho el porcentaje
                    if (tiempo_actual - ultima_actualizacion > config.PROGRESS_UPDATE_INTERVAL or 
                        abs(porcentaje - progreso_data['porcentaje_anterior']) > 5):
                        
                        progreso_data['porcentaje_anterior'] = porcentaje
                        
                        # Actualizar en segundo plano
                        asyncio.create_task(
                            actualizar_progreso(context, chat_id, message_id, porcentaje)
                        )
        
        # Paso 2: Configurar opciones de descarga
        opciones_ydl = {
            'outtmpl': f'{directorio_descarga}/%(title)s.%(ext)s',
            'progress_hooks': [hook_progreso],
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 30,
            'retries': MAX_RETRIES,
        }
        
        if es_video:
            # Para video: formato específico o mejor disponible
            if formato_id != 'best':
                opciones_ydl['format'] = formato_id
            else:
                opciones_ydl['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
            
            # Optimizar para velocidad
            opciones_ydl.update({
                'merge_output_format': 'mp4',
                'prefer_ffmpeg': False,
            })
        
        else:
            # Para audio: formato MP3
            opciones_ydl.update({
                'format': 'bestaudio',
                'extractaudio': True,
                'audioformat': 'mp3',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })
        
        # Paso 3: Descargar el contenido
        with yt_dlp.YoutubeDL(opciones_ydl) as ydl:
            info = ydl.extract_info(url, download=True)
            archivo_descargado = ydl.prepare_filename(info)
            
            # Para audio, ajustar extensión
            if not es_video:
                archivo_descargado = os.path.splitext(archivo_descargado)[0] + '.mp3'
            
            archivo_final = archivo_descargado
        
        # Paso 4: Verificar archivo descargado
        if not os.path.exists(archivo_final):
            raise Exception("El archivo no se descargó correctamente")
        
        tamaño = os.path.getsize(archivo_final)
        if tamaño > MAX_FILE_SIZE:
            os.remove(archivo_final)
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=f"❌ *Archivo demasiado grande*\n\n"
                     f"Tamaño: {tamaño/1024/1024:.1f}MB\n"
                     f"Límite: {MAX_FILE_SIZE/1024/1024:.0f}MB\n\n"
                     f"Intenta con una calidad más baja.",
                parse_mode='Markdown'
            )
            return
        
        # Paso 5: Preparar thumbnail
        if es_video and GENERATE_THUMBNAILS:
            # Intentar descargar thumbnail desde URL primero
            thumbnail_path = os.path.join(directorio_descarga, "thumbnail.jpg")
            if not await descargar_thumbnail_url(url, thumbnail_path):
                # Si falla, generar desde video
                thumbnail_path = os.path.join(directorio_descarga, "generated_thumb.jpg")
                await generar_thumbnail(archivo_final, thumbnail_path)
        
        # Paso 6: Actualizar mensaje para envío
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="📤 *Enviando a Telegram...*\n\n⏳ Un momento por favor.",
            parse_mode='Markdown'
        )
        
        # Paso 7: Preparar caption
        tamaño_mb = tamaño / 1024 / 1024
        plataforma = detectar_plataforma(url)
        
        if es_video:
            caption = (
                f"✅ *Video descargado*\n\n"
                f"📹 {titulo[:100]}\n"
                f"📦 Tamaño: {tamaño_mb:.1f}MB\n"
                f"🌐 Plataforma: {plataforma}\n"
                f"🎬 Calidad: {formato_id if formato_id != 'best' else 'Mejor disponible'}\n\n"
                f"👇 Reproduce desde Telegram"
            )
        else:
            caption = (
                f"✅ *Audio descargado*\n\n"
                f"🎵 {titulo[:100]}\n"
                f"📦 Tamaño: {tamaño_mb:.1f}MB\n"
                f"🌐 Plataforma: {plataforma}\n"
                f"🎧 Formato: MP3\n\n"
                f"👇 Escucha desde Telegram"
            )
        
        # Paso 8: Enviar archivo con reintentos
        for intento in range(MAX_RETRIES):
            try:
                with open(archivo_final, 'rb') as archivo:
                    if es_video:
                        # Detectar si es contenido corto
                        if es_contenido_corto(url):
                            width, height = 360, 640  # Vertical para shorts
                        else:
                            width, height = 640, 360  # Horizontal normal
                        
                        await context.bot.send_video(
                            chat_id=chat_id,
                            video=InputFile(archivo),
                            caption=caption,
                            parse_mode='Markdown',
                            width=width,
                            height=height,
                            supports_streaming=True,
                            thumbnail=InputFile(thumbnail_path) if thumbnail_path and os.path.exists(thumbnail_path) else None,
                            read_timeout=60,
                            write_timeout=60,
                            connect_timeout=30
                        )
                    else:
                        await context.bot.send_audio(
                            chat_id=chat_id,
                            audio=InputFile(archivo),
                            caption=caption,
                            parse_mode='Markdown',
                            title=titulo[:64],
                            thumbnail=InputFile(thumbnail_path) if thumbnail_path and os.path.exists(thumbnail_path) else None,
                            read_timeout=60,
                            write_timeout=60,
                            connect_timeout=30
                        )
                
                # Si llegamos aquí, el envío fue exitoso
                break
                
            except Exception as e:
                if intento < MAX_RETRIES - 1:
                    logger.warning(f"Intento {intento + 1} falló: {e}")
                    await asyncio.sleep(RETRY_DELAY)
                    continue
                else:
                    # Último intento falló
                    raise
        
        # Paso 9: Mensaje final
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="✅ *¡Descarga completada exitosamente!*\n\n"
                 "El archivo ha sido enviado.\n\n"
                 "¿Quieres descargar otro video? Envía un nuevo enlace.",
            parse_mode='Markdown'
        )
    
    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e).lower()
        
        if "facebook" in error_msg or "instagram" in error_msg:
            mensaje_error = (
                "❌ *Error con Facebook/Instagram*\n\n"
                "Estas plataformas pueden requerir:\n"
                "• Inicio de sesión\n"
                "• Configuración adicional\n"
                "• Esperar unos minutos\n\n"
                "Intenta con otro enlace o plataforma."
            )
        elif "private video" in error_msg or "members only" in error_msg:
            mensaje_error = "❌ El video es privado o requiere suscripción."
        elif "unsupported url" in error_msg:
            mensaje_error = "❌ URL no soportada. Intenta con otra plataforma."
        elif "format not available" in error_msg:
            mensaje_error = "❌ El formato seleccionado no está disponible."
        else:
            mensaje_error = f"❌ Error en la descarga: {error_msg[:100]}"
        
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=mensaje_error,
            parse_mode='Markdown'
        )
        logger.error(f"DownloadError: {e}")
    
    except Exception as e:
        logger.error(f"Error en descargar_y_enviar: {e}")
        
        mensaje_error = (
            f"❌ *Error inesperado*\n\n"
            f"Detalles: {str(e)[:150]}\n\n"
            f"Intenta:\n"
            f"1. Con otro enlace\n"
            f"2. Con otra calidad\n"
            f"3. Esperar unos minutos"
        )
        
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=mensaje_error,
            parse_mode='Markdown'
        )
    
    finally:
        # Paso 10: Limpieza
        try:
            if archivo_final and os.path.exists(archivo_final):
                os.remove(archivo_final)
            
            if thumbnail_path and os.path.exists(thumbnail_path):
                os.remove(thumbnail_path)
            
            # Intentar limpiar directorio si está vacío
            try:
                if os.path.exists(directorio_descarga):
                    if not os.listdir(directorio_descarga):
                        os.rmdir(directorio_descarga)
            except:
                pass
        except Exception as e:
            logger.warning(f"Error en limpieza: {e}")

async def actualizar_progreso(context, chat_id: int, message_id: int, porcentaje: float):
    """Actualiza el mensaje con el progreso de descarga"""
    try:
        # Crear barra de progreso simple
        barras = 10
        llenas = int(porcentaje / 100 * barras)
        barra = "█" * llenas + "░" * (barras - llenas)
        
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=f"⬇️ *Descargando...* {porcentaje:.1f}%\n\n{barra}\n\n⏳ Por favor espera.",
            parse_mode='Markdown'
        )
    except Exception:
        # Ignorar errores de edición (mensaje muy similar, etc.)
        pass

# ==================== CONFIGURACIÓN DEL BOT ====================
def configurar_bot():
    """Configura y retorna la aplicación del bot"""
    # Crear aplicación
    application = Application.builder().token(TOKEN).build()
    
    # Comandos
    application.add_handler(CommandHandler("start", comando_start))
    application.add_handler(CommandHandler("ayuda", comando_ayuda))
    application.add_handler(CommandHandler("help", comando_ayuda))
    application.add_handler(CommandHandler("limpiar", comando_limpiar))
    
    # Callbacks (botones)
    application.add_handler(CallbackQueryHandler(manejar_callbacks))
    
    # URLs (mensajes con enlaces)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        manejar_url
    ))
    
    return application

# ==================== INICIAR BOT ====================
def main():
    """Función principal para iniciar el bot"""
    print("=" * 50)
    print("🤖 BOT DESCARGADOR DE VIDEOS - VERSIÓN MEJORADA")
    print("=" * 50)

    # VERIFICACIÓN CORREGIDA - Solo formato básico
    if not TOKEN or ":" not in TOKEN or len(TOKEN) < 30:
        print("❌ ERROR: Token inválido o no configurado")
        print("   Formato esperado: '1234567890:ABCdefGhIJKlmNoPQRsTUVwxyZ'")
        print("   Usa variable de entorno o edita config.py")
        return
    
    # Mostrar solo parte del token por seguridad
    partes_token = TOKEN.split(":")
    if len(partes_token) >= 2:
        print(f"✅ Token configurado: {partes_token[0]}:...{partes_token[1][-6:]}")
    else:
        print(f"✅ Token configurado (longitud: {len(TOKEN)})")
    
    print(f"📁 Carpeta de descargas: {DOWNLOAD_PATH}")
    print(f"📏 Tamaño máximo: {MAX_FILE_SIZE/1024/1024:.0f}MB")
    print(f"🔧 Cache: {'HABILITADO' if CACHE_ENABLED else 'DESHABILITADO'}")
    print(f"🖼️ Thumbnails: {'HABILITADOS' if GENERATE_THUMBNAILS else 'DESHABILITADOS'}")
    print("=" * 50)
    print("🟢 Iniciando bot... (Ctrl+C para detener)")
    print("=" * 50)

    try:
        # Limpiar cache expirado al inicio
        if CACHE_ENABLED:
            video_cache.clear_expired()

        # Configurar y ejecutar bot
        application = configurar_bot()
        application.run_polling(drop_pending_updates=True)

    except KeyboardInterrupt:
        print("\n⏹️ Bot detenido por el usuario")

    except Exception as e:
        logger.error(f"Error fatal: {e}")
        print(f"❌ Error fatal: {e}")