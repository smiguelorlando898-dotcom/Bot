import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from datetime import datetime, timedelta
import sqlite3
import os
import hashlib
import traceback

# ==================== CONFIGURACIÓN ====================
TOKEN = "8530361444:AAFZ-yZIFzDC0CVUvX-W14kTZGVKFITGBCE"
ADMIN_IDS = [8282703640]  # ⚠️ CAMBIA ESTO POR TU ID REAL DE TELEGRAM
PAYMENT_NUMBER = "50321300"

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== BASE DE DATOS ====================
def init_db():
    """Inicializa todas las tablas de la base de datos"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    # Tabla de usuarios (MEJORADA)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            join_date TIMESTAMP,
            credit REAL DEFAULT 0.0,
            referral_code TEXT UNIQUE,
            referred_by INTEGER,
            total_referrals INTEGER DEFAULT 0,
            total_spent REAL DEFAULT 0.0,
            last_active TIMESTAMP,
            FOREIGN KEY (referred_by) REFERENCES users (user_id)
        )
    ''')
    
    # Tabla de referidos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER,
            referred_id INTEGER,
            bonus_applied BOOLEAN DEFAULT FALSE,
            referral_date TIMESTAMP,
            FOREIGN KEY (referrer_id) REFERENCES users (user_id),
            FOREIGN KEY (referred_id) REFERENCES users (user_id)
        )
    ''')
    
    # Tabla de solicitudes (MEJORADA)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            plan_type TEXT,
            plan_name TEXT,
            price REAL,
            credit_used REAL DEFAULT 0.0,
            phone_number TEXT,
            status TEXT DEFAULT 'pending',
            request_date TIMESTAMP,
            admin_action_date TIMESTAMP,
            screenshot_path TEXT,
            payment_method TEXT DEFAULT 'transfer',
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    # Tabla de planes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_type TEXT,
            plan_name TEXT,
            price REAL,
            active BOOLEAN DEFAULT TRUE
        )
    ''')
    
    # Insertar planes si no existen
    cursor.execute("SELECT COUNT(*) FROM plans")
    if cursor.fetchone()[0] == 0:
        plans_data = [
            ('datos', 'Plan toDus (600 MB)', 10.00),
            ('voz', '5 Minutos', 15.00),
            ('voz', '10 Minutos', 30.00),
            ('voz', '15 Minutos', 45.00),
            ('voz', '25 Minutos', 70.00),
            ('voz', '40 Minutos', 110.00),
            ('sms', '20 SMS', 6.00),
            ('sms', '50 SMS', 12.00),
            ('sms', '90 SMS', 20.00),
            ('sms', '120 SMS', 25.00)
        ]
        cursor.executemany("INSERT INTO plans (plan_type, plan_name, price) VALUES (?, ?, ?)", plans_data)
    
    conn.commit()
    conn.close()
    print("✅ Base de datos inicializada")

def register_user(user_id, username, first_name, last_name, referred_by=None):
    """Registra un nuevo usuario con sistema de referidos"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    # Verificar si ya existe
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if cursor.fetchone():
        conn.close()
        return False
    
    # Generar código de referencia único
    referral_code = f"REF{hashlib.md5(f'{user_id}{datetime.now()}'.encode()).hexdigest()[:8].upper()}"
    
    # Insertar usuario
    cursor.execute('''
        INSERT INTO users (user_id, username, first_name, last_name, join_date, 
                          referral_code, referred_by, last_active)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, username, first_name, last_name, datetime.now(), 
          referral_code, referred_by, datetime.now()))
    
    # Si vino por referencia, registrar
    if referred_by:
        cursor.execute('''
            INSERT INTO referrals (referrer_id, referred_id, referral_date)
            VALUES (?, ?, ?)
        ''', (referred_by, user_id, datetime.now()))
        
        # Actualizar contador de referidos
        cursor.execute('''
            UPDATE users 
            SET total_referrals = total_referrals + 1 
            WHERE user_id = ?
        ''', (referred_by,))
    
    conn.commit()
    conn.close()
    return True

def update_user_activity(user_id):
    """Actualiza la última actividad del usuario"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET last_active = ? WHERE user_id = ?', (datetime.now(), user_id))
    conn.commit()
    conn.close()

def get_user_credit(user_id):
    """Obtiene el crédito disponible del usuario"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT credit FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0.0

def add_user_credit(user_id, amount):
    """Añade crédito a un usuario"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET credit = credit + ? WHERE user_id = ?', (amount, user_id))
    conn.commit()
    conn.close()

def apply_referral_bonus(referred_user_id):
    """Aplica 1 CUP de bono al referidor cuando el referido hace su primer pedido"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    # Obtener quién refirió a este usuario
    cursor.execute("SELECT referred_by FROM users WHERE user_id = ?", (referred_user_id,))
    result = cursor.fetchone()
    
    if result and result[0]:
        referrer_id = result[0]
        
        # Verificar si ya se aplicó el bono para esta referencia
        cursor.execute('''
            SELECT bonus_applied FROM referrals 
            WHERE referred_id = ? AND referrer_id = ?
        ''', (referred_user_id, referrer_id))
        
        ref_result = cursor.fetchone()
        
        if ref_result and not ref_result[0]:
            # Aplicar bono de 1 CUP
            cursor.execute('UPDATE users SET credit = credit + 1.0 WHERE user_id = ?', (referrer_id,))
            
            # Marcar bono como aplicado
            cursor.execute('''
                UPDATE referrals 
                SET bonus_applied = TRUE 
                WHERE referred_id = ? AND referrer_id = ?
            ''', (referred_user_id, referrer_id))
            
            conn.commit()
            
            # Notificar al referidor
            try:
                from main import application
                bot = application.bot
                bot.send_message(
                    chat_id=referrer_id,
                    text=f"🎉 ¡Felicidades! Has recibido 1 CUP por referir a un amigo.\n"
                         f"Tu crédito ahora es: {get_user_credit(referrer_id):.2f} CUP"
                )
            except:
                pass
    
    conn.close()

def save_request(user_id, plan_type, plan_name, price, credit_used, phone_number, payment_method):
    """Guarda una nueva solicitud"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO requests (user_id, plan_type, plan_name, price, credit_used, 
                             phone_number, status, request_date, payment_method)
        VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)
    ''', (user_id, plan_type, plan_name, price, credit_used, phone_number, datetime.now(), payment_method))
    
    request_id = cursor.lastrowid
    
    # Actualizar total gastado por el usuario
    cursor.execute('UPDATE users SET total_spent = total_spent + ? WHERE user_id = ?', (price, user_id))
    
    # Si usó crédito, descontarlo
    if credit_used > 0:
        cursor.execute('UPDATE users SET credit = credit - ? WHERE user_id = ?', (credit_used, user_id))
    
    conn.commit()
    conn.close()
    
    return request_id

