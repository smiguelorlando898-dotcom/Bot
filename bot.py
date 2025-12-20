# bot.py - Sistema de Recargas Rápidas (Versión Simplificada para Render)
import logging
import asyncio
import sys
import time
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, CallbackContext
import sqlite3

# ==================== CONFIGURACIÓN ====================
TOKEN_CLIENTE = "8120597277:AAFsKTgowtm_rApAotAL0L-lYhyQEvJ1m4g"
ADMIN_USERNAME = "landitho9"  # Tu username SIN @
ADMIN_CHAT_ID = None  # Se detectará automáticamente al usar /admin
NUMERO_RECIBIR_SALDO = "50321300"

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== BASE DE DATOS (SIMPLIFICADA) ====================
def init_database():
    conn = sqlite3.connect('recargas_rapidas.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pedidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            user_name TEXT NOT NULL,
            numero_destino TEXT,
            producto_nombre TEXT NOT NULL,
            precio REAL NOT NULL,
            estado TEXT DEFAULT 'solicitado',
            fecha TEXT NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS config (
            clave TEXT PRIMARY KEY,
            valor TEXT NOT NULL
        )
    ''')
    cursor.execute("INSERT OR IGNORE INTO config (clave, valor) VALUES ('service_active', 'yes')")
    conn.commit()
    conn.close()

def get_service_status():
    conn = sqlite3.connect('recargas_rapidas.db')
    cursor = conn.cursor()
    cursor.execute("SELECT valor FROM config WHERE clave = 'service_active'")
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 'yes'

def set_service_status(status):
    conn = sqlite3.connect('recargas_rapidas.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO config (clave, valor) VALUES (?, ?)", ('service_active', status))
    conn.commit()
    conn.close()

def crear_pedido(user_id, user_name, producto_nombre, precio, numero_destino):
    conn = sqlite3.connect('recargas_rapidas.db')
    cursor = conn.cursor()
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('''
        INSERT INTO pedidos (user_id, user_name, numero_destino, producto_nombre, precio, estado, fecha)
        VALUES (?, ?, ?, ?, ?, 'solicitado', ?)
    ''', (user_id, user_name, numero_destino, producto_nombre, precio, fecha))
    pedido_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return pedido_id

def get_pedidos_pendientes():
    conn = sqlite3.connect('recargas_rapidas.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pedidos WHERE estado = 'solicitado' ORDER BY fecha DESC")
    pedidos = cursor.fetchall()
    conn.close()
    return pedidos

# ==================== FUNCIONES AUXILIARES ====================
def es_administrador(usuario):
    return usuario.username and usuario.username.lower() == ADMIN_USERNAME.lower()

async def enviar_notificacion_admin(context: CallbackContext, mensaje: str, keyboard=None):
    """Envía una notificación directa al administrador (@landitho9)"""
    global ADMIN_CHAT_ID
    if ADMIN_CHAT_ID:
        try:
            if keyboard:
                await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=mensaje, reply_markup=keyboard, parse_mode='Markdown')
            else:
                await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=mensaje, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Error enviando notificación: {e}")

# ==================== HANDLERS CLIENTE ====================
async def start(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    
    # Detectar si eres el administrador
    global ADMIN_CHAT_ID
    if es_administrador(user):
        ADMIN_CHAT_ID = update.effective_chat.id
        logger.info(f"✅ Chat ID de administrador detectado: {ADMIN_CHAT_ID}")
        await admin(update, context)
        return
    
    # Verificar servicio activo para clientes normales
    if get_service_status() != 'yes':
        await update.message.reply_text(
            "⏸️ *SERVICIO TEMPORALMENTE NO DISPONIBLE*\n\n"
            "En este momento no hay fondos disponibles para procesar nuevas recargas. "
            "Por favor, inténtalo de nuevo más tarde.",
            parse_mode='Markdown'
        )
        return
    
    # Menú para clientes normales
    welcome_message = f"""
🚀 **SERVICIO DE ACTIVACIÓN DE PLANES ETECSA**

👋 *¡Hola {user.first_name}!* 

**Planes disponibles:**
📡 **Datos:** 600 MB toDus - 10 CUP
📞 **Voz:** 10 minutos - 18 CUP
💬 **SMS:** 50 mensajes - 8 CUP

👇 *Para solicitar un plan, escribe:* /solicitar
    """
    await update.message.reply_text(welcome_message, parse_mode='Markdown')

async def solicitar(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    
    # Lista de productos (puedes expandir esto)
    productos = [
        {"id": 1, "nombre": "600 MB toDus", "precio": 10.0, "categoria": "datos"},
        {"id": 2, "nombre": "10 minutos de voz", "precio": 18.0, "categoria": "voz"},
        {"id": 3, "nombre": "50 SMS", "precio": 8.0, "categoria": "sms"}
    ]
    
    mensaje = "📋 *Selecciona un plan:*\n\n"
    keyboard = []
    for prod in productos:
        mensaje += f"• {prod['nombre']} - {prod['precio']} CUP\n"
        keyboard.append([InlineKeyboardButton(f"🛒 {prod['nombre']} - {prod['precio']} CUP", 
                      callback_data=f"seleccionar_{prod['id']}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Cancelar", callback_data="cancelar")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(mensaje, reply_markup=reply_markup, parse_mode='Markdown')

async def button_handler(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("seleccionar_"):
        producto_id = int(query.data.split('_')[1])
        # Productos de ejemplo
        productos = {
            1: {"nombre": "600 MB toDus", "precio": 10.0},
            2: {"nombre": "10 minutos de voz", "precio": 18.0},
            3: {"nombre": "50 SMS", "precio": 8.0}
        }
        
        producto = productos.get(producto_id)
        if producto:
            context.user_data['producto_seleccionado'] = producto
            await query.edit_message_text(
                f"✅ *Has seleccionado:*\n"
                f"**{producto['nombre']}**\n"
                f"💰 *Precio:* {producto['precio']} CUP\n\n"
                f"📱 *Ahora escribe tu número de teléfono* (ej: 52123456):",
                parse_mode='Markdown'
            )
    
    elif query.data.startswith("confirmar_pedido_"):
        pedido_id = int(query.data.split('_')[2])
        # Aquí iría la lógica para confirmar el pedido
        await query.edit_message_text(f"✅ Pedido #{pedido_id} confirmado. Se han enviado instrucciones al cliente.")
    
    elif query.data.startswith("rechazar_pedido_"):
        pedido_id = int(query.data.split('_')[2])
        # Aquí iría la lógica para rechazar el pedido
        await query.edit_message_text(f"❌ Pedido #{pedido_id} rechazado.")

async def recibir_numero(update: Update, context: CallbackContext) -> None:
    if 'producto_seleccionado' not in context.user_data:
        return
    
    numero = update.message.text.strip()
    if not numero.isdigit() or len(numero) < 6:
        await update.message.reply_text("❌ Número inválido. Por favor, escribe solo números (ej: 52123456):")
        return
    
    producto = context.user_data['producto_seleccionado']
    user = update.effective_user
    
    # Crear pedido
    pedido_id = crear_pedido(
        user_id=user.id,
        user_name=user.full_name,
        producto_nombre=producto['nombre'],
        precio=producto['precio'],
        numero_destino=numero
    )
    
    # Notificar al cliente
    await update.message.reply_text(
        f"✅ *Solicitud #{pedido_id} recibida*\n\n"
        f"Hemos recibido tu solicitud de **{producto['nombre']}**\n"
        f"Para el número: `{numero}`\n"
        f"Precio: {producto['precio']} CUP\n\n"
        f"📬 *Estado:* 🟡 **Esperando confirmación**\n"
        f"Te notificaremos cuando puedas realizar el pago.",
        parse_mode='Markdown'
    )
    
    # ENVIAR NOTIFICACIÓN AL ADMINISTRADOR (A TI)
    mensaje_admin = f"""
📨 *¡NUEVA SOLICITUD!*

📋 **Solicitud #** `{pedido_id}`
👤 **Cliente:** {user.full_name} (@{user.username if user.username else 'Sin usuario'})
📱 **Número destino:** `{numero}`
📦 **Producto:** {producto['nombre']}
💰 **Monto:** {producto['precio']} CUP
🕒 **Fecha:** {datetime.now().strftime("%d/%m/%Y %H:%M")}
    """
    
    keyboard = [
        [
            InlineKeyboardButton("✅ CONFIRMAR", callback_data=f"confirmar_pedido_{pedido_id}"),
            InlineKeyboardButton("❌ RECHAZAR", callback_data=f"rechazar_pedido_{pedido_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Esto te envía la notificación directamente a tu chat privado con el bot
    await enviar_notificacion_admin(context, mensaje_admin, reply_markup)
    
    # Limpiar datos temporales
    context.user_data.clear()

# ==================== HANDLERS ADMIN (SOLO PARA TI) ====================
async def admin(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    if not es_administrador(user):
        return
    
    pedidos_pendientes = get_pedidos_pendientes()
    
    mensaje = f"""
🛠️ *PANEL DE ADMINISTRACIÓN*

👑 **Administrador:** {user.full_name} (@{user.username})
📊 **Solicitudes pendientes:** {len(pedidos_pendientes)}
🔧 **Estado del servicio:** {'🟢 ACTIVO' if get_service_status() == 'yes' else '🔴 PAUSADO'}

*Comandos disponibles:*
/fondosno - Pausar servicio
/fondosyes - Reactivar servicio
/pedidos - Ver solicitudes pendientes
    """
    
    await update.message.reply_text(mensaje, parse_mode='Markdown')

async def fondos_no(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    if not es_administrador(user):
        return
    
    set_service_status('no')
    await update.message.reply_text("✅ *Servicio PAUSADO*\n\nLos usuarios no podrán realizar nuevas solicitudes.", parse_mode='Markdown')

async def fondos_yes(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    if not es_administrador(user):
        return
    
    set_service_status('yes')
    await update.message.reply_text("✅ *Servicio ACTIVADO*\n\nLos usuarios ya pueden realizar solicitudes.", parse_mode='Markdown')

async def pedidos(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    if not es_administrador(user):
        return
    
    pedidos_lista = get_pedidos_pendientes()
    
    if not pedidos_lista:
        await update.message.reply_text("📭 No hay solicitudes pendientes.")
        return
    
    mensaje = "📋 *SOLICITUDES PENDIENTES:*\n\n"
    for pedido in pedidos_lista[:5]:  # Mostrar máximo 5
        pedido_id, user_id, user_name, numero, producto, precio, estado, fecha = pedido
        mensaje += f"• *Solicitud #{pedido_id}*\n"
        mensaje += f"  👤 {user_name}\n"
        mensaje += f"  📱 `{numero}`\n"
        mensaje += f"  📦 {producto}\n"
        mensaje += f"  💰 {precio} CUP\n"
        mensaje += f"  🕒 {fecha}\n\n"
    
    await update.message.reply_text(mensaje, parse_mode='Markdown')

# ==================== INICIALIZACIÓN ====================
def run_bot():
    """Función principal simplificada y estable para Render"""
    
    # Inicializar base de datos
    init_database()
    
    print("""
    ============================================
    🚀 SISTEMA DE RECARGAS RÁPIDAS - INICIANDO
    ============================================
    🤖 Bot: @RecargasRBot
    👑 Admin: @landitho9
    💳 Número saldo: 50321300
    🔧 Servicio: ACTIVO
    ============================================
    """)
    
    async def main():
        # Crear aplicación
        app = Application.builder().token(TOKEN_CLIENTE).build()
        
        # Handlers para clientes (siempre activos)
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("solicitar", solicitar))
        app.add_handler(CallbackQueryHandler(button_handler))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_numero))
        
        # Handlers para administrador (solo responden si eres tú)
        app.add_handler(CommandHandler("admin", admin))
        app.add_handler(CommandHandler("fondosno", fondos_no))
        app.add_handler(CommandHandler("fondosyes", fondos_yes))
        app.add_handler(CommandHandler("pedidos", pedidos))
        
        print("✅ Bot configurado correctamente")
        print("🔄 Iniciando... (usa CTRL+C para detener)")
        
        # Iniciar bot con polling
        await app.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
            close_loop=False
        )
    
    # Configurar y ejecutar el event loop
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot detenido por el usuario")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("🔄 Reiniciando en 5 segundos...")
        time.sleep(5)
        run_bot()

if __name__ == '__main__':
    run_bot()