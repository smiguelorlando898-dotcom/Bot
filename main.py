import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from datetime import datetime
import sqlite3
import os

# Configuración
TOKEN = "8530361444:AAFZ-yZIFzDC0CVUvX-W14kTZGVKFITGBCE"
ADMIN_ID = 8282703640  # ⚠️ CAMBIA ESTO POR TU ID REAL DE TELEGRAM
PAYMENT_NUMBER = "50321300"

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Inicializar base de datos
def init_db():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    # Tabla para usuarios
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            join_date TIMESTAMP
        )
    ''')
    
    # Tabla para solicitudes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            plan_type TEXT,
            plan_name TEXT,
            price REAL,
            phone_number TEXT,
            status TEXT DEFAULT 'pending',
            request_date TIMESTAMP,
            admin_action_date TIMESTAMP,
            screenshot_path TEXT,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    # Insertar planes predefinidos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_type TEXT,
            plan_name TEXT,
            price REAL
        )
    ''')
    
    # Verificar si ya existen planes
    cursor.execute("SELECT COUNT(*) FROM plans")
    if cursor.fetchone()[0] == 0:
        # Planes de datos
        data_plans = [
            ('datos', 'Plan toDus (600 MB)', 10.00)
        ]
        
        # Planes de voz
        voice_plans = [
            ('voz', '5 Minutos', 15.00),
            ('voz', '10 Minutos', 30.00),
            ('voz', '15 Minutos', 45.00),
            ('voz', '25 Minutos', 70.00),
            ('voz', '40 Minutos', 110.00)
        ]
        
        # Planes de SMS
        sms_plans = [
            ('sms', '20 SMS', 6.00),
            ('sms', '50 SMS', 12.00),
            ('sms', '90 SMS', 20.00),
            ('sms', '120 SMS', 25.00)
        ]
        
        all_plans = data_plans + voice_plans + sms_plans
        cursor.executemany("INSERT INTO plans (plan_type, plan_name, price) VALUES (?, ?, ?)", all_plans)
    
    conn.commit()
    conn.close()

# Registrar usuario
def register_user(user_id, username, first_name, last_name):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, join_date)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, username, first_name, last_name, datetime.now()))
    
    conn.commit()
    conn.close()

# Guardar solicitud
def save_request(user_id, plan_type, plan_name, price, phone_number):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO requests (user_id, plan_type, plan_name, price, phone_number, request_date, status)
        VALUES (?, ?, ?, ?, ?, ?, 'pending')
    ''', (user_id, plan_type, plan_name, price, phone_number, datetime.now()))
    
    request_id = cursor.lastrowid
    
    conn.commit()
    conn.close()
    return request_id

# Actualizar estado de solicitud
def update_request_status(request_id, status, screenshot_path=None):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    if screenshot_path:
        cursor.execute('''
            UPDATE requests 
            SET status = ?, admin_action_date = ?, screenshot_path = ?
            WHERE id = ?
        ''', (status, datetime.now(), screenshot_path, request_id))
    else:
        cursor.execute('''
            UPDATE requests 
            SET status = ?, admin_action_date = ?
            WHERE id = ?
        ''', (status, datetime.now(), request_id))
    
    conn.commit()
    
    # Obtener user_id para notificar
    cursor.execute("SELECT user_id FROM requests WHERE id = ?", (request_id,))
    result = cursor.fetchone()
    user_id = result[0] if result else None
    
    conn.close()
    return user_id

# Obtener solicitudes pendientes
def get_pending_requests():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT r.id, r.user_id, r.plan_type, r.plan_name, r.price, r.phone_number, 
               r.request_date, u.username, u.first_name
        FROM requests r
        LEFT JOIN users u ON r.user_id = u.user_id
        WHERE r.status = 'pending'
        ORDER BY r.request_date
    ''')
    
    requests = cursor.fetchall()
    conn.close()
    return requests