def get_pending_requests():
    """Obtiene solicitudes pendientes"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT r.id, r.user_id, r.plan_type, r.plan_name, r.price, r.credit_used, 
               r.phone_number, r.request_date, u.username, u.first_name
        FROM requests r
        LEFT JOIN users u ON r.user_id = u.user_id
        WHERE r.status = 'pending'
        ORDER BY r.request_date
    ''')
    
    requests = cursor.fetchall()
    conn.close()
    return requests

def update_request_status(request_id, status, screenshot_path=None):
    """Actualiza el estado de una solicitud"""
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
    
    cursor.execute("SELECT user_id FROM requests WHERE id = ?", (request_id,))
    result = cursor.fetchone()
    user_id = result[0] if result else None
    
    conn.close()
    return user_id

def get_user_orders(user_id):
    """Obtiene los pedidos de un usuario"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, plan_name, price, credit_used, status, request_date
        FROM requests 
        WHERE user_id = ? 
        ORDER BY request_date DESC 
        LIMIT 10
    ''', (user_id,))
    
    orders = cursor.fetchall()
    conn.close()
    
    # Convertir a diccionarios
    result = []
    for order in orders:
        result.append({
            'id': order[0],
            'plan_name': order[1],
            'price': order[2],
            'credit_used': order[3],
            'status': order[4],
            'date': order[5]
        })
    
    return result

def get_user_stats(user_id):
    """Obtiene estadísticas del usuario"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT u.credit, u.total_referrals, u.total_spent, u.referral_code,
               COUNT(r.id) as total_orders,
               COUNT(CASE WHEN r.status = 'confirmed' THEN 1 END) as confirmed_orders
        FROM users u
        LEFT JOIN requests r ON u.user_id = r.user_id
        WHERE u.user_id = ?
        GROUP BY u.user_id
    ''', (user_id,))
    
    result = cursor.fetchone()
    
    # Obtener referidos exitosos
    cursor.execute('SELECT COUNT(*) FROM referrals WHERE referrer_id = ? AND bonus_applied = TRUE', (user_id,))
    successful_refs = cursor.fetchone()[0]
    
    conn.close()
    
    if result:
        return {
            'credit': result[0],
            'total_referrals': result[1],
            'total_spent': result[2],
            'referral_code': result[3],
            'total_orders': result[4],
            'confirmed_orders': result[5],
            'successful_refs': successful_refs
        }
    
    return None

