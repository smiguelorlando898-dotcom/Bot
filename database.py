# database.py - Funciones compartidas de base de datos
import sqlite3
from datetime import datetime

# Configuración compartida
NUMERO_RECIBIR_SALDO = "50321300"
ADMIN_USERNAME = "@landitho9"

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