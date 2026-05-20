import re
import uuid
import requests
import os
import json
from datetime import datetime, timedelta
from database import Database
from flaresend_client import FlaresendClient

class WhatsAppHandler:
    def __init__(self):
        self.db = Database()
        self.sessions = {}
        self.admin_sessions = {}  # Track admin logins
        self.admin_password = os.getenv('ADMIN_PASSWORD', '1039')
        self.paystack_secret_key = os.getenv('PAYSTACK_SECRET_KEY', '')
        self.flaresend = FlaresendClient()
        
        # Load shop settings
        self.shop_settings = self.load_shop_settings()
        
        print(f"✅ WhatsApp Shop Agent Ready")
        print(f"🔐 Admin password loaded: {'SET' if self.admin_password else 'NOT SET'}")
        print(f"🏪 Shop name: {self.shop_settings.get('name', 'Our Shop')}")
    
    def load_shop_settings(self):
        """Load shop settings from database"""
        try:
            conn = self.db.get_connection()
            cursor = conn.execute("SELECT * FROM settings WHERE key = 'shop_name'")
            row = cursor.fetchone()
            
            if row:
                return {'name': row['value']}
            else:
                conn.execute("INSERT INTO settings (key, value) VALUES ('shop_name', 'Our Shop')")
                conn.commit()
                return {'name': 'Our Shop'}
        except:
            conn = self.db.get_connection()
            conn.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')
            conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('shop_name', 'Our Shop')")
            conn.commit()
            return {'name': 'Our Shop'}
    
    def save_shop_settings(self):
        """Save shop settings to database"""
        try:
            conn = self.db.get_connection()
            conn.execute("UPDATE settings SET value = ? WHERE key = 'shop_name'", (self.shop_settings['name'],))
            conn.commit()
        except Exception as e:
            print(f"Error saving shop settings: {e}")
    
    def get_shop_name(self):
        """Get current shop name"""
        return self.shop_settings.get('name', 'Our Shop')
    
    def set_shop_name(self, new_name):
        """Set new shop name"""
        self.shop_settings['name'] = new_name
        self.save_shop_settings()
    
    def send_whatsapp_message(self, to_number: str, message: str):
        """Send message"""
        return self.flaresend.send_message(to_number, message)
    
    def is_admin(self, phone):
        """Check if user has an active admin session"""
        if phone in self.admin_sessions:
            expiry = self.admin_sessions[phone]
            if datetime.now() < expiry:
                return True
            else:
                del self.admin_sessions[phone]
        return False
    
    def show_admin_menu(self, phone):
        """Show admin menu options"""
        shop_name = self.get_shop_name()
        menu = "🔐 *ADMIN PANEL*\n\n"
        menu += f"🏪 *Current Shop Name:* {shop_name}\n\n"
        menu += "*What would you like to do?*\n\n"
        menu += "📦 *1. ADD PRODUCT*\n"
        menu += "   Send: ADD\n\n"
        menu += "📋 *2. LIST PRODUCTS*\n"
        menu += "   Send: LIST\n\n"
        menu += "✏️ *3. EDIT PRODUCT*\n"
        menu += "   Send: EDIT\n\n"
        menu += "📊 *4. UPDATE STOCK*\n"
        menu += "   Send: STOCK\n\n"
        menu += "🗑️ *5. DELETE PRODUCT*\n"
        menu += "   Send: DELETE\n\n"
        menu += "🏪 *6. CHANGE SHOP NAME*\n"
        menu += "   Send: SHOP NAME\n\n"
        menu += "🔓 *7. LOGOUT*\n"
        menu += "   Send: LOGOUT\n\n"
        menu += "Type the command number or name to continue."
        
        self.send_whatsapp_message(phone, menu)
    
    def handle_admin_command(self, phone, message):
        """Handle admin commands when logged in"""
        message_lower = message.lower().strip()
        
        # Check for awaiting states first
        admin_state = self.sessions.get(phone, {}).get('admin_state', '')
        
        # ============ AWAITING PRODUCT DETAILS (ADD) ============
        if admin_state == 'awaiting_product_details':
            if message_lower == 'cancel':
                self.sessions[phone]['admin_state'] = ''
                self.show_admin_menu(phone)
                return True
            
            try:
                parts = [p.strip() for p in message.split(',')]
                if len(parts) >= 3:
                    name = parts[0]
                    price = int(parts[1])
                    stock = int(parts[2])
                    
                    code = name[:3].upper() + str(int(datetime.now().timestamp()))[-4:]
                    
                    conn = self.db.get_connection()
                    conn.execute(
                        'INSERT INTO products (code, name, price, stock) VALUES (?, ?, ?, ?)',
                        (code, name, price, stock)
                    )
                    conn.commit()
                    
                    self.sessions[phone]['admin_state'] = ''
                    response = f"✅ *Product Added!*\n\n📦 Name: {name}\n💰 Price: KES {price}\n📊 Stock: {stock}\n🔖 Code: {code}\n\nSend *ADMIN* for menu"
                    self.send_whatsapp_message(phone, response)
                else:
                    self.send_whatsapp_message(phone, "❌ Please use format: `Name, Price, Stock`\nExample: `Wheat Flour, 250, 50`")
            except Exception as e:
                self.send_whatsapp_message(phone, f"❌ Error: {e}\nPlease use format: Name, Price, Stock")
            return True
        
        # ============ AWAITING EDIT SELECTION ============
        if admin_state == 'awaiting_edit_selection':
            products = self.db.get_products()
            selected = None
            
            if message.isdigit():
                idx = int(message) - 1
                if 0 <= idx < len(products):
                    selected = products[idx]
            else:
                for p in products:
                    if p['code'].lower() == message_lower:
                        selected = p
                        break
            
            if selected:
                self.sessions[phone]['admin_edit_product'] = selected
                self.sessions[phone]['admin_state'] = 'awaiting_edit_details'
                response = f"✏️ *Editing: {selected['name']}*\n\n"
                response += f"Current Price: KES {selected['price']}\n"
                response += f"Current Stock: {selected['stock']}\n\n"
                response += "Send new details in format:\n"
                response += "`new_price, new_stock`\n\n"
                response += "Example: `300, 75`\n\n"
                response += "Send *CANCEL* to cancel"
            else:
                response = "❌ Product not found. Send the product NUMBER or CODE.\n\nSend *CANCEL* to cancel"
            
            self.send_whatsapp_message(phone, response)
            return True
        
        # ============ AWAITING EDIT DETAILS ============
        if admin_state == 'awaiting_edit_details':
            if message_lower == 'cancel':
                self.sessions[phone]['admin_state'] = ''
                self.show_admin_menu(phone)
                return True
            
            try:
                parts = [p.strip() for p in message.split(',')]
                if len(parts) >= 2:
                    new_price = int(parts[0])
                    new_stock = int(parts[1])
                    product = self.sessions[phone].get('admin_edit_product')
                    
                    if product:
                        conn = self.db.get_connection()
                        conn.execute(
                            'UPDATE products SET price = ?, stock = ? WHERE id = ?',
                            (new_price, new_stock, product['id'])
                        )
                        conn.commit()
                        
                        response = f"✅ *Product Updated!*\n\n📦 {product['name']}\n💰 New Price: KES {new_price}\n📊 New Stock: {new_stock}\n\nSend *ADMIN* for menu"
                        self.sessions[phone]['admin_state'] = ''
                        self.sessions[phone].pop('admin_edit_product', None)
                    else:
                        response = "❌ Error: Product not found"
                else:
                    response = "❌ Please use format: `new_price, new_stock`\nExample: `300, 75`"
            except Exception as e:
                response = f"❌ Error: {e}"
            
            self.send_whatsapp_message(phone, response)
            return True
        
        # ============ AWAITING STOCK SELECTION ============
        if admin_state == 'awaiting_stock_selection':
            products = self.db.get_products()
            selected = None
            
            if message.isdigit():
                idx = int(message) - 1
                if 0 <= idx < len(products):
                    selected = products[idx]
            else:
                for p in products:
                    if p['code'].lower() == message_lower:
                        selected = p
                        break
            
            if selected:
                self.sessions[phone]['admin_stock_product'] = selected
                self.sessions[phone]['admin_state'] = 'awaiting_stock_quantity'
                response = f"📊 *Updating Stock: {selected['name']}*\n\n"
                response += f"Current Stock: {selected['stock']}\n\n"
                response += "Send the *NEW STOCK QUANTITY*\n"
                response += "Example: `100`\n\n"
                response += "Send *CANCEL* to cancel"
            else:
                response = "❌ Product not found. Send the product NUMBER or CODE.\n\nSend *CANCEL* to cancel"
            
            self.send_whatsapp_message(phone, response)
            return True
        
        # ============ AWAITING STOCK QUANTITY ============
        if admin_state == 'awaiting_stock_quantity':
            if message_lower == 'cancel':
                self.sessions[phone]['admin_state'] = ''
                self.show_admin_menu(phone)
                return True
            
            try:
                new_stock = int(message)
                product = self.sessions[phone].get('admin_stock_product')
                
                if product:
                    conn = self.db.get_connection()
                    conn.execute('UPDATE products SET stock = ? WHERE id = ?', (new_stock, product['id']))
                    conn.commit()
                    
                    response = f"✅ *Stock Updated!*\n\n📦 {product['name']}\n📊 New Stock: {new_stock}\n\nSend *ADMIN* for menu"
                    self.sessions[phone]['admin_state'] = ''
                    self.sessions[phone].pop('admin_stock_product', None)
                else:
                    response = "❌ Error: Product not found"
            except Exception as e:
                response = f"❌ Error: {e}\nPlease send a valid number"
            
            self.send_whatsapp_message(phone, response)
            return True
        
        # ============ AWAITING DELETE SELECTION ============
        if admin_state == 'awaiting_delete_selection':
            products = self.db.get_products()
            selected = None
            
            if message.isdigit():
                idx = int(message) - 1
                if 0 <= idx < len(products):
                    selected = products[idx]
            else:
                for p in products:
                    if p['code'].lower() == message_lower:
                        selected = p
                        break
            
            if selected:
                self.sessions[phone]['admin_delete_product'] = selected
                self.sessions[phone]['admin_state'] = 'awaiting_delete_confirm'
                response = f"⚠️ *Confirm Deletion*\n\n"
                response += f"Are you sure you want to delete:\n"
                response += f"📦 {selected['name']}\n"
                response += f"💰 Price: KES {selected['price']}\n"
                response += f"📊 Stock: {selected['stock']}\n\n"
                response += "Reply *YES* to delete or *CANCEL*"
            else:
                response = "❌ Product not found. Send the product NUMBER or CODE.\n\nSend *CANCEL* to cancel"
            
            self.send_whatsapp_message(phone, response)
            return True
        
        # ============ AWAITING DELETE CONFIRM ============
        if admin_state == 'awaiting_delete_confirm':
            if message_lower == 'yes':
                product = self.sessions[phone].get('admin_delete_product')
                if product:
                    conn = self.db.get_connection()
                    conn.execute('DELETE FROM products WHERE id = ?', (product['id'],))
                    conn.commit()
                    response = f"✅ *Product Deleted!*\n\n📦 {product['name']} has been removed."
                    self.sessions[phone]['admin_state'] = ''
                    self.sessions[phone].pop('admin_delete_product', None)
                else:
                    response = "❌ Error: Product not found"
            elif message_lower == 'cancel':
                response = "❌ Deletion cancelled."
                self.sessions[phone]['admin_state'] = ''
            else:
                response = "❌ Reply *YES* to delete or *CANCEL*"
            
            self.send_whatsapp_message(phone, response)
            return True
        
        # ============ AWAITING SHOP NAME ============
        if admin_state == 'awaiting_shop_name':
            if message_lower == 'cancel':
                self.sessions[phone]['admin_state'] = ''
                self.show_admin_menu(phone)
                return True
            
            new_name = message.strip()
            old_name = self.get_shop_name()
            self.set_shop_name(new_name)
            self.sessions[phone]['admin_state'] = ''
            response = f"✅ *Shop Name Changed!*\n\nOld: {old_name}\nNew: {new_name}\n\nSend *ADMIN* for menu"
            self.send_whatsapp_message(phone, response)
            return True
        
        # ============ REGULAR COMMANDS ============
        
        # ADD PRODUCT
        if message_lower == 'add' or message_lower == '1':
            self.sessions[phone] = self.sessions.get(phone, {})
            self.sessions[phone]['admin_state'] = 'awaiting_product_details'
            self.send_whatsapp_message(phone, "📦 *ADD PRODUCT*\n\nSend product details in format:\n`Name, Price, Stock`\n\nExample: `Wheat Flour, 250, 50`\n\nSend *CANCEL* to cancel")
            return True
        
        # LIST PRODUCTS
        if message_lower == 'list' or message_lower == '2':
            products = self.db.get_products()
            if not products:
                self.send_whatsapp_message(phone, "📋 No products found. Use ADD to add products.")
            else:
                response = "📋 *YOUR PRODUCTS*\n\n"
                for p in products:
                    response += f"🔖 *{p['name']}*\n"
                    response += f"   Code: {p['code']}\n"
                    response += f"   Price: KES {p['price']}\n"
                    response += f"   Stock: {p['stock']}\n\n"
                self.send_whatsapp_message(phone, response)
            return True
        
        # EDIT PRODUCT
        if message_lower == 'edit' or message_lower == '3':
            products = self.db.get_products()
            if not products:
                self.send_whatsapp_message(phone, "📋 No products to edit. Use ADD to add products first.")
                return True
            
            self.sessions[phone]['admin_state'] = 'awaiting_edit_selection'
            response = "✏️ *EDIT PRODUCT*\n\n"
            response += "Select a product to edit:\n\n"
            for idx, p in enumerate(products, 1):
                response += f"{idx}. {p['name']} - KES {p['price']} (Stock: {p['stock']})\n"
            response += "\nSend the product *NUMBER* or *CODE*\n"
            response += "Example: `1` or `MF001`\n\n"
            response += "Send *CANCEL* to cancel"
            self.send_whatsapp_message(phone, response)
            return True
        
        # UPDATE STOCK
        if message_lower == 'stock' or message_lower == '4':
            products = self.db.get_products()
            if not products:
                self.send_whatsapp_message(phone, "📋 No products. Use ADD to add products first.")
                return True
            
            self.sessions[phone]['admin_state'] = 'awaiting_stock_selection'
            response = "📊 *UPDATE STOCK*\n\n"
            response += "Select a product to update stock:\n\n"
            for idx, p in enumerate(products, 1):
                response += f"{idx}. {p['name']} - Current stock: {p['stock']}\n"
            response += "\nSend the product *NUMBER* or *CODE*\n"
            response += "Example: `1` or `MF001`\n\n"
            response += "Send *CANCEL* to cancel"
            self.send_whatsapp_message(phone, response)
            return True
        
        # DELETE PRODUCT
        if message_lower == 'delete' or message_lower == '5':
            products = self.db.get_products()
            if not products:
                self.send_whatsapp_message(phone, "📋 No products to delete. Use ADD to add products first.")
                return True
            
            self.sessions[phone]['admin_state'] = 'awaiting_delete_selection'
            response = "🗑️ *DELETE PRODUCT*\n\n"
            response += "Select a product to delete:\n\n"
            for idx, p in enumerate(products, 1):
                response += f"{idx}. {p['name']} - KES {p['price']} (Stock: {p['stock']})\n"
            response += "\nSend the product *NUMBER* or *CODE*\n"
            response += "Example: `1` or `MF001`\n\n"
            response += "Send *CANCEL* to cancel"
            self.send_whatsapp_message(phone, response)
            return True
        
        # CHANGE SHOP NAME
        if message_lower.startswith('shop name'):
            parts = message.split(' ', 2)
            if len(parts) >= 3:
                new_name = parts[2].strip()
                old_name = self.get_shop_name()
                self.set_shop_name(new_name)
                self.send_whatsapp_message(phone, f"✅ *Shop Name Changed!*\n\nOld name: {old_name}\nNew name: {new_name}")
            else:
                current_name = self.get_shop_name()
                self.sessions[phone] = self.sessions.get(phone, {})
                self.sessions[phone]['admin_state'] = 'awaiting_shop_name'
                self.send_whatsapp_message(phone, f"🏪 *CHANGE SHOP NAME*\n\nCurrent shop name: {current_name}\n\nSend the new shop name:\nExample: `Mike's Groceries`\n\nSend *CANCEL* to cancel")
            return True
        
        # LOGOUT
        if message_lower == 'logout' or message_lower == '7' or message_lower == '6':
            if phone in self.admin_sessions:
                del self.admin_sessions[phone]
            self.sessions[phone] = self.sessions.get(phone, {})
            self.sessions[phone]['admin_state'] = ''
            self.send_whatsapp_message(phone, "🔐 *Logged out!* Your admin session has ended.\n\nSend *MENU* to continue shopping.")
            return True
        
        # If not recognized, show menu
        self.show_admin_menu(phone)
        return True
    
    def process_message(self, phone, message):
        """Process message - Main entry point"""
        message = message.strip()
        message_lower = message.lower()
        
        # ============ FIRST: Check for admin login ============
        if message_lower.startswith('admin'):
            parts = message.split()
            if len(parts) >= 2:
                password = parts[1]
                if password == self.admin_password:
                    self.admin_sessions[phone] = datetime.now() + timedelta(hours=1)
                    self.show_admin_menu(phone)
                    return
                else:
                    self.send_whatsapp_message(phone, "❌ *Invalid Password!* Access denied.\n\nSend *ADMIN your_password* to try again.")
                    return
            else:
                self.send_whatsapp_message(phone, "🔐 *Admin Access*\n\nPlease send your password:\n`ADMIN your_password`\n\nExample: `ADMIN 1039`")
                return
        
        # ============ SECOND: Check if logged in as admin ============
        if self.is_admin(phone):
            if self.handle_admin_command(phone, message):
                return
        
        # ============ THIRD: Customer flow ============
        
        if phone not in self.sessions:
            self.sessions[phone] = {
                'cart': [],
                'state': 'main_menu',
                'order_id': None,
                'total': 0
            }
        
        session = self.sessions[phone]
        state = session['state']
        
        # ============ GREETINGS ============
        if message_lower in ['hi', 'hello', 'hey', 'hola', 'jambo', 'sasa']:
            response = f"👋 *Hello!* Welcome to {self.get_shop_name()}! 😊\n\n{self.show_main_menu(phone)}"
            self.send_whatsapp_message(phone, response)
            return
        
        if message_lower in ['thank you', 'thanks', 'asante']:
            response = f"🙏 *You're welcome!* Thank you for shopping at {self.get_shop_name()}."
            self.send_whatsapp_message(phone, response)
            return
        
        # ============ MAIN MENU ============
        if state == 'main_menu':
            if message_lower in ['menu', 'start', 'shop', 'products']:
                response = self.show_main_menu(phone)
                self.send_whatsapp_message(phone, response)
                return
            
            if message.isdigit():
                response = self.handle_product_selection(phone, int(message))
                self.send_whatsapp_message(phone, response)
                return
            
            if message_lower == 'cart':
                response = self.show_cart(phone)
                self.send_whatsapp_message(phone, response)
                return
            
            if message_lower == 'checkout':
                response = self.start_checkout(phone)
                self.send_whatsapp_message(phone, response)
                return
            
            if message_lower == 'status':
                response = self.show_status(phone)
                self.send_whatsapp_message(phone, response)
                return
            
            response = f"🤔 I didn't quite understand '*{message}*'.\n\n{self.show_main_menu(phone)}"
            self.send_whatsapp_message(phone, response)
            return
        
        # ============ AWAITING QUANTITY ============
        elif state == 'awaiting_quantity':
            if message.isdigit():
                quantity = int(message)
                if quantity > 0:
                    response = self.add_to_cart(phone, quantity)
                    self.send_whatsapp_message(phone, response)
                    return
                else:
                    self.send_whatsapp_message(phone, "❌ Please enter a valid quantity (1 or more).")
                    return
            elif message_lower == 'cancel':
                session['state'] = 'main_menu'
                session['pending_product'] = None
                self.send_whatsapp_message(phone, "❌ Cancelled. Send *MENU* to continue.")
                return
            else:
                self.send_whatsapp_message(phone, "❌ Please send a number for quantity (e.g., 2) or send *CANCEL*.")
                return
        
        # ============ IN CART ============
        elif state == 'in_cart':
            if message_lower == 'checkout':
                response = self.start_checkout(phone)
                self.send_whatsapp_message(phone, response)
                return
            elif message_lower == 'menu':
                response = self.show_main_menu(phone)
                self.send_whatsapp_message(phone, response)
                return
            elif message_lower == 'cart':
                response = self.show_cart(phone)
                self.send_whatsapp_message(phone, response)
                return
            elif message_lower == 'clear':
                session['cart'] = []
                session['total'] = 0
                session['state'] = 'main_menu'
                self.send_whatsapp_message(phone, "🗑️ Cart cleared. Send *MENU* to shop.")
                return
            else:
                response = self.show_cart(phone)
                self.send_whatsapp_message(phone, response)
                return
        
        # ============ AWAITING ADDRESS ============
        elif state == 'awaiting_address':
            if message_lower == 'cancel':
                session['state'] = 'main_menu'
                self.send_whatsapp_message(phone, "❌ Checkout cancelled.")
                return
            else:
                response = self.save_address_and_payment(phone, message)
                self.send_whatsapp_message(phone, response)
                return
        
        # ============ AWAITING PAYMENT ============
        elif state == 'awaiting_payment':
            if message_lower == 'pay':
                response = self.process_payment(phone)
                self.send_whatsapp_message(phone, response)
                return
            elif message_lower == 'cancel':
                session['state'] = 'main_menu'
                self.send_whatsapp_message(phone, "❌ Payment cancelled.")
                return
            else:
                self.send_whatsapp_message(phone, "💳 Reply *PAY* to complete payment or *CANCEL*.")
                return
        
        # Default
        response = self.show_main_menu(phone)
        self.send_whatsapp_message(phone, response)
    
    def show_main_menu(self, phone):
        """Show customer menu"""
        products = self.db.get_products()
        shop_name = self.get_shop_name()
        
        if not products:
            return f"📋 {shop_name} - No products available. Please check back later."
        
        self.sessions[phone]['state'] = 'main_menu'
        
        menu = f"🛒 *WELCOME TO {shop_name.upper()}* 🛒\n\n"
        menu += "*Here are our products:*\n\n"
        
        for idx, p in enumerate(products, 1):
            stock_status = "✅" if p['stock'] > 0 else "❌"
            menu += f"{idx}. *{p['name']}* - KES {p['price']} {stock_status}\n"
        
        menu += "\n" + "─" * 30 + "\n\n"
        menu += "📝 *How to order:*\n"
        menu += "• Send the *NUMBER* of the product\n"
        menu += "• Then send the *QUANTITY*\n\n"
        menu += "*Commands:*\n"
        menu += "• `CART` - View cart\n"
        menu += "• `CHECKOUT` - Pay\n"
        menu += "• `STATUS` - Your orders\n\n"
        menu += f"💬 *Send a number to start shopping at {shop_name}!*"
        
        return menu
    
    def handle_product_selection(self, phone, product_number):
        """Select product"""
        products = self.db.get_products()
        
        if product_number < 1 or product_number > len(products):
            return "❌ Invalid selection. Send a number from the menu."
        
        selected = products[product_number - 1]
        
        if selected['stock'] <= 0:
            return f"❌ Sorry, {selected['name']} is out of stock."
        
        self.sessions[phone]['pending_product'] = selected
        self.sessions[phone]['state'] = 'awaiting_quantity'
        
        return f"📦 *{selected['name']}*\n💰 Price: KES {selected['price']}\n📊 In stock: {selected['stock']}\n\n🔢 *How many?* (Send a number)\n\nSend *CANCEL* to cancel"
    
    def add_to_cart(self, phone, quantity):
        """Add to cart"""
        session = self.sessions[phone]
        product = session.get('pending_product')
        
        if not product:
            session['state'] = 'main_menu'
            return "❌ Session expired. Send *MENU* to start over."
        
        if quantity < 1:
            return "❌ Quantity must be at least 1."
        
        if product['stock'] < quantity:
            return f"❌ Only {product['stock']} available."
        
        for item in session['cart']:
            if item['product_id'] == product['id']:
                item['quantity'] += quantity
                item['subtotal'] = item['price'] * item['quantity']
                break
        else:
            session['cart'].append({
                'product_id': product['id'],
                'product_name': product['name'],
                'price': product['price'],
                'quantity': quantity,
                'subtotal': product['price'] * quantity
            })
        
        session['total'] = sum(item['subtotal'] for item in session['cart'])
        session['pending_product'] = None
        session['state'] = 'in_cart'
        
        total_items = sum(item['quantity'] for item in session['cart'])
        grand = session['total'] + 100
        
        return f"✅ *Added {quantity}x {product['name']}*\n\n🛒 Cart: {total_items} item(s)\n💰 Subtotal: KES {session['total']}\n🚚 Delivery: KES 100\n💵 Total: KES {grand}\n\nSend *CHECKOUT* to pay"
    
    def show_cart(self, phone):
        """Show cart"""
        session = self.sessions[phone]
        
        if not session['cart']:
            session['state'] = 'main_menu'
            return "🛒 Your cart is empty. Send *MENU* to shop!"
        
        cart = "🛒 *YOUR CART*\n\n"
        for item in session['cart']:
            cart += f"• {item['product_name']}: {item['quantity']} x KES {item['price']} = KES {item['subtotal']}\n"
        
        grand = session['total'] + 100
        cart += f"\n💰 Subtotal: KES {session['total']}\n🚚 Delivery: KES 100\n💵 Total: KES {grand}\n\nSend *CHECKOUT* to pay"
        
        return cart
    
    def start_checkout(self, phone):
        """Start checkout"""
        session = self.sessions[phone]
        
        if not session['cart']:
            session['state'] = 'main_menu'
            return "🛒 Cart empty. Send *MENU* to add items."
        
        session['state'] = 'awaiting_address'
        grand_total = session['total'] + 100
        
        return f"📍 *DELIVERY ADDRESS*\n\nTotal: KES {grand_total}\n\nSend your address:\nExample: Westlands, Mpaka Road, Nairobi\n\nSend *CANCEL* to cancel"
    
    def save_address_and_payment(self, phone, address):
        """Save address"""
        session = self.sessions[phone]
        grand_total = session['total'] + 100
        
        order_id = str(uuid.uuid4())[:8].upper()
        session['order_id'] = order_id
        session['address'] = address
        
        items_text = ", ".join([f"{item['quantity']}x {item['product_name']}" for item in session['cart']])
        self.db.create_order(order_id, phone, items_text, grand_total, address)
        
        session['state'] = 'awaiting_payment'
        
        return f"✅ *Order #{order_id} Saved*\n📍 {address}\n💰 Total: KES {grand_total}\n\n💳 Reply *PAY* to complete payment"
    
    def process_payment(self, phone):
        """Process payment"""
        session = self.sessions.get(phone)
        
        if not session or not session.get('order_id'):
            return "❌ No order found. Send *MENU* to start over."
        
        grand_total = session['total'] + 100
        
        if not self.paystack_secret_key:
            return self.simulate_payment(phone)
        
        try:
            self.send_whatsapp_message(phone, "⏳ Processing payment...")
            
            reference = f"ORDER_{session['order_id']}_{int(datetime.now().timestamp())}"
            amount_in_cents = int(grand_total * 100)
            clean_phone = phone.replace('+', '').replace('254', '')
            customer_email = f"customer_{clean_phone}@whatsappshop.com"
            
            response = requests.post(
                "https://api.paystack.co/transaction/initialize",
                json={
                    "email": customer_email,
                    "amount": amount_in_cents,
                    "currency": "KES",
                    "reference": reference,
                    "channels": ["mobile_money", "card"]
                },
                headers={
                    "Authorization": f"Bearer {self.paystack_secret_key}",
                    "Content-Type": "application/json"
                },
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('status'):
                    conn = self.db.get_connection()
                    for item in session['cart']:
                        product = self.db.get_product_by_name(item['product_name'])
                        if product:
                            new_stock = product['stock'] - item['quantity']
                            conn.execute('UPDATE products SET stock = ? WHERE id = ?', (new_stock, product['id']))
                            conn.commit()
                    
                    self.db.update_order_status(session['order_id'], 'pending')
                    session['state'] = 'order_confirmed'
                    payment_link = data['data']['authorization_url']
                    
                    return f"💰 *PAYMENT READY*\n\nOrder: {session['order_id']}\nAmount: KES {grand_total}\n\n📱 M-PESA: STK push sent\n💳 Card: {payment_link}\n\n✅ Pay to confirm"
                else:
                    return f"❌ Payment error: {data.get('message')}"
            else:
                return "❌ Payment service error. Try again"
        except Exception as e:
            print(f"Payment error: {e}")
            return "❌ Payment error. Try again"
    
    def simulate_payment(self, phone):
        """Simulate payment for testing"""
        session = self.sessions.get(phone)
        
        if not session or not session.get('order_id'):
            return "❌ No order found."
        
        grand_total = session['total'] + 100
        
        conn = self.db.get_connection()
        for item in session['cart']:
            product = self.db.get_product_by_name(item['product_name'])
            if product:
                new_stock = product['stock'] - item['quantity']
                conn.execute('UPDATE products SET stock = ? WHERE id = ?', (new_stock, product['id']))
                conn.commit()
        
        self.db.update_order_status(session['order_id'], 'paid')
        session['state'] = 'order_confirmed'
        
        return f"💰 *PAYMENT CONFIRMED!*\n\nOrder: {session['order_id']}\nAmount: KES {grand_total}\n📍 {session.get('address', 'N/A')}\n\n✅ Order confirmed! Delivery in 2 hours.\n\nSend *MENU* to shop more"
    
    def show_status(self, phone):
        """Show order history"""
        orders = self.db.get_customer_orders(phone)
        if not orders:
            return "No orders yet. Send *MENU* to start shopping!"
        
        response = "📊 *YOUR ORDERS*\n\n"
        for order in orders[:5]:
            status_icon = "✅" if order['status'] == 'paid' else "⏳"
            response += f"{status_icon} *{order['order_id']}*\n"
            response += f"   {order['items']}\n"
            response += f"   KES {order['amount']}\n\n"
        
        return response