# ==================== HANDLERS PRINCIPALES ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para /start con sistema de referidos"""
    user = update.effective_user
    user_id = user.id
    
    # Verificar si hay parámetro de referencia
    referred_by = None
    if context.args:
        for arg in context.args:
            if arg.startswith('ref='):
                try:
                    referral_code = arg[4:]
                    conn = sqlite3.connect('bot_database.db')
                    cursor = conn.cursor()
                    cursor.execute("SELECT user_id FROM users WHERE referral_code = ?", (referral_code,))
                    result = cursor.fetchone()
                    conn.close()
                    
                    if result and result[0] != user_id:
                        referred_by = result[0]
                except Exception as e:
                    logger.error(f"Error processing referral: {e}")
    
    # Registrar usuario (si es nuevo)
    is_new_user = register_user(user_id, user.username, user.first_name, user.last_name, referred_by)
    
    # Actualizar actividad
    update_user_activity(user_id)
    
    # Si es admin
    if user_id in ADMIN_IDS:
        keyboard = [
            [InlineKeyboardButton("📋 Ver solicitudes pendientes", callback_data='admin_view_requests')],
            [InlineKeyboardButton("📊 Ver estadísticas", callback_data='admin_stats')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f'👑 **¡Bienvenido Administrador {user.first_name}!**\n'
            'Selecciona una opción:',
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        # Menú principal para usuarios normales
        user_credit = get_user_credit(user_id)
        
        # Mensaje especial para nuevos usuarios referidos
        welcome_msg = ""
        if is_new_user and referred_by:
            welcome_msg = f"\n🎉 ¡Bienvenido! Viniste por invitación. "
            welcome_msg += "Cuando hagas tu primer pedido, ¡tu amigo recibirá 1 CUP!"
        
        keyboard = [
            [InlineKeyboardButton("📋 Ver Planes y Comprar", callback_data='view_plans')],
            [InlineKeyboardButton("📦 Mis Pedidos", callback_data='user_my_orders')],
            [InlineKeyboardButton("👤 Mi Perfil y Crédito", callback_data='user_profile')],
            [InlineKeyboardButton("🧑‍🤝‍🧑 Invitar Amigos", callback_data='user_invite')],
            [InlineKeyboardButton("❓ Ayuda", callback_data='user_help')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f'¡Hola {user.first_name}! 👋\n'
            f'**Bienvenido a RECARGAS RÁPIDAS**\n\n'
            f'💳 **Crédito disponible:** `{user_credit:.2f} CUP`\n'
            f'{welcome_msg}\n\n'
            f'Selecciona una opción:',
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

async def user_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el perfil del usuario"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    update_user_activity(user_id)
    
    stats = get_user_stats(user_id)
    
    if stats:
        profile_text = (
            f"👤 **TU PERFIL**\n\n"
            f"💳 **Crédito disponible:** `{stats['credit']:.2f} CUP`\n"
            f"🛒 **Pedidos totales:** {stats['total_orders']}\n"
            f"✅ **Pedidos completados:** {stats['confirmed_orders']}\n"
            f"💰 **Total gastado:** {stats['total_spent']:.2f} CUP\n"
            f"👥 **Personas invitadas:** {stats['total_referrals']}\n"
            f"🎯 **Referidos exitosos:** {stats['successful_refs']}\n"
            f"🔗 **Tu código:** `{stats['referral_code']}`\n\n"
            f"*Ganas 1 CUP por cada amigo que haga su primer pedido.*"
        )
    else:
        profile_text = "❌ Error al cargar tu perfil."
    
    keyboard = [
        [InlineKeyboardButton("🧑‍🤝‍🧑 Invitar Amigos", callback_data='user_invite')],
        [InlineKeyboardButton("📋 Ver Planes", callback_data='view_plans')],
        [InlineKeyboardButton("📦 Mis Pedidos", callback_data='user_my_orders')],
        [InlineKeyboardButton("« Volver al Menú", callback_data='user_back_to_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        profile_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def user_invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sistema de referidos"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    update_user_activity(user_id)
    
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT referral_code FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        ref_code = result[0]
        bot_username = context.bot.username
        invite_link = f"https://t.me/{bot_username}?start=ref={ref_code}"
        
        invite_text = (
            f"🎁 **INVITA AMIGOS Y GANA CRÉDITO**\n\n"
            f"**¡Cada amigo que haga su primer pedido te da 1 CUP!**\n\n"
            f"🔗 **Tu enlace único:**\n"
            f"`{invite_link}`\n\n"
            f"**Cómo funciona:**\n"
            f"1. Comparte este enlace con amigos\n"
            f"2. Cuando se registren, quedarán vinculados a ti\n"
            f"3. **Por su primer pedido, recibes 1 CUP**\n"
            f"4. Usa tu crédito para pagar planes\n\n"
            f"💡 **¡Puedes pagar planes completos con tu crédito!**"
        )
    else:
        invite_text = "❌ Error al generar enlace."
    
    keyboard = [
        [InlineKeyboardButton("👤 Mi Perfil", callback_data='user_profile')],
        [InlineKeyboardButton("📋 Ver Planes", callback_data='view_plans')],
        [InlineKeyboardButton("« Volver al Menú", callback_data='user_back_to_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        invite_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def user_my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra historial de pedidos"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    update_user_activity(user_id)
    
    orders = get_user_orders(user_id)
    
    if not orders:
        orders_text = "📭 **Aún no has hecho pedidos.**\n\n¡Explora nuestros planes!"
    else:
        orders_text = "📋 **TUS ÚLTIMOS PEDIDOS**\n\n"
        
        for order in orders:
            # Emoji según estado
            status_emoji = {
                'pending': '⏳',
                'waiting_payment': '💰',
                'payment_received': '📸',
                'confirmed': '✅',
                'cancelled': '❌'
            }.get(order['status'], '📌')
            
            # Método de pago
            if order['credit_used'] > 0:
                if order['credit_used'] == order['price']:
                    payment = f"({order['credit_used']:.2f}C crédito)"
                else:
                    payment = f"({order['credit_used']:.2f}C crédito + {order['price'] - order['credit_used']:.2f}C transferencia)"
            else:
                payment = "(transferencia)"
            
            orders_text += (
                f"{status_emoji} **Pedido #{order['id']}**\n"
                f"   📦 {order['plan_name']}\n"
                f"   💰 {order['price']:.2f} CUP {payment}\n"
                f"   📅 {order['date'][:16]} | {order['status']}\n"
                f"   ───────────────\n"
            )
    
    keyboard = [
        [InlineKeyboardButton("📋 Ver Planes", callback_data='view_plans')],
        [InlineKeyboardButton("👤 Mi Perfil", callback_data='user_profile')],
        [InlineKeyboardButton("« Volver al Menú", callback_data='user_back_to_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        orders_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def user_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra ayuda"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    update_user_activity(user_id)
    
    help_text = (
        "❓ **AYUDA Y PREGUNTAS FRECUENTES**\n\n"
        
        "**🤔 ¿Cómo funcionan los referidos?**\n"
        "Invita amigos con tu enlace único. Por cada amigo que haga su "
        "PRIMER pedido, recibes 1 CUP en crédito.\n\n"
        
        "**💳 ¿Cómo uso mi crédito?**\n"
        "Al seleccionar un plan, si tienes crédito suficiente, "
        "verás la opción 'PAGAR CON CRÉDITO'.\n\n"
        
        "**💰 ¿Puedo usar crédito parcial?**\n"
        "Sí, selecciona 'Usar crédito parcial' y elige cuánto crédito usar.\n\n"
        
        "**⏱️ ¿Cuánto tarda la activación?**\n"
        "Normalmente 5-15 minutos después del pago confirmado.\n\n"
        
        "**📞 ¿Cómo contacto soporte?**\n"
        "Envía un mensaje directo con tu consulta."
    )
    
    keyboard = [
        [InlineKeyboardButton("📋 Ver Planes", callback_data='view_plans')],
        [InlineKeyboardButton("👤 Mi Perfil", callback_data='user_profile')],
        [InlineKeyboardButton("« Volver al Menú", callback_data='user_back_to_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        help_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def view_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra tipos de planes"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    update_user_activity(user_id)
    
    user_credit = get_user_credit(user_id)
    
    keyboard = [
        [InlineKeyboardButton("📡 Planes de Datos", callback_data='plan_type_datos')],
        [InlineKeyboardButton("📞 Planes de Voz", callback_data='plan_type_voz')],
        [InlineKeyboardButton("💬 Planes de SMS", callback_data='plan_type_sms')],
        [InlineKeyboardButton("👤 Mi Perfil", callback_data='user_profile')],
        [InlineKeyboardButton("« Volver al Menú", callback_data='user_back_to_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"📋 **SELECCIONA TIPO DE PLAN**\n\n"
        f"💳 **Tu crédito:** `{user_credit:.2f} CUP`\n\n"
        f"**Métodos de pago disponibles:**\n"
        f"✅ Transferencia de saldo móvil\n"
        f"✅ Crédito de referidos (si alcanza)\n"
        f"✅ Combinación de ambos\n\n"
        f"Selecciona una categoría:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def select_plan_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra planes específicos"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    plan_type = query.data.replace('plan_type_', '')
    
    update_user_activity(user_id)
    
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, plan_name, price FROM plans WHERE plan_type = ?", (plan_type,))
    plans = cursor.fetchall()
    conn.close()
    
    user_credit = get_user_credit(user_id)
    
    keyboard = []
    type_names = {'datos': 'Datos', 'voz': 'Voz', 'sms': 'SMS'}
    
    for plan_id, plan_name, price in plans:
        # Si tiene crédito suficiente, ofrecer pago con crédito
        if user_credit >= price:
            button_text = f"{plan_name} → {price:.2f} CUP (PAGAR CON CRÉDITO)"
            callback_data = f'select_plan_{plan_id}_credit'
        else:
            button_text = f"{plan_name} → {price:.2f} CUP"
            callback_data = f'select_plan_{plan_id}_transfer'
        
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    # Botón para usar crédito parcial
    if user_credit > 0:
        keyboard.append([InlineKeyboardButton(f"💳 Usar Crédito Parcial ({user_credit:.2f} CUP)", callback_data=f'use_partial_{plan_type}')])
    
    keyboard.append([InlineKeyboardButton("« Volver a Categorías", callback_data='view_plans')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"📋 **Planes de {type_names.get(plan_type, plan_type)}**\n\n"
        f"💳 **Tu crédito:** `{user_credit:.2f} CUP`\n\n"
        f"**Opciones de pago:**\n"
        f"• Planes en **NEGRITA**: pagar con crédito\n"
        f"• Planes normales: pagar con transferencia\n"
        f"• **Usar crédito parcial**: combinar crédito + transferencia\n\n"
        f"Selecciona un plan:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def handle_plan_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja selección de plan y método de pago"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    update_user_activity(user_id)
    
    if data.startswith('select_plan_'):
        parts = data.split('_')
        plan_id = int(parts[2])
        payment_method = parts[3]  # 'credit' o 'transfer'
        
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT plan_type, plan_name, price FROM plans WHERE id = ?", (plan_id,))
        plan = cursor.fetchone()
        conn.close()
        
        if plan:
            plan_type, plan_name, price = plan
            
            user_credit = get_user_credit(user_id)
            
            if payment_method == 'credit':
                # Verificar crédito
                if user_credit < price:
                    await query.edit_message_text(
                        f"❌ **Crédito insuficiente**\n\n"
                        f"Necesitas: {price:.2f} CUP\n"
                        f"Tienes: {user_credit:.2f} CUP\n\n"
                        f"Selecciona otro método de pago.",
                        parse_mode='Markdown'
                    )
                    return
                
                context.user_data['selected_plan'] = {
                    'id': plan_id,
                    'type': plan_type,
                    'name': plan_name,
                    'price': price,
                    'payment_method': 'credit',
                    'credit_used': price
                }
                
                await query.edit_message_text(
                    f"✅ **Plan seleccionado**\n\n"
                    f"📦 **Plan:** {plan_name}\n"
                    f"💰 **Precio:** {price:.2f} CUP\n"
                    f"💳 **Pago con:** Crédito completo\n"
                    f"📉 **Crédito restante:** {(user_credit - price):.2f} CUP\n\n"
                    f"Envía el número de teléfono (8 dígitos, ej: 51234567):",
                    parse_mode='Markdown'
                )
                
            else:  # transfer
                context.user_data['selected_plan'] = {
                    'id': plan_id,
                    'type': plan_type,
                    'name': plan_name,
                    'price': price,
                    'payment_method': 'transfer',
                    'credit_used': 0.0
                }
                
                await query.edit_message_text(
                    f"✅ **Plan seleccionado**\n\n"
                    f"📦 **Plan:** {plan_name}\n"
                    f"💰 **Precio:** {price:.2f} CUP\n"
                    f"💳 **Pago con:** Transferencia\n\n"
                    f"Envía el número de teléfono (8 dígitos, ej: 51234567):",
                    parse_mode='Markdown'
                )
    
    elif data.startswith('use_partial_'):
        plan_type = data.replace('use_partial_', '')
        
        user_credit = get_user_credit(user_id)
        
        context.user_data['awaiting_credit_amount'] = plan_type
        
        await query.edit_message_text(
            f"💳 **USAR CRÉDITO PARCIAL**\n\n"
            f"Tu crédito: `{user_credit:.2f} CUP`\n\n"
            f"Escribe la cantidad de crédito que quieres usar.\n"
            f"Ejemplo: `5.50` para usar 5.50 CUP\n\n"
            f"Luego seleccionarás el plan.",
            parse_mode='Markdown'
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja mensajes de texto"""
    user_id = update.effective_user.id
    message_text = update.message.text
    
    update_user_activity(user_id)
    
    # 1. Usuario especificando crédito parcial
    if 'awaiting_credit_amount' in context.user_data:
        plan_type = context.user_data['awaiting_credit_amount']
        
        try:
            credit_to_use = float(message_text)
            user_credit = get_user_credit(user_id)
            
            if credit_to_use <= 0:
                await update.message.reply_text("❌ Cantidad debe ser mayor a 0.")
                return
            
            if credit_to_use > user_credit:
                await update.message.reply_text(
                    f"❌ **Solo tienes {user_credit:.2f} CUP**\nEscribe menos:",
                    parse_mode='Markdown'
                )
                return
            
            # Guardar crédito a usar
            context.user_data['partial_credit'] = credit_to_use
            
            # Mostrar planes para esa categoría
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()
            cursor.execute("SELECT id, plan_name, price FROM plans WHERE plan_type = ?", (plan_type,))
            plans = cursor.fetchall()
            conn.close()
            
            keyboard = []
            for plan_id, plan_name, price in plans:
                remaining = price - credit_to_use
                
                if remaining <= 0:
                    button_text = f"{plan_name} → {price:.2f} CUP (CRÉDITO COMPLETO)"
                    callback_data = f'select_plan_{plan_id}_credit'
                else:
                    button_text = f"{plan_name} → {price:.2f} CUP ({credit_to_use:.2f}C + {remaining:.2f}C)"
                    callback_data = f'select_plan_{plan_id}_partial_{credit_to_use}'
                
                keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
            
            keyboard.append([InlineKeyboardButton("« Cancelar", callback_data=f'plan_type_{plan_type}')])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"💳 **Usarás {credit_to_use:.2f} CUP de crédito**\nSelecciona plan:",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
            del context.user_data['awaiting_credit_amount']
            
        except ValueError:
            await update.message.reply_text("❌ Escribe solo números (ej: 5.50)")
        return
    
    # 2. Usuario enviando número de teléfono
    elif 'selected_plan' in context.user_data:
        if message_text.isdigit() and len(message_text) == 8:
            phone_number = message_text
            plan = context.user_data['selected_plan']
            
            # Para pagos parciales
            if plan.get('payment_method') == 'partial':
                credit_used = float(plan.get('credit_partial', 0))
                remaining = plan['price'] - credit_used
                payment_method = 'mixed'
            elif plan['payment_method'] == 'credit':
                credit_used = plan['price']
                remaining = 0
                payment_method = 'credit'
            else:
                credit_used = 0
                remaining = plan['price']
                payment_method = 'transfer'
            
            # Guardar solicitud
            request_id = save_request(
                user_id, 
                plan['type'], 
                plan['name'], 
                plan['price'],
                credit_used,
                phone_number,
                payment_method
            )
            
            # Aplicar bono de referido si es primer pedido
            apply_referral_bonus(user_id)
            
            # Mensaje al usuario
            if payment_method == 'credit':
                payment_text = f"💳 **Pago con crédito completo** ({credit_used:.2f} CUP)"
                admin_note = f"✅ PAGADO CON CRÉDITO"
            elif payment_method == 'mixed':
                payment_text = f"💳+💰 **Pago mixto** (Crédito: {credit_used:.2f} CUP + Transferencia: {remaining:.2f} CUP)"
                admin_note = f"💰 PAGO PARCIAL (Crédito usado: {credit_used:.2f} CUP)"
            else:
                payment_text = f"💰 **Pago por transferencia** ({remaining:.2f} CUP)"
                admin_note = f"⏳ PENDIENTE DE PAGO"
            
            await update.message.reply_text(
                f"✅ **Solicitud enviada**\n\n"
                f"🆔 **ID:** #{request_id}\n"
                f"📞 **Teléfono:** `{phone_number}`\n"
                f"📦 **Plan:** {plan['name']}\n"
                f"💰 **Total:** {plan['price']:.2f} CUP\n"
                f"{payment_text}\n\n"
                f"⏳ **En proceso...**",
                parse_mode='Markdown'
            )
            
            # Notificar a administradores
            user = update.effective_user
            keyboard = [
                [
                    InlineKeyboardButton("✅ Aceptar", callback_data=f'admin_accept_{request_id}'),
                    InlineKeyboardButton("❌ Cancelar", callback_data=f'admin_cancel_{request_id}')
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=(
                            f"🚨 **NUEVA SOLICITUD #{request_id}**\n\n"
                            f"👤 **Usuario:** {user.first_name}\n"
                            f"📞 **Teléfono:** `{phone_number}`\n"
                            f"📦 **Plan:** {plan['name']}\n"
                            f"💰 **Precio:** {plan['price']:.2f} CUP\n"
                            f"💳 **{admin_note}**\n"
                            f"📅 **Fecha:** {datetime.now().strftime('%H:%M')}"
                        ),
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                except:
                    pass
            
            del context.user_data['selected_plan']
            
        else:
            await update.message.reply_text(
                "❌ **Número inválido**\nEnvía 8 dígitos (ej: 51234567):",
                parse_mode='Markdown'
            )
    
    # 3. Comando /cancel
    elif message_text.lower() in ['/cancel', 'cancel', 'cancelar']:
        keys = ['awaiting_credit_amount', 'selected_plan', 'partial_credit']
        for key in keys:
            if key in context.user_data:
                del context.user_data[key]
        
        await update.message.reply_text(
            "🔄 **Operación cancelada**\nUsa /start para volver al menú.",
            parse_mode='Markdown'
        )
    
    # 4. Mensaje normal
    else:
        await update.message.reply_text(
            "🤖 **Usa los botones del menú**\nEscribe /start para ver opciones.",
            parse_mode='Markdown'
        )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja capturas de pantalla"""
    user_id = update.effective_user.id
    photo = update.message.photo[-1]
    file_id = photo.file_id
    
    update_user_activity(user_id)
    
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
        
        # Descargar foto
        file = await context.bot.get_file(file_id)
        os.makedirs('screenshots', exist_ok=True)
        screenshot_path = f"screenshots/{request_id}_{user_id}.jpg"
        await file.download_to_drive(screenshot_path)
        
        # Actualizar estado
        update_request_status(request_id, 'payment_received', screenshot_path)
        
        await update.message.reply_text(
            "✅ **Captura recibida**\n\n"
            "📋 **Pago en verificación**\n"
            "Te notificaremos cuando se active.",
            parse_mode='Markdown'
        )
        
        # Notificar admin
        user = update.effective_user
        keyboard = [
            [InlineKeyboardButton("✅ Procesar", callback_data=f'confirm_request_{request_id}')],
            [InlineKeyboardButton("❌ Problema", callback_data=f'cancel_request_{request_id}')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=(
                        f"💰 **PAGO RECIBIDO #{request_id}**\n\n"
                        f"👤 **Usuario:** {user.first_name}\n"
                        f"📦 **Plan:** {plan_name}\n"
                        f"💰 **Monto:** {price:.2f} CUP\n"
                        f"📅 **Hora:** {datetime.now().strftime('%H:%M')}"
                    ),
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                
                # Enviar foto también
                await context.bot.send_photo(
                    chat_id=admin_id,
                    photo=file_id,
                    caption=f"Captura - Solicitud #{request_id}"
                )
            except:
                pass
    
    else:
        await update.message.reply_text(
            "📌 **No tienes pagos pendientes**\nPrimero espera aceptación del admin.",
            parse_mode='Markdown'
        )
    
    conn.close()

# ==================== ADMIN HANDLERS ====================
async def admin_view_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra solicitudes pendientes al admin"""
    query = update.callback_query
    await query.answer()
    
    requests = get_pending_requests()
    
    if not requests:
        keyboard = [[InlineKeyboardButton("« Volver", callback_data='admin_back')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("📭 **No hay solicitudes pendientes**", reply_markup=reply_markup, parse_mode='Markdown')
        return
    
    message_text = "📋 **SOLICITUDES PENDIENTES**\n\n"
    for req in requests:
        req_id, user_id, plan_type, plan_name, price, credit_used, phone, req_date, username, first_name = req
        
        # Método de pago
        if credit_used > 0:
            if credit_used == price:
                payment = f"CRÉDITO ({credit_used:.2f}C)"
            else:
                payment = f"MIXTO ({credit_used:.2f}C crédito)"
        else:
            payment = "TRANSFERENCIA"
        
        message_text += (
            f"🆔 **ID:** {req_id}\n"
            f"👤 **Usuario:** {first_name}\n"
            f"📞 **Teléfono:** {phone}\n"
            f"📦 **Plan:** {plan_name}\n"
            f"💰 **Precio:** {price:.2f} CUP\n"
            f"💳 **Pago:** {payment}\n"
            f"📅 **Hora:** {req_date[11:16]}\n"
            f"────────────────────\n"
        )
    
    keyboard = [[InlineKeyboardButton("« Volver", callback_data='admin_back')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
    
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
        
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=f"**Solicitud #{req_id}** - ¿Aceptar o cancelar?",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            except:
                pass

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra estadísticas al admin"""
    query = update.callback_query
    await query.answer()
    
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    # Totales
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM requests")
    total_requests = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM requests WHERE DATE(request_date) = DATE('now')")
    today_requests = cursor.fetchone()[0]
    
    cursor.execute("SELECT COALESCE(SUM(price), 0) FROM requests WHERE status = 'confirmed'")
    total_income = cursor.fetchone()[0]
    
    # Solicitudes por estado
    cursor.execute("SELECT status, COUNT(*) FROM requests GROUP BY status")
    status_counts = cursor.fetchall()
    
    conn.close()
    
    status_text = ""
    for status, count in status_counts:
        status_emoji = {
            'pending': '⏳',
            'waiting_payment': '💰',
            'payment_received': '📸',
            'confirmed': '✅',
            'cancelled': '❌'
        }.get(status, '📌')
        status_text += f"{status_emoji} {status}: {count}\n"
    
    message = (
        f"📊 **ESTADÍSTICAS**\n\n"
        f"👥 **Usuarios totales:** {total_users}\n"
        f"📋 **Solicitudes totales:** {total_requests}\n"
        f"📅 **Solicitudes hoy:** {today_requests}\n"
        f"💵 **Ingresos totales:** {total_income:.2f} CUP\n\n"
        f"📈 **Estados:**\n{status_text}"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔄 Actualizar", callback_data='admin_stats')],
        [InlineKeyboardButton("« Volver", callback_data='admin_back')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def admin_accept(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin acepta solicitud"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    request_id = int(data.replace('admin_accept_', ''))
    
    await query.edit_message_text(
        f"✅ **Solicitud #{request_id} aceptada**\n"
        f"Instrucciones enviadas al usuario.",
        parse_mode='Markdown'
    )
    
    # Actualizar estado
    update_request_status(request_id, 'waiting_payment')
    
    # Obtener datos para notificar usuario
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, plan_name, price, credit_used FROM requests WHERE id = ?", (request_id,))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        user_id, plan_name, price, credit_used = result
        
        # Calcular cuánto debe transferir
        if credit_used > 0:
            if credit_used == price:
                payment_text = "✅ **PAGADO CON CRÉDITO**\nNo necesitas transferir."
                transfer_amount = 0
            else:
                transfer_amount = price - credit_used
                payment_text = f"💳 **Crédito usado:** {credit_used:.2f} CUP\n💰 **Debes transferir:** {transfer_amount:.2f} CUP"
        else:
            transfer_amount = price
            payment_text = f"💰 **Debes transferir:** {transfer_amount:.2f} CUP"
        
        # Notificar usuario
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    f"✅ **Tu solicitud #{request_id} fue ACEPTADA**\n\n"
                    f"📦 **Plan:** {plan_name}\n"
                    f"💰 **Precio total:** {price:.2f} CUP\n"
                    f"{payment_text}\n\n"
                    f"📲 **INSTRUCCIONES:**\n"
                    f"1. Transfiere {transfer_amount:.2f} CUP al: `{PAYMENT_NUMBER}`\n"
                    f"2. Envía captura de la transferencia\n"
                    f"3. Espera activación"
                ),
                parse_mode='Markdown'
            )
        except:
            pass

async def admin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin cancela solicitud"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    request_id = int(data.replace('admin_cancel_', ''))
    
    user_id = update_request_status(request_id, 'cancelled')
    
    # Notificar usuario si se usó crédito, devolverlo
    if user_id:
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT credit_used FROM requests WHERE id = ?", (request_id,))
        credit_used = cursor.fetchone()[0]
        conn.close()
        
        if credit_used > 0:
            add_user_credit(user_id, credit_used)
        
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"❌ **Tu solicitud #{request_id} fue CANCELADA**\n"
                     f"Contacta soporte si necesitas ayuda.",
                parse_mode='Markdown'
            )
        except:
            pass
    
    await query.edit_message_text(
        f"❌ **Solicitud #{request_id} cancelada**\n"
        f"Usuario notificado.",
        parse_mode='Markdown'
    )

async def confirm_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin confirma pago recibido"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    request_id = int(data.replace('confirm_request_', ''))
    
    user_id = update_request_status(request_id, 'confirmed')
    
    if user_id:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    f"✅ **¡Tu pedido #{request_id} ha sido PROCESADO!**\n\n"
                    f"Tu plan ha sido activado exitosamente.\n\n"
                    f"¡Gracias por usar RECARGAS RÁPIDAS! 🎉"
                ),
                parse_mode='Markdown'
            )
        except:
            pass
    
    await query.edit_message_text(
        f"✅ **Solicitud #{request_id} procesada**\n"
        f"Usuario notificado.",
        parse_mode='Markdown'
    )

async def cancel_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin reporta problema con pago"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    request_id = int(data.replace('cancel_request_', ''))
    
    user_id = update_request_status(request_id, 'cancelled')
    
    # Devolver crédito si se usó
    if user_id:
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT credit_used FROM requests WHERE id = ?", (request_id,))
        credit_used = cursor.fetchone()[0]
        conn.close()
        
        if credit_used > 0:
            add_user_credit(user_id, credit_used)
        
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    f"❌ **Problema con tu pago #{request_id}**\n\n"
                    f"Hubo un problema con tu captura de pago.\n"
                    f"Contacta soporte para más información.\n"
                    f"Si usaste crédito, fue devuelto a tu cuenta."
                ),
                parse_mode='Markdown'
            )
        except:
            pass
    
    await query.edit_message_text(
        f"❌ **Solicitud #{request_id} cancelada por problema**\n"
        f"Usuario notificado.",
        parse_mode='Markdown'
    )

async def admin_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Vuelve al menú admin"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📋 Ver solicitudes pendientes", callback_data='admin_view_requests')],
        [InlineKeyboardButton("📊 Ver estadísticas", callback_data='admin_stats')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        '👑 **Menú de Administrador**\n'
        'Selecciona una opción:',
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def user_back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Vuelve al menú principal usuario"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_credit = get_user_credit(user_id)
    
    keyboard = [
        [InlineKeyboardButton("📋 Ver Planes y Comprar", callback_data='view_plans')],
        [InlineKeyboardButton("📦 Mis Pedidos", callback_data='user_my_orders')],
        [InlineKeyboardButton("👤 Mi Perfil y Crédito", callback_data='user_profile')],
        [InlineKeyboardButton("🧑‍🤝‍🧑 Invitar Amigos", callback_data='user_invite')],
        [InlineKeyboardButton("❓ Ayuda", callback_data='user_help')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f'📱 **Menú Principal**\n\n'
        f'💳 **Tu crédito:** `{user_credit:.2f} CUP`\n\n'
        f'Selecciona una opción:',
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# ==================== MAIN ====================
def main():
    """Función principal"""
    print("🤖 Iniciando bot de recargas con sistema de referidos...")
    
    # Inicializar base de datos
    init_db()
    
    # Crear aplicación
    application = Application.builder().token(TOKEN).build()
    
    # Handlers de comandos
    application.add_handler(CommandHandler("start", start))
    
    # Handlers de botones para usuarios
    application.add_handler(CallbackQueryHandler(user_profile, pattern='^user_profile$'))
    application.add_handler(CallbackQueryHandler(user_invite, pattern='^user_invite$'))
    application.add_handler(CallbackQueryHandler(user_my_orders, pattern='^user_my_orders$'))
    application.add_handler(CallbackQueryHandler(user_help, pattern='^user_help$'))
    application.add_handler(CallbackQueryHandler(view_plans, pattern='^view_plans$'))
    application.add_handler(CallbackQueryHandler(select_plan_type, pattern='^plan_type_'))
    application.add_handler(CallbackQueryHandler(handle_plan_selection, pattern='^(select_plan_|use_partial_)'))
    application.add_handler(CallbackQueryHandler(user_back_to_menu, pattern='^user_back_to_menu$'))
    
    # Handlers de botones para admin
    application.add_handler(CallbackQueryHandler(admin_view_requests, pattern='^admin_view_requests$'))
    application.add_handler(CallbackQueryHandler(admin_stats, pattern='^admin_stats$'))
    application.add_handler(CallbackQueryHandler(admin_accept, pattern='^admin_accept_'))
    application.add_handler(CallbackQueryHandler(admin_cancel, pattern='^admin_cancel_'))
    application.add_handler(CallbackQueryHandler(confirm_request, pattern='^confirm_request_'))
    application.add_handler(CallbackQueryHandler(cancel_request, pattern='^cancel_request_'))
    application.add_handler(CallbackQueryHandler(admin_back, pattern='^admin_back$'))
    
    # Handlers de mensajes
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    print("✅ Bot listo y funcionando!")
    print(f"👑 Admins configurados: {ADMIN_IDS}")
    print("💳 Sistema de referidos: ACTIVADO")
    print("🎯 Créditos por referido: 1 CUP")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    def main():
    """Función principal con Webhook para Render"""
    print("🤖 Iniciando bot con sistema de referidos y créditos...")
    
    # Inicializar base de datos
    init_db()
    
    # Crear aplicación
    application = Application.builder().token(TOKEN).build()
    
    # ==================== CONFIGURAR HANDLERS ====================
    
    # Handlers de comandos
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("cancel", handle_message))
    
    # Handlers de botones para usuarios
    application.add_handler(CallbackQueryHandler(user_profile, pattern='^user_profile$'))
    application.add_handler(CallbackQueryHandler(user_invite, pattern='^user_invite$'))
    application.add_handler(CallbackQueryHandler(user_my_orders, pattern='^user_my_orders$'))
    application.add_handler(CallbackQueryHandler(user_help, pattern='^user_help$'))
    application.add_handler(CallbackQueryHandler(view_plans, pattern='^view_plans$'))
    application.add_handler(CallbackQueryHandler(select_plan_type, pattern='^plan_type_'))
    application.add_handler(CallbackQueryHandler(handle_plan_selection, pattern='^(select_plan_|use_partial_)'))
    application.add_handler(CallbackQueryHandler(user_back_to_menu, pattern='^user_back_to_menu$'))
    
    # Handlers de botones para admin
    application.add_handler(CallbackQueryHandler(admin_view_requests, pattern='^admin_view_requests$'))
    application.add_handler(CallbackQueryHandler(admin_stats, pattern='^admin_stats$'))
    application.add_handler(CallbackQueryHandler(admin_accept, pattern='^admin_accept_'))
    application.add_handler(CallbackQueryHandler(admin_cancel, pattern='^admin_cancel_'))
    application.add_handler(CallbackQueryHandler(confirm_request, pattern='^confirm_request_'))
    application.add_handler(CallbackQueryHandler(cancel_request, pattern='^cancel_request_'))
    application.add_handler(CallbackQueryHandler(admin_back, pattern='^admin_back$'))
    
    # Handlers de mensajes
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    # ==================== MODO WEBHOOK (Render) ====================
    
    # Obtener URL de Render automáticamente
    import os
    render_external_url = os.getenv('RENDER_EXTERNAL_URL')
    render_hostname = os.getenv('RENDER_EXTERNAL_HOSTNAME')
    
    # Si estamos en Render (tiene variable de entorno)
    if render_external_url or render_hostname:
        print("🌐 Detectado Render.com - Configurando Webhook...")
        
        # Usar la URL proporcionada por Render
        if render_external_url:
            webhook_url = f"{render_external_url}/{TOKEN}"
        elif render_hostname:
            webhook_url = f"https://{render_hostname}/{TOKEN}"
        else:
            print("❌ No se pudo determinar la URL de Render")
            return
        
        print(f"✅ Webhook URL: {webhook_url}")
        
        # Importar para webhook
        import asyncio
        from telegram import Update
        import uvicorn
        from fastapi import FastAPI, Request, Response
        import json
        
        # Crear aplicación FastAPI
        app = FastAPI(title="Bot de Recargas")
        
        # Variable global para la aplicación de bot
        global bot_application
        bot_application = application
        
        @app.post(f"/{TOKEN}")
        async def telegram_webhook(request: Request):
            """Endpoint para recibir webhooks de Telegram"""
            try:
                # Leer datos del webhook
                data = await request.json()
                
                # Convertir a objeto Update de Telegram
                update = Update.de_json(data, bot_application.bot)
                
                # Procesar la actualización
                await bot_application.process_update(update)
                
                return Response(status_code=200)
            except Exception as e:
                print(f"❌ Error procesando webhook: {e}")
                return Response(status_code=500)
        
        @app.get("/")
        async def root():
            """Página principal - Health check para Render"""
            return {
                "status": "online",
                "service": "Bot de Recargas ETECSA",
                "mode": "webhook",
                "features": ["referidos", "créditos", "planes ETECSA"],
                "endpoints": {
                    "webhook": f"POST /{TOKEN}",
                    "health": "GET /health"
                }
            }
        
        @app.get("/health")
        async def health_check():
            """Endpoint de salud para Render"""
            return {
                "status": "healthy",
                "bot": "running",
                "timestamp": datetime.now().isoformat()
            }
        
        @app.on_event("startup")
        async def on_startup():
            """Configurar webhook al iniciar la aplicación"""
            print("🚀 Iniciando bot en modo Webhook...")
            
            try:
                # Eliminar webhook anterior si existe
                await application.bot.delete_webhook(drop_pending_updates=True)
                print("✅ Webhooks anteriores eliminados")
                
                # Configurar nuevo webhook
                await application.bot.set_webhook(
                    url=webhook_url,
                    max_connections=40,
                    allowed_updates=["message", "callback_query"]
                )
                print(f"✅ Webhook configurado en: {webhook_url}")
                
                # Verificar información del bot
                bot_info = await application.bot.get_me()
                print(f"🤖 Bot: @{bot_info.username}")
                print(f"💳 Sistema de referidos: ACTIVADO")
                print(f"🎯 Créditos por referido: 1 CUP")
                print(f"👑 Admins: {ADMIN_IDS}")
                
            except Exception as e:
                print(f"❌ Error configurando webhook: {e}")
                # Intentar modo polling como respaldo
                print("🔄 Intentando modo polling como respaldo...")
                asyncio.create_task(run_polling_backup())
        
        async def run_polling_backup():
            """Modo de respaldo si falla webhook"""
            try:
                print("🔄 Iniciando modo polling...")
                await application.initialize()
                await application.start()
                await application.updater.start_polling(
                    allowed_updates=["message", "callback_query"]
                )
                
                # Mantener el bot corriendo
                while True:
                    await asyncio.sleep(3600)
                    
            except Exception as e:
                print(f"❌ Error en modo polling: {e}")
        
        # Configurar puerto para Render
        port = int(os.getenv("PORT", 10000))
        host = "0.0.0.0"
        
        print(f"🌍 Servidor iniciando en: {host}:{port}")
        print(f"🔗 Webhook: {webhook_url}")
        print("📞 Health check: /health")
        
        # Iniciar servidor FastAPI
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info"
        )
        
    else:
        # ==================== MODO POLLING (Desarrollo Local) ====================
        print("💻 Modo desarrollo local - Usando Polling...")
        
        # Eliminar webhook anterior si existe
        import asyncio
        
        async def setup_polling():
            try:
                # Eliminar cualquier webhook previo
                await application.bot.delete_webhook(drop_pending_updates=True)
                print("✅ Webhooks anteriores eliminados")
            except Exception as e:
                print(f"⚠️ No se pudo eliminar webhook: {e}")
            
            # Esperar un momento
            await asyncio.sleep(2)
            
            # Verificar información del bot
            bot_info = await application.bot.get_me()
            print(f"🤖 Bot: @{bot_info.username}")
            print(f"👤 Nombre: {bot_info.first_name}")
            
            # Iniciar polling
            print("🔄 Iniciando polling...")
            await application.run_polling(
                allowed_updates=Update.ALL_TYPES,
                close_loop=False,
                drop_pending_updates=True
            )
        
        # Ejecutar en modo asíncrono
        asyncio.run(setup_polling())