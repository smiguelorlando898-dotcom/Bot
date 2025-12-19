# bot_cliente.py - Bot exclusivo para clientes (@RecargasRBot)
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, CallbackContext
from telegram.error import BadRequest
from database import *

# ⚠️ CONFIGURACIÓN IMPORTANTE: REEMPLAZAR CON TU TOKEN
TOKEN_CLIENTE = "TU_TOKEN_DEL_BOT_CLIENTE_AQUÍ"  # Token de @RecargasRBot
BOT_USERNAME = "@RecargasRBot"

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename='bot_cliente.log'
)
logger = logging.getLogger(__name__)

# ==================== FUNCIONES AUXILIARES ====================
def precio_formateado(precio):
    """Formatea el precio"""
    return f"{precio:.0f}" if precio.is_integer() else f"{precio:.1f}"

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

# ==================== COMANDOS PRINCIPALES ====================
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
    
    # NOTA: La notificación al administrador se manejará desde el bot admin
    # Aquí solo guardamos el pedido en la base de datos
    
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
    
    # NOTA: La notificación al administrador se manejará desde el bot admin
    # El bot admin monitorea la base de datos para nuevas capturas
    
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

# ==================== MANEJADOR DE CALLBACKS ====================
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

# ==================== CONFIGURACIÓN DEL BOT ====================
def main_cliente():
    """Función principal para iniciar el bot cliente"""
    # Inicializar base de datos
    init_database()
    
    # Crear la aplicación del bot cliente
    application = Application.builder().token(TOKEN_CLIENTE).build()
    
    # Comandos principales
    application.add_handler(CommandHandler("start", start))
    
    # Manejador de botones (callbacks)
    application.add_handler(CallbackQueryHandler(button_handler_cliente))
    
    # Manejadores de mensajes
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_numero))
    application.add_handler(MessageHandler(filters.PHOTO, recibir_captura_pago))
    
    # Iniciar el bot
    logger.info("✅ Bot CLIENTE RECARGAS RÁPIDAS iniciado correctamente")
    print(f"""
    ============================================
    🤖 BOT CLIENTE INICIADO
    ============================================
    🏪 Nombre del bot: {BOT_USERNAME}
    👑 Administrador: {ADMIN_USERNAME}
    💳 Número para saldo: {NUMERO_RECIBIR_SALDO}
    📊 Productos cargados: {len(get_all_productos())}
    🔧 Estado del servicio: {get_service_status()}
    ============================================
    """)
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main_cliente()