# bot_admin.py - Bot exclusivo para administrador (@AdminRecargasRBot)
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, CallbackContext
from telegram.error import BadRequest
from database import *

# ⚠️ CONFIGURACIÓN IMPORTANTE: REEMPLAZAR CON TU TOKEN
TOKEN_ADMIN = "TU_TOKEN_DEL_BOT_ADMIN_AQUÍ"  # Token de @AdminRecargasRBot
BOT_USERNAME_ADMIN = "@AdminRecargasRBot"

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename='bot_admin.log'
)
logger = logging.getLogger(__name__)

# ==================== FUNCIONES AUXILIARES ====================
def precio_formateado(precio):
    """Formatea el precio"""
    return f"{precio:.0f}" if precio.is_integer() else f"{precio:.1f}"

def es_administrador(usuario):
    """Verifica si el usuario es administrador"""
    return usuario.username and usuario.username.lower() == ADMIN_USERNAME.replace('@', '').lower()

# ==================== FUNCIONES DE NOTIFICACIÓN ====================
async def notificar_administrador_nueva_solicitud(context: CallbackContext, pedido_id: int, user, producto, numero_destino: str):
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
        await context.bot.send_message(
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
        await context.bot.send_message(
            chat_id=user_id,
            text=mensaje_pago,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error al enviar instrucciones de pago: {e}")

async def notificar_administrador_captura(context: CallbackContext, pedido, file_id: str, user):
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
        await context.bot.send_photo(
            chat_id=ADMIN_USERNAME.replace('@', ''),
            photo=file_id,
            caption=mensaje_admin,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error al notificar al administrador: {e}")

# ==================== SISTEMA DE MONITOREO ====================
async def monitorear_nuevas_solicitudes(context: CallbackContext):
    """Monitorea nuevas solicitudes en la base de datos"""
    try:
        # Obtener solicitudes pendientes de notificación
        pedidos_solicitados = get_pedidos_por_estado('solicitado')
        
        for pedido in pedidos_solicitados:
            pedido_id, user_id, user_name, numero_destino, producto_id, precio, estado, captura_file_id, fecha, procesado_por, producto_nombre = pedido
            
            # Verificar si ya fue notificado (procesado_por es NULL)
            if not procesado_por:
                producto = get_producto_por_id(producto_id)
                if producto:
                    # Crear objeto usuario simulado para la notificación
                    class UsuarioSimulado:
                        def __init__(self, user_id, user_name):
                            self.id = user_id
                            self.full_name = user_name
                            self.username = None
                    
                    usuario = UsuarioSimulado(user_id, user_name)
                    producto_dict = {
                        'nombre': producto_nombre,
                        'precio': precio
                    }
                    
                    await notificar_administrador_nueva_solicitud(
                        context, pedido_id, usuario, producto_dict, numero_destino
                    )
                    
                    # Marcar como notificado
                    actualizar_etapa_pedido(pedido_id, 'notificado')
        
        # Monitorear capturas nuevas
        pedidos_en_proceso = get_pedidos_por_estado('en_proceso')
        
        for pedido in pedidos_en_proceso:
            pedido_id, user_id, user_name, numero_destino, producto_id, precio, estado, captura_file_id, fecha, procesado_por, producto_nombre = pedido
            
            if captura_file_id and not procesado_por:
                # Crear objeto usuario simulado
                class UsuarioSimulado:
                    def __init__(self, user_id, user_name):
                        self.id = user_id
                        self.full_name = user_name
                        self.username = None
                
                usuario = UsuarioSimulado(user_id, user_name)
                
                await notificar_administrador_captura(
                    context, pedido, captura_file_id, usuario
                )
                
                # Marcar como procesado
                actualizar_etapa_pedido(pedido_id, 'captura_notificada')
    
    except Exception as e:
        logger.error(f"Error en monitorear_nuevas_solicitudes: {e}")

# ==================== COMANDOS DE ADMINISTRADOR ====================
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
                await context.bot.send_message(
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
            await context.bot.send_message(
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
                await context.bot.send_message(
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

# ==================== COMANDOS DE CONTROL ====================
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
• Todas las funciones están disponibles

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

# ==================== MANEJADOR DE CALLBACKS ====================
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

# ==================== CONFIGURACIÓN DEL BOT ====================
def main_admin():
    """Función principal para iniciar el bot admin"""
    # Inicializar base de datos
    init_database()
    
    # Crear la aplicación del bot admin
    application = Application.builder().token(TOKEN_ADMIN).build()
    
    # Comandos principales
    application.add_handler(CommandHandler("admin", admin))
    application.add_handler(CommandHandler("fondosno", fondos_no))
    application.add_handler(CommandHandler("fondosyes", fondos_yes))
    
    # Manejador de botones (callbacks)
    application.add_handler(CallbackQueryHandler(button_handler_admin))
    
    # Manejador para precios
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_nuevo_precio_admin))
    
    # Agregar tarea de monitoreo periódico
    job_queue = application.job_queue
    job_queue.run_repeating(monitorear_nuevas_solicitudes, interval=30, first=10)
    
    # Iniciar el bot
    logger.info("✅ Bot ADMIN RECARGAS RÁPIDAS iniciado correctamente")
    print(f"""
    ============================================
    🛠️ BOT ADMINISTRADOR INICIADO
    ============================================
    👑 Nombre del bot: {BOT_USERNAME_ADMIN}
    👨‍💼 Administrador: {ADMIN_USERNAME}
    💳 Número para saldo: {NUMERO_RECIBIR_SALDO}
    📊 Productos cargados: {len(get_all_productos())}
    🔧 Estado del servicio: {get_service_status()}
    📡 Monitoreo activado: CADA 30 SEGUNDOS
    ============================================
    """)
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main_admin()