# Comandos
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    # Registrar usuario
    register_user(user_id, user.username, user.first_name, user.last_name)
    
    if user_id == ADMIN_ID:
        # Menú de administrador
        keyboard = [
            [InlineKeyboardButton("📋 Ver solicitudes pendientes", callback_data='admin_view_requests')],
            [InlineKeyboardButton("📊 Estadísticas", callback_data='admin_stats')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f'👑 ¡Bienvenido Administrador {user.first_name}!\n'
            'Selecciona una opción:',
            reply_markup=reply_markup
        )
    else:
        # Menú de usuario normal
        keyboard = [
            [InlineKeyboardButton("📋 Ver planes", callback_data='view_plans')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f'¡Hola {user.first_name}! 👋\n'
            'Bienvenido a RECARGAS RÁPIDAS. '
            'Convierte tu saldo móvil en planes de ETECSA al instante.\n\n'
            'Selecciona "Ver planes" para comenzar.',
            reply_markup=reply_markup
        )

# Manejar botones
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    
    if data == 'view_plans':
        # Mostrar tipos de planes
        keyboard = [
            [InlineKeyboardButton("📡 Planes de Datos", callback_data='plan_type_datos')],
            [InlineKeyboardButton("📞 Planes de Voz", callback_data='plan_type_voz')],
            [InlineKeyboardButton("💬 Planes de SMS", callback_data='plan_type_sms')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "Selecciona el tipo de plan que deseas:",
            reply_markup=reply_markup
        )
    
    elif data.startswith('plan_type_'):
        # Mostrar planes específicos del tipo seleccionado
        plan_type = data.replace('plan_type_', '')
        
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT id, plan_name, price FROM plans WHERE plan_type = ?", (plan_type,))
        plans = cursor.fetchall()
        conn.close()
        
        keyboard = []
        for plan_id, plan_name, price in plans:
            keyboard.append([InlineKeyboardButton(
                f"{plan_name} → {price:.2f} CUP", 
                callback_data=f'select_plan_{plan_id}'
            )])
        
        keyboard.append([InlineKeyboardButton("« Volver", callback_data='view_plans')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        type_names = {'datos': 'Datos', 'voz': 'Voz', 'sms': 'SMS'}
        await query.edit_message_text(
            f"📋 Planes de {type_names.get(plan_type, plan_type)} disponibles:\n"
            "Selecciona uno:",
            reply_markup=reply_markup
        )
    
    elif data.startswith('select_plan_'):
        # Seleccionar plan específico
        plan_id = int(data.replace('select_plan_', ''))
        
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT plan_type, plan_name, price FROM plans WHERE id = ?", (plan_id,))
        plan = cursor.fetchone()
        conn.close()
        
        if plan:
            plan_type, plan_name, price = plan
            
            # Guardar selección temporal en contexto
            context.user_data['selected_plan'] = {
                'type': plan_type,
                'name': plan_name,
                'price': price,
                'id': plan_id
            }
            
            await query.edit_message_text(
                f"✅ Has seleccionado:\n"
                f"📦 Plan: {plan_name}\n"
                f"💰 Precio: {price:.2f} CUP\n\n"
                f"Por favor, envía el número de teléfono al que deseas activar este plan.\n"
                f"Escríbelo en formato: 5XXXXXXXX"
            )
    
    elif data.startswith('confirm_request_'):
        # Confirmar solicitud
        request_id = int(data.replace('confirm_request_', ''))
        user_id = update_request_status(request_id, 'confirmed')
        
        # Notificar al usuario
        if user_id:
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="✅ ¡Tu solicitud ha sido PROCESADA!\n"
                         "Tu plan ha sido activado exitosamente.\n\n"
                         "¡Gracias por usar RECARGAS RÁPIDAS! 🎉"
                )
            except Exception as e:
                logger.error(f"Error notifying user: {e}")
        
        await query.edit_message_text(
            f"✅ Solicitud #{request_id} procesada exitosamente.\n"
            f"El usuario ha sido notificado."
        )
    
    elif data.startswith('cancel_request_'):
        # Cancelar solicitud
        request_id = int(data.replace('cancel_request_', ''))
        user_id = update_request_status(request_id, 'cancelled')
        
        # Notificar al usuario
        if user_id:
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="❌ Tu solicitud ha sido CANCELADA por el administrador.\n"
                         "Por favor, contacta con soporte si necesitas ayuda."
                )
            except Exception as e:
                logger.error(f"Error notifying user: {e}")
        
        await query.edit_message_text(
            f"❌ Solicitud #{request_id} cancelada.\n"
            f"El usuario ha sido notificado."
        )
    
    elif data == 'admin_view_requests':
        # Mostrar solicitudes pendientes al admin
        requests = get_pending_requests()
        
        if not requests:
            await query.edit_message_text("📭 No hay solicitudes pendientes.")
            return
        
        message_text = "📋 SOLICITUDES PENDIENTES:\n\n"
        for req in requests:
            req_id, user_id, plan_type, plan_name, price, phone, req_date, username, first_name = req
            message_text += (
                f"🆔 ID: {req_id}\n"
                f"👤 Usuario: {first_name} (@{username if username else 'Sin username'})\n"
                f"📞 Teléfono: {phone}\n"
                f"📦 Plan: {plan_name}\n"
                f"💰 Precio: {price:.2f} CUP\n"
                f"📅 Fecha: {req_date}\n"
                f"────────────────────\n"
            )
        
        await query.edit_message_text(message_text)
        
        # Botones para cada solicitud
        for req in requests:
            req_id = req[0]
            keyboard = [
                [
                    InlineKeyboardButton("✅ Aceptar", callback_data=f'admin_accept_{req_id}'),
                    InlineKeyboardButton("❌ Cancelar", callback_data=f'admin_cancel_{req_id}')
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"Solicitud #{req_id} - ¿Qué acción deseas tomar?",
                reply_markup=reply_markup
            )
    
    elif data.startswith('admin_accept_'):
        # Admin acepta solicitud
        request_id = int(data.replace('admin_accept_', ''))
        
        await query.edit_message_text(
            f"📋 Solicitud #{request_id} ACEPTADA.\n\n"
            f"⚠️ Instrucciones para el usuario:\n"
            f"1. Realiza transferencia de saldo móvil al número: {PAYMENT_NUMBER}\n"
            f"2. Monto exacto: Consulta en la base de datos\n"
            f"3. Envía captura de pantalla de la transferencia\n"
            f"4. Espera confirmación de activación"
        )
        
        # Actualizar estado a "waiting_payment"
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE requests SET status = 'waiting_payment' WHERE id = ?", (request_id,))
        conn.commit()
        
        # Obtener user_id para notificar
        cursor.execute("SELECT user_id, plan_name, price FROM requests WHERE id = ?", (request_id,))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            user_id, plan_name, price = result
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"✅ Tu solicitud ha sido ACEPTADA.\n\n"
                         f"📦 Plan: {plan_name}\n"
                         f"💰 Precio: {price:.2f} CUP\n\n"
                         f"📲 **INSTRUCCIONES DE PAGO:**\n"
                         f"1. Realiza transferencia de saldo móvil al número: {PAYMENT_NUMBER}\n"
                         f"2. Monto exacto: {price:.2f} CUP\n"
                         f"3. Envía la captura de pantalla de la transferencia a este chat\n"
                         f"4. Tu solicitud será procesada una vez verifiquemos el pago\n\n"
                         f"⚠️ Asegúrate de que la captura sea CLARA y LEGIBLE."
                )
            except Exception as e:
                logger.error(f"Error notifying user: {e}")
    
    elif data.startswith('admin_cancel_'):
        # Admin cancela solicitud
        request_id = int(data.replace('admin_cancel_', ''))
        user_id = update_request_status(request_id, 'cancelled')
        
        # Notificar al usuario
        if user_id:
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="❌ Tu solicitud ha sido CANCELADA por el administrador.\n"
                         "Por favor, contacta con soporte si necesitas ayuda."
                )
            except Exception as e:
                logger.error(f"Error notifying user: {e}")
        
        await query.edit_message_text(f"❌ Solicitud #{request_id} cancelada.")

# Manejar mensajes de texto
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message_text = update.message.text
    
    # Si es admin y envía un comando especial
    if user_id == ADMIN_ID and message_text.startswith('/'):
        # Aquí puedes agregar comandos especiales para admin
        pass
    
    # Si el usuario está en proceso de enviar número de teléfono
    elif 'selected_plan' in context.user_data:
        # Validar número de teléfono (simple validación)
        if message_text.isdigit() and len(message_text) == 8:
            phone_number = message_text
            
            # Obtener plan seleccionado
            plan = context.user_data['selected_plan']
            
            # Guardar solicitud en base de datos
            request_id = save_request(
                user_id, 
                plan['type'], 
                plan['name'], 
                plan['price'], 
                phone_number
            )
            
            # Notificar al usuario
            await update.message.reply_text(
                f"✅ Solicitud enviada exitosamente.\n"
                f"🆔 ID de solicitud: #{request_id}\n"
                f"📞 Teléfono: {phone_number}\n"
                f"📦 Plan: {plan['name']}\n"
                f"💰 Precio: {plan['price']:.2f} CUP\n\n"
                f"⏳ Tu solicitud está siendo procesada.\n"
                f"Te notificaremos cuando sea revisada por el administrador."
            )
            
            # Notificar al administrador
            user = update.effective_user
            keyboard = [
                [
                    InlineKeyboardButton("✅ Aceptar", callback_data=f'admin_accept_{request_id}'),
                    InlineKeyboardButton("❌ Cancelar", callback_data=f'admin_cancel_{request_id}')
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"📢 NUEVA SOLICITUD #{request_id}\n\n"
                     f"👤 Usuario: {user.first_name} (@{user.username if user.username else 'Sin username'})\n"
                     f"🆔 User ID: {user_id}\n"
                     f"📞 Teléfono: {phone_number}\n"
                     f"📦 Plan: {plan['name']}\n"
                     f"💰 Precio: {plan['price']:.2f} CUP\n"
                     f"📅 Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                     f"Selecciona una acción:",
                reply_markup=reply_markup
            )
            
            # Limpiar datos temporales
            del context.user_data['selected_plan']
        
        else:
            await update.message.reply_text(
                "❌ Número de teléfono inválido.\n"
                "Por favor, envía un número válido de 8 dígitos.\n"
                "Ejemplo: 51234567"
            )
    
    else:
        # Mensaje normal
        await update.message.reply_text(
            "Por favor, usa los botones del menú para navegar.\n"
            "Escribe /start para ver el menú principal."
        )

# Manejar fotos (capturas de pantalla)
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Obtener la foto de mayor calidad
    photo = update.message.photo[-1]
    file_id = photo.file_id
    
    # Verificar si el usuario tiene solicitudes en espera de pago
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, plan_name, price FROM requests 
        WHERE user_id = ? AND status = 'waiting_payment'
        ORDER BY request_date DESC LIMIT 1
    ''', (user_id,))
    
    result = cursor.fetchone()
    
    if result:
        request_id, plan_name, price = result
        
        # Descargar la foto (en un entorno real deberías guardarla)
        file = await context.bot.get_file(file_id)
        
        # Crear directorio para capturas si no existe
        os.makedirs('screenshots', exist_ok=True)
        
        # Guardar la captura (en producción, usa un servicio de almacenamiento)
        screenshot_path = f"screenshots/{request_id}_{user_id}.jpg"
        await file.download_to_drive(screenshot_path)
        
        # Actualizar solicitud con la captura
        update_request_status(request_id, 'payment_received', screenshot_path)
        
        # Notificar al usuario
        await update.message.reply_text(
            "✅ Captura de pantalla recibida.\n\n"
            "📋 Tu pago está siendo verificado.\n"
            "Te notificaremos cuando tu plan sea activado.\n\n"
            "⏳ Por favor, espera la confirmación."
        )
        
        # Notificar al administrador
        user = update.effective_user
        
        keyboard = [
            [InlineKeyboardButton("✅ Marcar como procesado", callback_data=f'confirm_request_{request_id}')],
            [InlineKeyboardButton("❌ Reportar problema", callback_data=f'cancel_request_{request_id}')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"💰 PAGO RECIBIDO - Solicitud #{request_id}\n\n"
                 f"👤 Usuario: {user.first_name} (@{user.username if user.username else 'Sin username'})\n"
                 f"📦 Plan: {plan_name}\n"
                 f"💰 Monto: {price:.2f} CUP\n"
                 f"📅 Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                 f"Se ha recibido la captura de pago.\n"
                 f"¿Qué acción deseas tomar?",
            reply_markup=reply_markup
        )
        
        # También enviar la foto al admin
        await context.bot.send_photo(
            chat_id=ADMIN_ID,
            photo=file_id,
            caption=f"Captura de pago - Solicitud #{request_id}"
        )
        
    else:
        await update.message.reply_text(
            "📌 No tienes solicitudes pendientes de pago.\n"
            "Primero selecciona un plan y espera la aceptación del administrador."
        )
    
    conn.close()

# Función principal
def main():
    # Inicializar base de datos
    init_db()
    
    # Crear aplicación
    application = Application.builder().token(TOKEN).build()
    
    # Comandos
    application.add_handler(CommandHandler("start", start))
    
    # Botones
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Mensajes
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Fotos
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    # Iniciar bot
    print("🤖 Bot iniciado...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()