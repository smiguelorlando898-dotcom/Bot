# bot.py - Sistema completo de Recargas Rápidas para Telegram
# Incluye bot para clientes y bot para administrador en un solo archivo
import logging
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, CallbackContext
from telegram.error import BadRequest
import sqlite3
import time
import os

# ==================== CONFIGURACIÓN ====================
# ⚠️ REEMPLAZAR CON TUS TOKENS REALES
TOKEN_CLIENTE = "8120597277:AAFsKTgowtm_rApAotAL0L-lYhyQEvJ1m4g"  # Token de @RecargasRBot
TOKEN_ADMIN = "8410026862:AAEq0HxRKFV-tjz9U8RVfwS74mgL3ELa1Dc"      # Token de @AdminRecargasRBot

# ⚠️ REEMPLAZAR CON TU INFORMACIÓN REAL
NUMERO_RECIBIR_SALDO = "50321300"
ADMIN_USERNAME = "@landitho9"  # Tu username de Telegram (con @)
BOT_USERNAME = "@RecargasRBot"  # Nombre del bot cliente
BOT_USERNAME_ADMIN = "@ARecargasRBot"  # Nombre del bot admin

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('recargas_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==================== BASE DE DATOS ====================
def init_database():
    """Inicializa la base de datos SQLite con tablas necesarias"""
    conn = sqlite3.connect('recargas_rapidas.db')
    cursor = conn.cursor()
    
    # Tabla de productos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            categoria TEXT NOT NULL,
            nombre TEXT NOT NULL,
            descripcion TEXT,
            precio_saldo REAL NOT NULL,
            activo INTEGER DEFAULT 1
        )
    ''')
    
    # Tabla de pedidos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pedidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            user_name TEXT NOT NULL,
            numero_destino TEXT,
            producto_id INTEGER NOT NULL,
            precio REAL NOT NULL,
            estado TEXT DEFAULT 'solicitado',
            captura_file_id TEXT,
            fecha TEXT NOT NULL,
            procesado_por TEXT,
            etapa TEXT DEFAULT 'solicitud',
            FOREIGN KEY (producto_id) REFERENCES productos (id)
        )
    ''')
    
    # Tabla de configuración
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS config (
            clave TEXT PRIMARY KEY,
            valor TEXT NOT NULL
        )
    ''')
    
    # Configuración inicial
    cursor.execute("SELECT valor FROM config WHERE clave = 'service_active'")
    if cursor.fetchone() is None:
        cursor.execute("INSERT INTO config (clave, valor) VALUES ('service_active', 'yes')")
    
    # Productos iniciales
    cursor.execute("SELECT COUNT(*) FROM productos")
    if cursor.fetchone()[0] == 0:
        productos = [
            # 📡 PLANES DE DATOS
            ('datos', 'toDus (600 MB)', '600 MB para app toDus y correo Nauta', 10.0),
            
            # 📞 PLANES DE VOZ
            ('voz', '5 minutos', '5 minutos para llamadas nacionales', 10.0),
            ('voz', '10 minutos', '10 minutos para llamadas nacionales', 18.0),
            ('voz', '15 minutos', '15 minutos para llamadas nacionales', 25.0),
            ('voz', '25 minutos', '25 minutos para llamadas nacionales', 40.0),
            ('voz', '40 minutos', '40 minutos para llamadas nacionales', 60.0),
            
            # 💬 PLANES DE SMS
            ('sms', '20 SMS', '20 mensajes de texto', 4.0),
            ('sms', '50 SMS', '50 mensajes de texto', 8.0),
            ('sms', '90 SMS', '90 mensajes de texto', 12.0),
            ('sms', '120 SMS', '120 mensajes de texto', 15.0),
        ]
        
        cursor.executemany(
            "INSERT INTO productos (categoria, nombre, descripcion, precio_saldo) VALUES (?, ?, ?, ?)",
            productos
        )
    
    conn.commit()
    conn.close()

# ==================== FUNCIONES DE PRODUCTOS ====================
def get_productos_por_categoria(categoria):
    """Obtiene productos por categoría"""
    conn = sqlite3.connect('recargas_rapidas.db')
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, nombre, descripcion, precio_saldo FROM productos WHERE categoria = ? AND activo = 1 ORDER BY precio_saldo ASC",
        (categoria,)
    )
    productos = cursor.fetchall()
    conn.close()
    return productos

def get_producto_por_id(producto_id):
    """Obtiene un producto por ID"""
    conn = sqlite3.connect('recargas_rapidas.db')
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, nombre, descripcion, precio_saldo FROM productos WHERE id = ?",
        (producto_id,)
    )
    producto = cursor.fetchone()
    conn.close()
    return producto

def get_all_productos():
    """Obtiene todos los productos"""
    conn = sqlite3.connect('recargas_rapidas.db')
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, categoria, nombre, descripcion, precio_saldo FROM productos WHERE activo = 1 ORDER BY categoria, precio_saldo"
    )
    productos = cursor.fetchall()
    conn.close()
    return productos

def actualizar_precio_producto(producto_id, nuevo_precio):
    """Actualiza el precio de un producto"""
    conn = sqlite3.connect('recargas_rapidas.db')
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE productos SET precio_saldo = ? WHERE id = ?",
        (nuevo_precio, producto_id)
    )
    conn.commit()
    conn.close()

# ==================== FUNCIONES DE PEDIDOS ====================
def crear_pedido(user_id, user_name, producto_id, precio, numero_destino=None):
    """Crea un nuevo pedido"""
    conn = sqlite3.connect('recargas_rapidas.db')
    cursor = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute('''
        INSERT INTO pedidos (user_id, user_name, numero_destino, producto_id, precio, estado, fecha, etapa)
        VALUES (?, ?, ?, ?, ?, 'solicitado', ?, 'solicitud')
    ''', (user_id, user_name, numero_destino, producto_id, precio, fecha_actual))
    
    pedido_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return pedido_id

def actualizar_etapa_pedido(pedido_id, nueva_etapa):
    """Actualiza la etapa del pedido"""
    conn = sqlite3.connect('recargas_rapidas.db')
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE pedidos SET etapa = ? WHERE id = ?",
        (nueva_etapa, pedido_id)
    )
    conn.commit()
    conn.close()

def confirmar_pedido_admin(pedido_id, admin_username):
    """Confirma el pedido por parte del administrador"""
    conn = sqlite3.connect('recargas_rapidas.db')
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE pedidos SET estado = 'confirmado', etapa = 'esperando_pago', procesado_por = ? WHERE id = ?",
        (admin_username, pedido_id)
    )
    conn.commit()
    conn.close()

def actualizar_captura_pedido(pedido_id, captura_file_id):
    """Actualiza la captura del pedido"""
    conn = sqlite3.connect('recargas_rapidas.db')
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE pedidos SET captura_file_id = ?, estado = 'en_proceso', etapa = 'verificando_pago' WHERE id = ?",
        (captura_file_id, pedido_id)
    )
    conn.commit()
    conn.close()

def completar_pedido(pedido_id, admin_username):
    """Marca el pedido como completado"""
    conn = sqlite3.connect('recargas_rapidas.db')
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE pedidos SET estado = 'completado', etapa = 'finalizado', procesado_por = ? WHERE id = ?",
        (admin_username, pedido_id)
    )
    conn.commit()
    conn.close()

def cancelar_pedido(pedido_id, admin_username):
    """Cancela un pedido"""
    conn = sqlite3.connect('recargas_rapidas.db')
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE pedidos SET estado = 'cancelado', etapa = 'cancelado', procesado_por = ? WHERE id = ?",
        (admin_username, pedido_id)
    )
    conn.commit()
    conn.close()

def get_pedidos_por_estado(estado=None):
    """Obtiene pedidos por estado"""
    conn = sqlite3.connect('recargas_rapidas.db')
    cursor = conn.cursor()
    
    if estado:
        cursor.execute(
            "SELECT p.*, pr.nombre as producto_nombre FROM pedidos p JOIN productos pr ON p.producto_id = pr.id WHERE p.estado = ? ORDER BY p.fecha DESC",
            (estado,)
        )
    else:
        cursor.execute(
            "SELECT p.*, pr.nombre as producto_nombre FROM pedidos p JOIN productos pr ON p.producto_id = pr.id ORDER BY p.fecha DESC"
        )
    
    pedidos = cursor.fetchall()
    conn.close()
    return pedidos

def get_pedido_por_id(pedido_id):
    """Obtiene un pedido por ID"""
    conn = sqlite3.connect('recargas_rapidas.db')
    cursor = conn.cursor()
    cursor.execute(
        "SELECT p.*, pr.nombre as producto_nombre FROM pedidos p JOIN productos pr ON p.producto_id = pr.id WHERE p.id = ?",
        (pedido_id,)
    )
    pedido = cursor.fetchone()
    conn.close()
    return pedido

def get_pedidos_por_usuario(user_id):
    """Obtiene pedidos de un usuario"""
    conn = sqlite3.connect('recargas_rapidas.db')
    cursor = conn.cursor()
    cursor.execute(
        "SELECT p.*, pr.nombre as producto_nombre FROM pedidos p JOIN productos pr ON p.producto_id = pr.id WHERE p.user_id = ? ORDER BY p.fecha DESC",
        (user_id,)
    )
    pedidos = cursor.fetchall()
    conn.close()
    return pedidos

def get_pedidos_pendientes_confirmacion():
    """Obtiene pedidos pendientes de confirmación del administrador"""
    return get_pedidos_por_estado('solicitado')

def get_pedidos_esperando_pago():
    """Obtiene pedidos confirmados esperando pago"""
    return get_pedidos_por_estado('confirmado')

def get_pedidos_verificando_pago():
    """Obtiene pedidos con pago enviado para verificar"""
    return get_pedidos_por_estado('en_proceso')

# ==================== FUNCIONES DE CONFIGURACIÓN ====================
def get_service_status():
    """Obtiene el estado del servicio"""
    conn = sqlite3.connect('recargas_rapidas.db')
    cursor = conn.cursor()
    cursor.execute("SELECT valor FROM config WHERE clave = 'service_active'")
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 'yes'

def set_service_status(status):
    """Establece el estado del servicio"""
    conn = sqlite3.connect('recargas_rapidas.db')
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO config (clave, valor) VALUES (?, ?)",
        ('service_active', status)
    )
    conn.commit()
    conn.close()

def get_estadisticas():
    """Obtiene estadísticas del sistema"""
    conn = sqlite3.connect('recargas_rapidas.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM productos WHERE activo = 1")
    total_productos = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM pedidos")
    total_pedidos = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM pedidos WHERE estado = 'solicitado'")
    solicitados = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM pedidos WHERE estado = 'confirmado'")
    confirmados = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM pedidos WHERE estado = 'en_proceso'")
    en_proceso = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM pedidos WHERE estado = 'completado'")
    completados = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(precio) FROM pedidos WHERE estado = 'completado'")
    total_ventas = cursor.fetchone()[0] or 0
    
    conn.close()
    
    return {
        'total_productos': total_productos,
        'total_pedidos': total_pedidos,
        'solicitados': solicitados,
        'confirmados': confirmados,
        'en_proceso': en_proceso,
        'completados': completados,
        'total_ventas': total_ventas
    }

# ==================== FUNCIONES AUXILIARES ====================
def precio_formateado(precio):
    """Formatea el precio"""
    return f"{precio:.0f}" if precio.is_integer() else f"{precio:.1f}"

def es_administrador(usuario):
    """Verifica si el usuario es administrador"""
    return usuario.username and usuario.username.lower() == ADMIN_USERNAME.replace('@', '').lower()

# ==================== GESTOR DE APLICACIONES ====================
# Variables globales para las aplicaciones
cliente_app = None
admin_app = None

# ==================== BOT CLIENTE ====================
async def check_service_active(update: Update, context: CallbackContext, send_message=True):
    """Verifica si el servicio está activo"""
    status = get_service_status()
    
    if status != 'yes' and send_message:
        mensaje = (
            "⏸️ *SERVICIO TEMPORALMENTE NO DISPONIBLE*\n\n"
            "En este momento no hay fondos disponibles para procesar nuevas recargas. "
            "Estamos trabajando para restablecer el servicio lo antes posible.\n\n"
            "Por favor, inténtalo de nuevo más tarde. ¡Gracias por tu comprensión! 🙏"
        )
        
        keyboard = [[InlineKeyboardButton("🔄 Reintentar", callback_data="reintentar_start")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(mensaje, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.message.reply_text(mensaje, reply_markup=reply_markup, parse_mode='Markdown')
        
        return False
    
    return status == 'yes'

async def start(update: Update, context: CallbackContext) -> None:
    """Comando /start - Menú principal para clientes"""
    user = update.effective_user
    
    # Verificar servicio activo
    if not await check_service_active(update, context):
        return
    
    welcome_message = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🚀 **SERVICIO DE ACTIVACIÓN DE PLANES ETECSA**  
*(Pago exclusivo mediante Transferencia de Saldo Móvil)*  

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

👋 *¡Hola {user.first_name}!* 

**¿Cómo funciona? (3 pasos simples)**  
1️⃣ Selecciona el plan que necesitas  
2️⃣ Envías tu número de teléfono  
3️⃣ Esperas nuestra confirmación para realizar el pago  

✅ *Tu activación será procesada en cuanto confirmemos tu pago*

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

👇 *Selecciona una categoría para comenzar:*
    """
    
    keyboard = [
        [InlineKeyboardButton("📡 DATOS", callback_data="cat_datos")],
        [InlineKeyboardButton("📞 MINUTOS DE VOZ", callback_data="cat_voz")],
        [InlineKeyboardButton("💬 MENSAJES SMS", callback_data="cat_sms")],
        [
            InlineKeyboardButton("📋 VER TODOS LOS PLANES", callback_data="ver_todos"),
            InlineKeyboardButton("❓ AYUDA", callback_data="ayuda")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(welcome_message, reply_markup=reply_markup, parse_mode='Markdown')
    elif update.callback_query:
        await update.callback_query.edit_message_text(welcome_message, reply_markup=reply_markup, parse_mode='Markdown')

async def ver_todos_planes(update: Update, context: CallbackContext) -> None:
    """Muestra todos los planes disponibles"""
    query = update.callback_query
    await query.answer()
    
    productos = get_all_productos()
    
    if not productos:
        mensaje = "📭 No hay productos disponibles por el momento."
        keyboard = [[InlineKeyboardButton("🔙 VOLVER", callback_data="volver_inicio")]]
    else:
        mensaje = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        mensaje += "📋 **PLANES DISPONIBLES Y TARIFAS**\n\n"
        mensaje += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        categorias_mostradas = {}
        
        for producto in productos:
            id_prod, categoria, nombre, descripcion, precio = producto
            
            if categoria not in categorias_mostradas:
                categorias_mostradas[categoria] = []
            
            categorias_mostradas[categoria].append((id_prod, nombre, descripcion, precio))
        
        # Mostrar por categorías
        for cat, prods in categorias_mostradas.items():
            if cat == 'datos':
                mensaje += "📡 **DATOS**\n"
            elif cat == 'voz':
                mensaje += "📞 **VOZ**\n"
            elif cat == 'sms':
                mensaje += "💬 **SMS**\n"
            
            for prod in prods:
                id_prod, nombre, descripcion, precio = prod
                mensaje += f"• **{nombre}** → {precio_formateado(precio)} CUP\n"
            
            mensaje += "\n"
        
        mensaje += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        mensaje += "👇 *Selecciona el plan que deseas solicitar:*"
        
        # Crear teclado con productos
        keyboard = []
        for producto in productos:
            id_prod, _, nombre, _, precio = producto
            keyboard.append([
                InlineKeyboardButton(
                    f"🛒 {nombre} - {precio_formateado(precio)} CUP",
                    callback_data=f"seleccionar_{id_prod}"
                )
            ])
        
        # Botones de navegación
        keyboard.append([
            InlineKeyboardButton("🔙 VOLVER AL INICIO", callback_data="volver_inicio"),
            InlineKeyboardButton("❓ AYUDA", callback_data="ayuda")
        ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(mensaje, reply_markup=reply_markup, parse_mode='Markdown')

async def ayuda(update: Update, context: CallbackContext) -> None:
    """Muestra información de ayuda"""
    ayuda_text = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 **INFORMACIÓN COMPLETA DEL SERVICIO**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔹 **¿Cómo funciona?**  
1. Selecciona el plan que necesitas  
2. Envía tu número de teléfono  
3. Espera nuestra confirmación  
4. Realiza el pago cuando te lo indiquemos  
5. Envía la captura del comprobante  

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💳 **INSTRUCCIONES DE PAGO**  
- Realiza el pago exacto según el plan seleccionado  
- Método: **Transferencia de Saldo Móvil**  
- Número destino: **`{NUMERO_RECIBIR_SALDO}`**  
- Adjunta comprobante mediante captura clara y legible  

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✨ **VENTAJAS DEL SERVICIO**  
✅ Todo el proceso se gestiona desde Telegram  
✅ Activación rápida y confiable  
✅ Aprovecha al máximo tu saldo disponible  
✅ Atención personalizada 24/7  

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ **INFORMACIÓN IMPORTANTE**  
- El pago se acepta únicamente por transferencia de saldo móvil  
- La captura debe ser nítida y verificable  
- Solo realiza el pago después de nuestra confirmación  

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

👨‍💼 **CONTACTO Y SOPORTE**  
Para asistencia directa: {ADMIN_USERNAME}  

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    """
    
    keyboard = [
        [InlineKeyboardButton("🛒 VER PLANES", callback_data="ver_todos")],
        [InlineKeyboardButton("🔙 VOLVER AL INICIO", callback_data="volver_inicio")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(ayuda_text, reply_markup=reply_markup, parse_mode='Markdown')

async def mostrar_categoria(update: Update, context: CallbackContext, categoria: str) -> None:
    """Muestra productos de una categoría específica"""
    if not await check_service_active(update, context, send_message=False):
        await update.callback_query.answer("⚠️ El servicio no está disponible temporalmente.", show_alert=True)
        return
    
    query = update.callback_query
    await query.answer()
    
    categorias_map = {
        'cat_datos': 'datos',
        'cat_voz': 'voz',
        'cat_sms': 'sms'
    }
    
    categoria_db = categorias_map.get(categoria, categoria)
    productos = get_productos_por_categoria(categoria_db)
    
    if not productos:
        mensaje = "📭 No hay productos disponibles en esta categoría por el momento."
        keyboard = [[InlineKeyboardButton("🔙 VOLVER", callback_data="volver_inicio")]]
    else:
        titulos = {
            'datos': "📡 **DATOS**\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n",
            'voz': "📞 **VOZ**\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n",
            'sms': "💬 **SMS**\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        }
        
        mensaje = titulos.get(categoria_db, "📋 **PRODUCTOS**\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n")
        
        for producto in productos:
            id_prod, nombre, descripcion, precio = producto
            mensaje += f"• **{nombre}** → {precio_formateado(precio)} CUP\n"
            if descripcion:
                mensaje += f"  _{descripcion}_\n"
            mensaje += "\n"
        
        mensaje += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        mensaje += "👇 *Selecciona el plan que deseas solicitar:*"
        
        keyboard = []
        for producto in productos:
            id_prod, nombre, _, precio = producto
            keyboard.append([
                InlineKeyboardButton(
                    f"🛒 {nombre} - {precio_formateado(precio)} CUP",
                    callback_data=f"seleccionar_{id_prod}"
                )
            ])
        
        keyboard.append([
            InlineKeyboardButton("📋 VER TODOS", callback_data="ver_todos"),
            InlineKeyboardButton("🔙 INICIO", callback_data="volver_inicio")
        ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(mensaje, reply_markup=reply_markup, parse_mode='Markdown')

async def seleccionar_producto(update: Update, context: CallbackContext) -> None:
    """Procesa la selección de un producto"""
    if not await check_service_active(update, context, send_message=False):
        await update.callback_query.answer("⚠️ El servicio no está disponible temporalmente.", show_alert=True)
        return
    
    query = update.callback_query
    await query.answer()
    
    producto_id = int(query.data.split('_')[1])
    producto = get_producto_por_id(producto_id)
    
    if not producto:
        await query.edit_message_text("❌ Producto no encontrado.")
        return
    
    id_prod, nombre, descripcion, precio = producto
    
    # Guardar producto en contexto
    context.user_data['producto_seleccionado'] = {
        'id': id_prod,
        'nombre': nombre,
        'precio': precio
    }
    
    mensaje = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ **HAS SELECCIONADO:**

**{nombre}**
{descripcion if descripcion else ''}

💰 **Precio:** {precio_formateado(precio)} CUP

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 **PARA SOLICITAR ESTE PLAN:**

1. **Envía tu número de teléfono** (ej: 52123456)
   *Este es el número donde se activará el plan*

2. **Espera nuestra confirmación**
   *Te notificaremos cuando puedas realizar el pago*

3. **Realiza el pago cuando te lo indiquemos**
   *Transferencia de saldo móvil a {NUMERO_RECIBIR_SALDO}*

4. **Envía la captura del comprobante**

⚠️ **IMPORTANTE:**
• Solo realiza el pago después de nuestra confirmación
• Solo aceptamos TRANSFERENCIA DE SALDO MÓVIL

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

👇 **¿Deseas solicitar este plan?**
    """
    
    keyboard = [
        [InlineKeyboardButton("✅ SI, SOLICITAR ESTE PLAN", callback_data="solicitar_plan")],
        [
            InlineKeyboardButton("🔙 VER OTROS", callback_data="ver_todos"),
            InlineKeyboardButton("🏠 INICIO", callback_data="volver_inicio")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(mensaje, reply_markup=reply_markup, parse_mode='Markdown')

async def solicitar_plan(update: Update, context: CallbackContext) -> None:
    """Inicia el proceso de solicitud"""
    query = update.callback_query
    await query.answer()
    
    producto = context.user_data.get('producto_seleccionado')
    
    if not producto:
        await query.edit_message_text("❌ Error: No se encontró el producto seleccionado.")
        return
    
    mensaje = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔄 **SOLICITANDO PLAN**

**Producto:** {producto['nombre']}
**Precio:** {precio_formateado(producto['precio'])} CUP

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📱 **PASO 1: ENVÍA TU NÚMERO**

Por favor, escribe tu **número de teléfono** (ej: 52123456) para recibir la activación:

⚠️ **Asegúrate de que sea el número correcto**, ya que allí se activará el plan.

*Después de enviar tu número, espera nuestra confirmación antes de realizar cualquier pago.*
    """
    
    # Guardar estado para esperar el número
    context.user_data['esperando_numero'] = True
    
    keyboard = [[InlineKeyboardButton("🔙 CANCELAR", callback_data="cancelar_solicitud")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(mensaje, reply_markup=reply_markup, parse_mode='Markdown')

async def recibir_numero(update: Update, context: CallbackContext) -> None:
    """Recibe y procesa el número de teléfono"""
    if not context.user_data.get('esperando_numero'):
        return
    
    numero = update.message.text.strip()
    
    # Validación básica
    if not numero.isdigit() or len(numero) < 6:
        await update.message.reply_text(
            "❌ Número inválido. Por favor, escribe solo números (ej: 52123456):",
            parse_mode='Markdown'
        )
        return
    
    # Guardar número
    context.user_data['numero_destino'] = numero
    
    producto = context.user_data.get('producto_seleccionado')
    
    if not producto:
        await update.message.reply_text("❌ Error en los datos del pedido. Por favor, inicia nuevamente.")
        return
    
    # Crear pedido en la base de datos
    user = update.effective_user
    pedido_id = crear_pedido(
        user_id=user.id,
        user_name=user.full_name,
        producto_id=producto['id'],
        precio=producto['precio'],
        numero_destino=numero
    )
    
    # Limpiar datos temporales
    context.user_data.clear()
    
    # Mensaje al cliente
    mensaje_cliente = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ **SOLICITUD RECIBIDA**

**Número de solicitud:** `#{pedido_id}`
**Producto:** {producto['nombre']}
**Precio:** {precio_formateado(producto['precio'])} CUP
**Número destino:** `{numero}`
**Fecha:** {datetime.now().strftime("%d/%m/%Y %H:%M")}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 **ESTADO:** 🟡 **ESPERANDO CONFIRMACIÓN**

Hemos recibido tu solicitud correctamente.

⏱️ **Proceso:**
1. Nuestro equipo revisará tu solicitud
2. Te notificaremos cuando puedas realizar el pago
3. Realiza la transferencia cuando te lo indiquemos
4. Envía la captura del comprobante

📬 **Recibirás una notificación** cuando tu solicitud sea confirmada.

⚠️ **No realices ningún pago hasta recibir nuestra confirmación.**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✨ **¡Gracias por tu solicitud!** 🙏
    """
    
    # Enviar notificación al administrador inmediatamente
    await notificar_administrador_nueva_solicitud(
        admin_app, 
        pedido_id, 
        user, 
        {'nombre': producto['nombre'], 'precio': producto['precio']}, 
        numero
    )
    
    keyboard = [[InlineKeyboardButton("🏠 VOLVER AL INICIO", callback_data="volver_inicio")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(mensaje_cliente, reply_markup=reply_markup, parse_mode='Markdown')

async def recibir_captura_pago(update: Update, context: CallbackContext) -> None:
    """Recibe la captura de pago del cliente"""
    user = update.effective_user
    
    # Verificar si el usuario tiene pedidos en espera de pago
    pedidos_usuario = get_pedidos_por_usuario(user.id)
    pedido_pendiente = None
    
    for pedido in pedidos_usuario:
        if pedido[6] == 'confirmado':  # estado = confirmado
            pedido_pendiente = pedido
            break
    
    if not pedido_pendiente:
        # Si no tiene pedidos confirmados
        await update.message.reply_text(
            "No tienes solicitudes pendientes de pago. "
            "Por favor, espera a que confirmemos tu solicitud antes de enviar el pago.",
            parse_mode='Markdown'
        )
        return
    
    # Obtener file_id de la foto
    if update.message.photo:
        photo = update.message.photo[-1]
        file_id = photo.file_id
    else:
        await update.message.reply_text("❌ Por favor, envía una imagen (captura de pantalla).")
        return
    
    pedido_id = pedido_pendiente[0]
    
    # Actualizar pedido con la captura
    actualizar_captura_pedido(pedido_id, file_id)
    
    # Mensaje de confirmación al cliente
    mensaje_cliente = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ **CAPTURA RECIBIDA**

📋 **Solicitud #** `{pedido_id}`
📦 **Producto:** {pedido_pendiente[10]}  # producto_nombre
💰 **Monto:** {precio_formateado(pedido_pendiente[5])} CUP

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Hemos recibido tu comprobante de pago correctamente.

⏱️ **Nuestro equipo verificará tu pago y activará tu plan.**

📬 **Recibirás una notificación** cuando tu plan sea activado.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✨ **¡Gracias por tu pago!** 🙏
    """
    
    # Enviar notificación al administrador inmediatamente
    await notificar_administrador_captura(
        admin_app,
        pedido_pendiente,
        file_id,
        user
    )
    
    await update.message.reply_text(mensaje_cliente, parse_mode='Markdown')

async def ver_mis_pedidos(update: Update, context: CallbackContext) -> None:
    """Muestra los pedidos del usuario"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    pedidos = get_pedidos_por_usuario(user.id)
    
    if not pedidos:
        mensaje = "📭 No tienes solicitudes realizadas."
        keyboard = [[InlineKeyboardButton("🔙 VOLVER", callback_data="volver_inicio")]]
    else:
        mensaje = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        mensaje += "📋 **MIS SOLICITUDES**\n\n"
        mensaje += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        for pedido in pedidos[:5]:  # Mostrar máximo 5 pedidos
            pedido_id, _, _, numero_destino, _, precio, estado, _, fecha, _, producto_nombre = pedido
            
            # Iconos según estado
            iconos_estado = {
                'solicitado': '🟡',
                'confirmado': '🟢',
                'en_proceso': '🟠',
                'completado': '✅',
                'cancelado': '❌'
            }
            
            icono = iconos_estado.get(estado, '⚪')
            
            mensaje += f"{icono} **Solicitud #{pedido_id}**\n"
            mensaje += f"📦 {producto_nombre}\n"
            mensaje += f"💰 {precio_formateado(precio)} CUP\n"
            mensaje += f"📱 `{numero_destino}`\n"
            mensaje += f"📅 {fecha}\n"
            mensaje += f"**Estado:** {estado.capitalize()}\n"
            mensaje += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    keyboard = [[InlineKeyboardButton("🔙 VOLVER AL INICIO", callback_data="volver_inicio")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(mensaje, reply_markup=reply_markup, parse_mode='Markdown')

# ==================== BOT ADMINISTRADOR ====================
async def notificar_administrador_nueva_solicitud(admin_app_context, pedido_id: int, user, producto, numero_destino: str):
    """Envía notificación al administrador sobre nueva solicitud"""
    mensaje_admin = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📨 **¡NUEVA SOLICITUD DE PLAN!**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 **Solicitud #** `{pedido_id}`
👤 **Cliente:** {user.full_name} (@{user.username if user.username else 'Sin usuario'})
🆔 **ID Cliente:** `{user.id}`
📱 **Número destino:** `{numero_destino}`
📦 **Producto:** {producto['nombre']}
💰 **Monto:** {precio_formateado(producto['precio'])} CUP
🕒 **Fecha:** {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

👇 **ACCIONES DISPONIBLES:**
    """
    
    keyboard = [
        [
            InlineKeyboardButton("✅ CONFIRMAR SOLICITUD", callback_data=f"admin_confirmar_{pedido_id}"),
            InlineKeyboardButton("❌ RECHAZAR SOLICITUD", callback_data=f"admin_rechazar_{pedido_id}")
        ],
        [InlineKeyboardButton("📊 VER PANEL ADMIN", callback_data="admin_panel")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        # Enviar mensaje al administrador
        await admin_app_context.bot.send_message(
            chat_id=ADMIN_USERNAME.replace('@', ''),
            text=mensaje_admin,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error al notificar al administrador: {e}")

async def enviar_instrucciones_pago(context: CallbackContext, user_id: int, pedido_id: int, producto_nombre: str, precio: float, numero_destino: str):
    """Envía instrucciones de pago al cliente después de confirmación"""
    mensaje_pago = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ **¡SOLICITUD CONFIRMADA!**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 **Solicitud #** `{pedido_id}`
📦 **Producto:** {producto_nombre}
💰 **Monto a pagar:** {precio_formateado(precio)} CUP
📱 **Número destino:** `{numero_destino}`

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💳 **INSTRUCCIONES DE PAGO:**

1. **Realiza la transferencia de saldo móvil a:**
   `{NUMERO_RECIBIR_SALDO}`

2. **Monto exacto:** {precio_formateado(precio)} CUP

3. **Toma una captura de pantalla** del comprobante
   *Debe verse CLARA y mostrar:*
   • Número destino ({NUMERO_RECIBIR_SALDO})
   • Monto transferido ({precio_formateado(precio)} CUP)
   • Fecha y hora
   • Confirmación de la transferencia

4. **Envía la captura** por este chat

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ **IMPORTANTE:**
• Solo realiza el pago a este número: **{NUMERO_RECIBIR_SALDO}**
• Asegúrate de transferir el monto exacto
• Tu plan será activado después de verificar tu pago

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

👇 **Realiza el pago y envía la captura cuando esté listo:**
    """
    
    try:
        # Enviar al cliente usando el bot cliente
        await cliente_app.bot.send_message(
            chat_id=user_id,
            text=mensaje_pago,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error al enviar instrucciones de pago: {e}")

async def notificar_administrador_captura(admin_app_context, pedido, file_id: str, user):
    """Envía la captura al administrador para verificación"""
    pedido_id, user_id, user_name, numero_destino, producto_id, precio, estado, captura_file_id, fecha, procesado_por, producto_nombre = pedido
    
    mensaje_admin = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📸 **¡CAPTURA DE PAGO RECIBIDA!**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 **Solicitud #** `{pedido_id}`
👤 **Cliente:** {user_name} (@{user.username if user.username else 'Sin usuario'})
📱 **Número destino:** `{numero_destino}`
📦 **Producto:** {producto_nombre}
💰 **Monto:** {precio_formateado(precio)} CUP
🕒 **Fecha de pago:** {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

👇 **CAPTURA DEL COMPROBANTE:**
    """
    
    keyboard = [
        [
            InlineKeyboardButton("✅ PAGO VERIFICADO - ACTIVAR PLAN", callback_data=f"admin_completar_{pedido_id}"),
            InlineKeyboardButton("❌ PAGO NO VÁLIDO", callback_data=f"admin_cancelar_{pedido_id}")
        ],
        [InlineKeyboardButton("📊 VER PANEL ADMIN", callback_data="admin_panel")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        # Enviar mensaje con foto al administrador
        await admin_app_context.bot.send_photo(
            chat_id=ADMIN_USERNAME.replace('@', ''),
            photo=file_id,
            caption=mensaje_admin,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error al notificar al administrador: {e}")

async def monitorear_nuevas_solicitudes(context: CallbackContext):
    """Monitorea nuevas solicitudes en la base de datos (compatibilidad)"""
    # Esta función se mantiene para compatibilidad, pero ahora las notificaciones son inmediatas
    pass

async def admin(update: Update, context: CallbackContext) -> None:
    """Panel de administración"""
    user = update.effective_user
    
    # Verificar si es administrador
    if not es_administrador(user):
        await update.message.reply_text("❌ No tienes permisos para acceder a esta función.")
        return
    
    stats = get_estadisticas()
    
    mensaje = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🛠️ **PANEL DE ADMINISTRACIÓN - RECARGAS RÁPIDAS**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

👨‍💼 **Administrador:** {user.full_name} ({ADMIN_USERNAME})
📅 **Fecha:** {datetime.now().strftime("%d/%m/%Y")}
🕒 **Hora:** {datetime.now().strftime("%H:%M:%S")}
🔧 **Estado del servicio:** {'🟢 ACTIVO' if get_service_status() == 'yes' else '🔴 PAUSADO'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 **ESTADÍSTICAS DEL SISTEMA:**
• Productos activos: {stats['total_productos']}
• Total solicitudes: {stats['total_pedidos']}
• Solicitudes pendientes: {stats['solicitados']}
• Solicitudes confirmadas: {stats['confirmados']}
• Pagos en verificación: {stats['en_proceso']}
• Planes activados: {stats['completados']}
• Total en ventas: {stats['total_ventas']:.0f} CUP

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔧 **HERRAMIENTAS DISPONIBLES:**
    """
    
    keyboard = [
        [InlineKeyboardButton("📨 SOLICITUDES PENDIENTES", callback_data="admin_solicitudes_pendientes")],
        [InlineKeyboardButton("✅ SOLICITUDES CONFIRMADAS", callback_data="admin_solicitudes_confirmadas")],
        [InlineKeyboardButton("📸 PAGOS POR VERIFICAR", callback_data="admin_pagos_verificar")],
        [InlineKeyboardButton("💰 ACTUALIZAR PRECIOS", callback_data="admin_actualizar_precios")],
        [InlineKeyboardButton("📊 VER ESTADÍSTICAS DETALLADAS", callback_data="admin_estadisticas")],
        [
            InlineKeyboardButton("⏸️ PAUSAR SERVICIO", callback_data="admin_pausar_servicio"),
            InlineKeyboardButton("▶️ ACTIVAR SERVICIO", callback_data="admin_activar_servicio")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(mensaje, reply_markup=reply_markup, parse_mode='Markdown')

async def admin_solicitudes(update: Update, context: CallbackContext, estado="solicitado") -> None:
    """Muestra solicitudes al administrador"""
    query = update.callback_query
    await query.answer()
    
    if estado == 'solicitado':
        pedidos = get_pedidos_pendientes_confirmacion()
    elif estado == 'confirmado':
        pedidos = get_pedidos_esperando_pago()
    elif estado == 'en_proceso':
        pedidos = get_pedidos_verificando_pago()
    else:
        pedidos = get_pedidos_por_estado(estado)
    
    if not pedidos:
        titulos = {
            'solicitado': "solicitudes pendientes",
            'confirmado': "solicitudes confirmadas",
            'en_proceso': "pagos por verificar"
        }
        mensaje = f"📭 No hay {titulos.get(estado, 'solicitudes')} por el momento."
    else:
        titulos = {
            'solicitado': "📨 **SOLICITUDES PENDIENTES**",
            'confirmado': "✅ **SOLICITUDES CONFIRMADAS**",
            'en_proceso': "📸 **PAGOS POR VERIFICAR**"
        }
        
        mensaje = f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        mensaje += f"{titulos.get(estado, '📋 SOLICITUDES')}\n\n"
        mensaje += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        for pedido in pedidos[:10]:  # Mostrar máximo 10
            pedido_id, user_id, user_name, numero_destino, producto_id, precio, estado_pedido, captura_file_id, fecha, procesado_por, producto_nombre = pedido
            
            mensaje += f"**Solicitud #{pedido_id}**\n"
            mensaje += f"👤 {user_name}\n"
            mensaje += f"📱 Destino: `{numero_destino}`\n"
            mensaje += f"📦 {producto_nombre}\n"
            mensaje += f"💰 {precio_formateado(precio)} CUP\n"
            mensaje += f"🕒 {fecha}\n"
            
            if estado == 'solicitado':
                mensaje += f"`/procesar_{pedido_id}`\n"
            elif estado == 'en_proceso':
                mensaje += f"`/verificar_{pedido_id}`\n"
            
            mensaje += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    keyboard = []
    if estado == "solicitado":
        keyboard.append([InlineKeyboardButton("✅ CONFIRMADAS", callback_data="admin_solicitudes_confirmadas")])
        keyboard.append([InlineKeyboardButton("📸 POR VERIFICAR", callback_data="admin_pagos_verificar")])
    elif estado == "confirmado":
        keyboard.append([InlineKeyboardButton("📨 PENDIENTES", callback_data="admin_solicitudes_pendientes")])
        keyboard.append([InlineKeyboardButton("📸 POR VERIFICAR", callback_data="admin_pagos_verificar")])
    else:  # en_proceso
        keyboard.append([InlineKeyboardButton("📨 PENDIENTES", callback_data="admin_solicitudes_pendientes")])
        keyboard.append([InlineKeyboardButton("✅ CONFIRMADAS", callback_data="admin_solicitudes_confirmadas")])
    
    keyboard.append([InlineKeyboardButton("🔙 PANEL ADMIN", callback_data="admin_panel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(mensaje, reply_markup=reply_markup, parse_mode='Markdown')

async def admin_procesar_solicitud(update: Update, context: CallbackContext) -> None:
    """Procesa una solicitud (confirmar o rechazar)"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user = update.effective_user
    
    if data.startswith("admin_confirmar_"):
        pedido_id = int(data.split('_')[2])
        pedido = get_pedido_por_id(pedido_id)
        
        if not pedido:
            await query.edit_message_text("❌ Solicitud no encontrada.")
            return
        
        # Confirmar solicitud
        confirmar_pedido_admin(pedido_id, user.username)
        
        # Enviar instrucciones de pago al cliente
        pedido_id, user_id, user_name, numero_destino, producto_id, precio, estado_pedido, captura_file_id, fecha, procesado_por, producto_nombre = pedido
        
        await enviar_instrucciones_pago(
            context, user_id, pedido_id, producto_nombre, precio, numero_destino
        )
        
        await query.edit_message_text(
            f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ **SOLICITUD #{pedido_id} CONFIRMADA**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Se han enviado las instrucciones de pago al cliente.

📋 **Detalles:**
• Cliente: {user_name}
• Producto: {producto_nombre}
• Monto: {precio_formateado(precio)} CUP
• Número destino: `{numero_destino}`

El cliente ahora puede realizar el pago.
            """,
            parse_mode='Markdown'
        )
    
    elif data.startswith("admin_rechazar_"):
        pedido_id = int(data.split('_')[2])
        cancelar_pedido(pedido_id, user.username)
        
        # Notificar al cliente
        pedido = get_pedido_por_id(pedido_id)
        if pedido:
            user_id = pedido[1]
            try:
                await cliente_app.bot.send_message(
                    chat_id=user_id,
                    text=f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

❌ **SOLICITUD RECHAZADA**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Lamentamos informarte que tu solicitud #{pedido_id} ha sido rechazada.

📦 **Producto:** {pedido[10]}
💰 **Monto:** {precio_formateado(pedido[5])} CUP

**Posibles razones:**
• Información incorrecta o incompleta
• Problemas técnicos
• Disponibilidad limitada

Para más información, contacta a {ADMIN_USERNAME}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    """,
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Error al notificar al cliente: {e}")
        
        await query.edit_message_text(
            f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

❌ **SOLICITUD #{pedido_id} RECHAZADA**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

El cliente ha sido notificado del rechazo.
            """,
            parse_mode='Markdown'
        )

async def admin_completar_pedido(update: Update, context: CallbackContext) -> None:
    """Completa un pedido después de verificar el pago"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user = update.effective_user
    
    if data.startswith("admin_completar_"):
        pedido_id = int(data.split('_')[2])
        pedido = get_pedido_por_id(pedido_id)
        
        if not pedido:
            await query.edit_message_text("❌ Solicitud no encontrada.")
            return
        
        # Completar pedido
        completar_pedido(pedido_id, user.username)
        
        # Notificar al cliente
        pedido_id, user_id, user_name, numero_destino, producto_id, precio, estado_pedido, captura_file_id, fecha, procesado_por, producto_nombre = pedido
        
        try:
            await cliente_app.bot.send_message(
                chat_id=user_id,
                text=f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎉 **¡PLAN ACTIVADO CON ÉXITO!**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ **Tu plan ha sido activado correctamente.**

📋 **Detalles de la activación:**
• **Solicitud #** `{pedido_id}`
• **Producto:** {producto_nombre}
• **Monto pagado:** {precio_formateado(precio)} CUP
• **Número activado:** `{numero_destino}`
• **Fecha de activación:** {datetime.now().strftime("%d/%m/%Y %H:%M")}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✨ **¡Disfruta de tu conexión!**

📱 **Para verificar tu plan:**
• Datos: Marca *222*328#
• Minutos: Marca *222*869#
• SMS: Marca *222*767#

Si tienes algún problema, contacta a {ADMIN_USERNAME}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🙏 **¡Gracias por confiar en RECARGAS RÁPIDAS!**
                """,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error al notificar al cliente: {e}")
        
        await query.edit_message_text(
            f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ **PLAN ACTIVADO**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**Solicitud #{pedido_id} completada correctamente.**

📋 **Detalles:**
• Cliente: {user_name}
• Producto: {producto_nombre}
• Monto: {precio_formateado(precio)} CUP
• Número: `{numero_destino}`

El cliente ha sido notificado de la activación.
            """,
            parse_mode='Markdown'
        )
    
    elif data.startswith("admin_cancelar_"):
        pedido_id = int(data.split('_')[2])
        cancelar_pedido(pedido_id, user.username)
        
        # Notificar al cliente
        pedido = get_pedido_por_id(pedido_id)
        if pedido:
            user_id = pedido[1]
            try:
                await cliente_app.bot.send_message(
                    chat_id=user_id,
                    text=f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ **PROBLEMA CON EL PAGO**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Lamentamos informarte que hemos detectado un problema con tu pago.

📋 **Solicitud #{pedido_id}**
📦 **Producto:** {pedido[10]}
💰 **Monto:** {precio_formateado(pedido[5])} CUP

**Posibles razones:**
• Comprobante no válido o ilegible
• Monto incorrecto transferido
• Información no coincide

Para resolver este problema, contacta a {ADMIN_USERNAME}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    """,
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Error al notificar al cliente: {e}")
        
        await query.edit_message_text(
            f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

❌ **PAGO NO VÁLIDO**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**Solicitud #{pedido_id} cancelada por problema de pago.**

El cliente ha sido notificado del problema.
            """,
            parse_mode='Markdown'
        )

async def fondos_no(update: Update, context: CallbackContext) -> None:
    """Comando /fondosno - Desactiva el servicio"""
    user = update.effective_user
    
    if not es_administrador(user):
        await update.message.reply_text("❌ No tienes permisos para ejecutar este comando.")
        return
    
    set_service_status('no')
    
    mensaje = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⏸️ **SERVICIO PAUSADO**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ **Estado actualizado correctamente.**

📋 **Cambios aplicados:**
• Los usuarios NO podrán iniciar nuevas solicitudes
• Las solicitudes en proceso continuarán normalmente
• El panel de administración sigue activo

⚠️ **Los clientes verán este mensaje:**
_"⏸️ Por el momento, no hay fondos disponibles para procesar nuevas recargas..."_

💡 **Para reactivar el servicio, usa:** `/fondosyes`
    """
    
    await update.message.reply_text(mensaje, parse_mode='Markdown')

async def fondos_yes(update: Update, context: CallbackContext) -> None:
    """Comando /fondosyes - Reactiva el servicio"""
    user = update.effective_user
    
    if not es_administrador(user):
        await update.message.reply_text("❌ No tienes permisos para ejecutar este comando.")
        return
    
    set_service_status('yes')
    
    mensaje = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

▶️ **SERVICIO REACTIVADO**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ **Estado actualizado correctamente.**

📋 **Cambios aplicados:**
• Los usuarios YA pueden iniciar nuevas solicitudes
• El comando /start funciona normalmente
• Todas las funciones están disponible

🎉 **¡El servicio está listo para recibir solicitudes!**

💡 **Para pausar el servicio, usa:** `/fondosno`
    """
    
    await update.message.reply_text(mensaje, parse_mode='Markdown')

async def admin_actualizar_precios(update: Update, context: CallbackContext) -> None:
    """Interfaz para actualizar precios"""
    query = update.callback_query
    await query.answer()
    
    productos = get_all_productos()
    
    mensaje = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💰 **ACTUALIZAR PRECIOS DE PRODUCTOS**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Selecciona el producto cuyo precio deseas modificar:
    """
    
    keyboard = []
    for producto in productos:
        id_prod, categoria, nombre, descripcion, precio = producto
        keyboard.append([
            InlineKeyboardButton(
                f"{nombre} - {precio_formateado(precio)} CUP",
                callback_data=f"admin_editar_precio_{id_prod}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 PANEL ADMIN", callback_data="admin_panel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(mensaje, reply_markup=reply_markup, parse_mode='Markdown')

async def admin_editar_precio(update: Update, context: CallbackContext) -> None:
    """Interfaz para editar precio específico"""
    query = update.callback_query
    await query.answer()
    
    producto_id = int(query.data.split('_')[3])
    producto = get_producto_por_id(producto_id)
    
    if not producto:
        await query.edit_message_text("❌ Producto no encontrado.")
        return
    
    id_prod, nombre, descripcion, precio = producto
    
    context.user_data['editando_precio'] = producto_id
    
    mensaje = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✏️ **EDITANDO PRECIO**

**Producto:** {nombre}
{descripcion if descripcion else ''}
**Precio actual:** {precio_formateado(precio)} CUP

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Por favor, escribe el **nuevo precio** (solo números, sin CUP):

**Ejemplo:** Para 15 CUP, escribe: `15`
    """
    
    keyboard = [[InlineKeyboardButton("🔙 CANCELAR", callback_data="admin_actualizar_precios")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(mensaje, reply_markup=reply_markup, parse_mode='Markdown')

async def recibir_nuevo_precio_admin(update: Update, context: CallbackContext) -> None:
    """Recibe y procesa nuevo precio de producto"""
    if 'editando_precio' not in context.user_data:
        return
    
    producto_id = context.user_data['editando_precio']
    user = update.effective_user
    
    if not es_administrador(user):
        await update.message.reply_text("❌ No tienes permisos para realizar esta acción.")
        return
    
    try:
        nuevo_precio = float(update.message.text.strip())
        
        if nuevo_precio <= 0:
            await update.message.reply_text("❌ El precio debe ser mayor que 0.")
            return
        
        # Actualizar precio en base de datos
        actualizar_precio_producto(producto_id, nuevo_precio)
        
        producto = get_producto_por_id(producto_id)
        
        # Limpiar datos temporales
        del context.user_data['editando_precio']
        
        await update.message.reply_text(
            f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ **PRECIO ACTUALIZADO CORRECTAMENTE**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**Producto:** {producto[1]}
**Nuevo precio:** {precio_formateado(nuevo_precio)} CUP

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

El cambio se aplicará inmediatamente en los menús.
            """,
            parse_mode='Markdown'
        )
        
    except ValueError:
        await update.message.reply_text("❌ Por favor, escribe solo números. Ejemplo: 15")

async def admin_estadisticas(update: Update, context: CallbackContext) -> None:
    """Muestra estadísticas detalladas"""
    query = update.callback_query
    await query.answer()
    
    stats = get_estadisticas()
    
    mensaje = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 **ESTADÍSTICAS DETALLADAS - RECARGAS RÁPIDAS**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📅 **Período:** Desde el inicio del sistema
🕒 **Última actualización:** {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📈 **RESUMEN GENERAL:**
• Productos activos: {stats['total_productos']}
• Total de solicitudes: {stats['total_pedidos']}
• Solicitudes pendientes: {stats['solicitados']}
• Solicitudes confirmadas: {stats['confirmados']}
• Pagos en verificación: {stats['en_proceso']}
• Planes activados: {stats['completados']}
• Cancelaciones: {stats['total_pedidos'] - stats['solicitados'] - stats['confirmados'] - stats['en_proceso'] - stats['completados']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 **DISTRIBUCIÓN POR ETAPA:**
📨 Pendientes: {stats['solicitados']}
✅ Confirmadas: {stats['confirmados']}
📸 Por verificar: {stats['en_proceso']}
🎉 Completadas: {stats['completados']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💰 **INGRESOS:**
• Promedio por plan: {stats['total_ventas']/stats['completados']:.0f if stats['completados'] > 0 else 0} CUP
• Total acumulado: {stats['total_ventas']:.0f} CUP

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔧 **ESTADO DEL SISTEMA:**
• Servicio: {'🟢 ACTIVO' if get_service_status() == 'yes' else '🔴 PAUSADO'}
• Base de datos: 🟢 OPERATIVA
    """
    
    keyboard = [
        [InlineKeyboardButton("📋 VER SOLICITUDES", callback_data="admin_solicitudes_pendientes")],
        [InlineKeyboardButton("🔙 PANEL ADMIN", callback_data="admin_panel")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(mensaje, reply_markup=reply_markup, parse_mode='Markdown')

async def admin_control_servicio(update: Update, context: CallbackContext) -> None:
    """Controla el estado del servicio desde botones"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "admin_pausar_servicio":
        set_service_status('no')
        mensaje = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⏸️ **Servicio PAUSADO**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Los usuarios no podrán realizar nuevas solicitudes.
        """
    elif data == "admin_activar_servicio":
        set_service_status('yes')
        mensaje = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

▶️ **Servicio ACTIVADO**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Los usuarios ya pueden realizar solicitudes.
        """
    else:
        mensaje = "❌ Acción no reconocida."
    
    keyboard = [[InlineKeyboardButton("🔙 PANEL ADMIN", callback_data="admin_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(mensaje, reply_markup=reply_markup, parse_mode='Markdown')

# ==================== MANEJADORES DE CALLBACKS ====================
async def button_handler_cliente(update: Update, context: CallbackContext) -> None:
    """Maneja todos los callbacks de botones del bot cliente"""
    query = update.callback_query
    data = query.data
    
    try:
        # Navegación principal
        if data in ["cat_datos", "cat_voz", "cat_sms"]:
            await mostrar_categoria(update, context, data)
        
        elif data == "ver_todos":
            await ver_todos_planes(update, context)
        
        elif data == "ayuda":
            await ayuda(update, context)
        
        elif data == "mis_pedidos":
            await ver_mis_pedidos(update, context)
        
        elif data == "volver_inicio":
            await start(update, context)
        
        elif data == "reintentar_start":
            await start(update, context)
        
        elif data.startswith("seleccionar_"):
            await seleccionar_producto(update, context)
        
        elif data == "solicitar_plan":
            await solicitar_plan(update, context)
        
        elif data == "cancelar_solicitud":
            context.user_data.clear()
            await query.edit_message_text(
                """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

❌ **SOLICITUD CANCELADA**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Si cambias de opinión, puedes volver a comenzar desde /start
                """,
                parse_mode='Markdown'
            )
        
        else:
            await query.answer("⚠️ Acción no reconocida", show_alert=True)
    
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            logger.error(f"Error en button_handler_cliente: {e}")
            await query.answer("❌ Ocurrió un error. Por favor, intenta nuevamente.", show_alert=True)
    except Exception as e:
        logger.error(f"Error en button_handler_cliente: {e}")
        await query.answer("❌ Ocurrió un error. Por favor, intenta nuevamente.", show_alert=True)

async def button_handler_admin(update: Update, context: CallbackContext) -> None:
    """Maneja todos los callbacks de botones del bot admin"""
    query = update.callback_query
    data = query.data
    
    try:
        # Panel de administración
        if data == "admin_panel":
            await admin(update, context)
        
        elif data in ["admin_solicitudes_pendientes", "admin_solicitudes_confirmadas", "admin_pagos_verificar"]:
            estado = data.split('_')[2] if data != "admin_pagos_verificar" else "en_proceso"
            await admin_solicitudes(update, context, estado)
        
        elif data.startswith("admin_confirmar_") or data.startswith("admin_rechazar_"):
            await admin_procesar_solicitud(update, context)
        
        elif data.startswith("admin_completar_") or data.startswith("admin_cancelar_"):
            await admin_completar_pedido(update, context)
        
        elif data == "admin_actualizar_precios":
            await admin_actualizar_precios(update, context)
        
        elif data.startswith("admin_editar_precio_"):
            await admin_editar_precio(update, context)
        
        elif data == "admin_estadisticas":
            await admin_estadisticas(update, context)
        
        elif data in ["admin_pausar_servicio", "admin_activar_servicio"]:
            await admin_control_servicio(update, context)
        
        else:
            await query.answer("⚠️ Acción no reconocida", show_alert=True)
    
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            logger.error(f"Error en button_handler_admin: {e}")
            await query.answer("❌ Ocurrió un error. Por favor, intenta nuevamente.", show_alert=True)
    except Exception as e:
        logger.error(f"Error en button_handler_admin: {e}")
        await query.answer("❌ Ocurrió un error. Por favor, intenta nuevamente.", show_alert=True)

# ==================== INICIALIZACIÓN DE BOTS (VERSIÓN CORREGIDA) ====================
def run_bots():
    """Función principal corregida para ejecutar ambos bots en Render"""
    import asyncio
    
    # Inicializar base de datos
    init_database()
    
    async def main_async():
        """Función asíncrona principal"""
        print("""
    ============================================
    🚀 SISTEMA DE RECARGAS RÁPIDAS - INICIANDO
    ============================================
        """)
        
        # Configurar aplicación cliente
        cliente_app_local = Application.builder().token(TOKEN_CLIENTE).build()
        
        # Configurar handlers del cliente
        cliente_app_local.add_handler(CommandHandler("start", start))
        cliente_app_local.add_handler(CallbackQueryHandler(button_handler_cliente))
        cliente_app_local.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_numero))
        cliente_app_local.add_handler(MessageHandler(filters.PHOTO, recibir_captura_pago))
        
        global cliente_app
        cliente_app = cliente_app_local
        
        print("🤖 Bot CLIENTE configurado")
        
        # Configurar aplicación admin
        admin_app_local = Application.builder().token(TOKEN_ADMIN).build()
        
        # Configurar handlers del admin
        admin_app_local.add_handler(CommandHandler("admin", admin))
        admin_app_local.add_handler(CommandHandler("fondosno", fondos_no))
        admin_app_local.add_handler(CommandHandler("fondosyes", fondos_yes))
        admin_app_local.add_handler(CallbackQueryHandler(button_handler_admin))
        admin_app_local.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_nuevo_precio_admin))
        
        # Configurar JobQueue (solo si está disponible, con manejo de errores)
        try:
            if hasattr(admin_app_local, 'job_queue') and admin_app_local.job_queue is not None:
                admin_app_local.job_queue.run_repeating(monitorear_nuevas_solicitudes, interval=30, first=10)
                print("✅ JobQueue configurado para admin")
        except Exception as e:
            print(f"⚠️ JobQueue no disponible: {e}")
            print("⚠️ Las notificaciones serán inmediatas en lugar de periódicas")
        
        global admin_app
        admin_app = admin_app_local
        
        print("🛠️ Bot ADMIN configurado")
        
        # Mostrar información del sistema
        stats = get_estadisticas()
        print(f"""
    ============================================
    📊 INFORMACIÓN DEL SISTEMA
    ============================================
    🤖 Bot Cliente: {BOT_USERNAME}
    🛠️ Bot Admin: {BOT_USERNAME_ADMIN}
    👑 Administrador: {ADMIN_USERNAME}
    💳 Número para saldo: {NUMERO_RECIBIR_SALDO}
    📊 Productos cargados: {stats['total_productos']}
    📨 Pedidos totales: {stats['total_pedidos']}
    🔧 Estado del servicio: {'ACTIVO' if get_service_status() == 'yes' else 'PAUSADO'}
    ============================================
        """)
        
        # Configurar parámetros para polling en Render
        polling_kwargs = {
            'allowed_updates': ['message', 'callback_query'],
            'drop_pending_updates': True,
            'close_loop': False  # Importante para Render
        }
        
        print("🔄 Iniciando bots con asyncio.gather...")
        
        # Ejecutar ambos bots simultáneamente
        await asyncio.gather(
            cliente_app_local.run_polling(**polling_kwargs),
            admin_app_local.run_polling(**polling_kwargs)
        )
    
    # Ejecutar en el event loop principal
    asyncio.run(main_async())

# ==================== INICIALIZACIÓN ALTERNATIVA (WEBHOOK) ====================
def run_bots_webhook():
    """Versión alternativa usando webhooks (recomendado para producción)"""
    from telegram.ext import ApplicationBuilder
    import os
    
    # Inicializar base de datos
    init_database()
    
    # Obtener variables de entorno de Render
    RENDER_EXTERNAL_URL = os.environ.get('RENDER_EXTERNAL_URL', '')
    PORT = int(os.environ.get('PORT', 10000))
    
    async def setup_webhooks():
        """Configurar webhooks para ambos bots"""
        
        # Bot cliente
        cliente_app_web = ApplicationBuilder().token(TOKEN_CLIENTE).build()
        cliente_app_web.add_handler(CommandHandler("start", start))
        cliente_app_web.add_handler(CallbackQueryHandler(button_handler_cliente))
        cliente_app_web.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_numero))
        cliente_app_web.add_handler(MessageHandler(filters.PHOTO, recibir_captura_pago))
        
        global cliente_app
        cliente_app = cliente_app_web
        
        # Bot admin
        admin_app_web = ApplicationBuilder().token(TOKEN_ADMIN).build()
        admin_app_web.add_handler(CommandHandler("admin", admin))
        admin_app_web.add_handler(CommandHandler("fondosno", fondos_no))
        admin_app_web.add_handler(CommandHandler("fondosyes", fondos_yes))
        admin_app_web.add_handler(CallbackQueryHandler(button_handler_admin))
        admin_app_web.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_nuevo_precio_admin))
        
        global admin_app
        admin_app = admin_app_web
        
        if RENDER_EXTERNAL_URL:
            # Configurar webhooks
            await cliente_app_web.initialize()
            await admin_app_web.initialize()
            
            # Configurar webhooks
            await cliente_app_web.bot.setWebhook(f"{RENDER_EXTERNAL_URL}/webhook/{TOKEN_CLIENTE}")
            await admin_app_web.bot.setWebhook(f"{RENDER_EXTERNAL_URL}/webhook/{TOKEN_ADMIN}")
            
            print(f"✅ Webhooks configurados:")
            print(f"   Cliente: {RENDER_EXTERNAL_URL}/webhook/{TOKEN_CLIENTE}")
            print(f"   Admin: {RENDER_EXTERNAL_URL}/webhook/{TOKEN_ADMIN}")
            
            # Mantener la aplicación corriendo
            print("✅ Bots configurados en modo webhook")
            print("⚠️ Necesitas configurar el servidor web para manejar las rutas /webhook/")
            
        else:
            print("⚠️ No se encontró RENDER_EXTERNAL_URL, usando polling")
            # Usar polling si no hay URL
            await asyncio.gather(
                cliente_app_web.run_polling(allowed_updates=['message', 'callback_query'], drop_pending_updates=True),
                admin_app_web.run_polling(allowed_updates=['message', 'callback_query'], drop_pending_updates=True)
            )
    
    # Ejecutar
    asyncio.run(setup_webhooks())

# ==================== EJECUCIÓN PRINCIPAL ====================
if __name__ == '__main__':
    # Usar la versión corregida con asyncio (recomendado para Render)
    try:
        run_bots()
    except KeyboardInterrupt:
        print("\n🛑 Sistema detenido por el usuario")
    except Exception as e:
        print(f"\n❌ Error crítico: {e}")
        print("⚠️ Reiniciando en 5 segundos...")
        time.sleep(5)
        # Intentar reiniciar
        run_bots()