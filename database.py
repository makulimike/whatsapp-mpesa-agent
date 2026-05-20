import sqlite3
from datetime import datetime
import threading

class Database:
    def __init__(self, db_file='shop.db'):
        self.db_file = db_file
        self.local = threading.local()
    
    def get_connection(self):
        """Get thread-local database connection"""
        if not hasattr(self.local, 'conn'):
            self.local.conn = sqlite3.connect(self.db_file, check_same_thread=False)
            self.local.conn.row_factory = sqlite3.Row
            self.setup_database(self.local.conn)
        return self.local.conn
    
    def setup_database(self, conn):
        """Create tables if they don't exist"""
        conn.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE,
                name TEXT,
                price INTEGER,
                stock INTEGER
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT UNIQUE,
                phone TEXT,
                items TEXT,
                amount INTEGER,
                address TEXT,
                status TEXT,
                created_at TIMESTAMP
            )
        ''')
        
        # Check if products exist
        cursor = conn.execute('SELECT COUNT(*) FROM products')
        if cursor.fetchone()[0] == 0:
            products = [
                ('MF001', 'Maize Flour', 120, 100),
                ('RF001', 'Rice', 350, 50),
                ('OIL001', 'Cooking Oil', 250, 75),
                ('SUG001', 'Sugar', 180, 200),
            ]
            for p in products:
                conn.execute('INSERT INTO products (code, name, price, stock) VALUES (?, ?, ?, ?)', p)
            print("✅ Sample products inserted")
        
        conn.commit()
    
    def get_products(self):
        conn = self.get_connection()
        cursor = conn.execute('SELECT * FROM products ORDER BY name')
        return [dict(row) for row in cursor.fetchall()]
    
    def get_product_by_name(self, product_name):
        conn = self.get_connection()
        try:
            cursor = conn.execute('SELECT * FROM products WHERE LOWER(name) = LOWER(?)', (product_name,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            
            cursor = conn.execute('SELECT * FROM products WHERE LOWER(name) LIKE ?', (f'%{product_name.lower()}%',))
            row = cursor.fetchone()
            return dict(row) if row else None
        except Exception as e:
            print(f"Error: {e}")
            return None
    
    def create_order(self, order_id, phone, items, amount, address):
        conn = self.get_connection()
        try:
            conn.execute('''
                INSERT INTO orders (order_id, phone, items, amount, address, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (order_id, phone, items, amount, address, 'pending', datetime.now().isoformat()))
            conn.commit()
            return True
        except Exception as e:
            print(f"Error creating order: {e}")
            return False
    
    def update_order_status(self, order_id, status):
        conn = self.get_connection()
        try:
            conn.execute('UPDATE orders SET status = ? WHERE order_id = ?', (status, order_id))
            conn.commit()
            return True
        except Exception as e:
            print(f"Error updating order: {e}")
            return False
    
    def get_order(self, order_id):
        conn = self.get_connection()
        cursor = conn.execute('SELECT * FROM orders WHERE order_id = ?', (order_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    
    def get_customer_orders(self, phone):
        conn = self.get_connection()
        cursor = conn.execute('SELECT * FROM orders WHERE phone = ? ORDER BY created_at DESC', (phone,))
        return [dict(row) for row in cursor.fetchall()]
    
    def get_all_orders(self, limit=50):
        conn = self.get_connection()
        cursor = conn.execute('SELECT * FROM orders ORDER BY created_at DESC LIMIT ?', (limit,))
        return [dict(row) for row in cursor.fetchall()]
    
    def update_stock(self, product_name, quantity):
        conn = self.get_connection()
        product = self.get_product_by_name(product_name)
        if product:
            new_stock = product['stock'] - quantity
            conn.execute('UPDATE products SET stock = ? WHERE id = ?', (new_stock, product['id']))
            conn.commit()
            return True
        return False
    
    def close(self):
        if hasattr(self.local, 'conn'):
            self.local.conn.close()