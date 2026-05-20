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
        self.admin_sessions = {}
        self.admin_password = os.getenv('ADMIN_PASSWORD', '1039')
        self.paystack_secret_key = os.getenv('PAYSTACK_SECRET_KEY', '')
        self.flaresend = FlaresendClient()
        
        # Cart expiration time (hours) - Cart clears after 2 hours of inactivity
        self.cart_expiry_hours = 2
        
        self.shop_settings = self.load_shop_settings()
        
        print(f"✅ Intelligent WhatsApp Shop Agent Ready")
        print(f"🏪 Shop: {self.shop_settings.get('name', 'Our Shop')}")
        print(f"⏰ Cart expires after {self.cart_expiry_hours} hours of inactivity")
    
    def load_shop_settings(self):
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
            conn.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
            conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('shop_name', 'Our Shop')")
            conn.commit()
            return {'name': 'Our Shop'}
    
    def save_shop_settings(self):
        try:
            conn = self.db.get_connection()
            conn.execute("UPDATE settings SET value = ? WHERE key = 'shop_name'", (self.shop_settings['name'],))
            conn.commit()
        except Exception as e:
            print(f"Error: {e}")
    
    def get_shop_name(self):
        return self.shop_settings.get('name', 'Our Shop')
    
    def set_shop_name(self, new_name):
        self.shop_settings['name'] = new_name
        self.save_shop_settings()
    
    def send_whatsapp_message(self, to_number: str, message: str):
        return self.flaresend.send_message(to_number, message)
    
    def is_admin(self, phone):
        if phone in self.admin_sessions:
            if datetime.now() < self.admin_sessions[phone]:
                return True
            else:
                del self.admin_sessions[phone]
        return False
    
    def is_cart_expired(self, session):
        """Check if cart has expired due to inactivity"""
        if 'last_activity' in session:
            last_active = session['last_activity']
            if datetime.now() - last_active > timedelta(hours=self.cart_expiry_hours):
                return True
        return False
    
    def clear_cart(self, phone):
        """Clear the user's cart completely"""
        if phone in self.sessions:
            self.sessions[phone]['cart'] = []
            self.sessions[phone]['total'] = 0
            self.sessions[phone]['state'] = 'main_menu'
            self.sessions[phone]['pending_product'] = None
            self.sessions[phone]['order_id'] = None
            self.sessions[phone]['address'] = None
            self.sessions[phone]['last_activity'] = datetime.now()
            return True
        return False
    
    def update_activity(self, phone):
        """Update last activity timestamp"""
        if phone in self.sessions:
            self.sessions[phone]['last_activity'] = datetime.now()
    
    def show_admin_menu(self, phone):
        shop_name = self.get_shop_name()
        menu = f"🔐 *ADMIN PORTAL - {shop_name.upper()}*\n\n"
        menu += "What would you like to manage?\n\n"
        menu += "📦 *ADD PRODUCT* - Send: ADD\n"
        menu += "📋 *VIEW PRODUCTS* - Send: LIST\n"
        menu += "✏️ *EDIT PRODUCT* - Send: EDIT\n"
        menu += "📊 *UPDATE STOCK* - Send: STOCK\n"
        menu += "🗑️ *DELETE PRODUCT* - Send: DELETE\n"
        menu += "🏪 *CHANGE SHOP NAME* - Send: SHOP NAME\n"
        menu += "🔓 *EXIT ADMIN* - Send: LOGOUT\n\n"
        menu += "Type a command or just tell me what you want to do."
        self.send_whatsapp_message(phone, menu)
    
    def handle_admin_command(self, phone, message):
        message_lower = message.lower().strip()
        
        # LOGOUT - always available
        if message_lower in ['logout', 'exit', 'quit', 'done', '6', '7']:
            if phone in self.admin_sessions:
                del self.admin_sessions[phone]
            if phone in self.sessions:
                self.sessions[phone]['admin_state'] = ''
            self.send_whatsapp_message(phone, f"🔐 *Logged out!* Thanks for managing {self.get_shop_name()}.\n\nSend *MENU* to continue shopping.")
            return True
        
        # Check admin states
        admin_state = self.sessions.get(phone, {}).get('admin_state', '')
        
        # ADD PRODUCT flow
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
                    conn.execute('INSERT INTO products (code, name, price, stock) VALUES (?, ?, ?, ?)', (code, name, price, stock))
                    conn.commit()
                    self.sessions[phone]['admin_state'] = ''
                    self.send_whatsapp_message(phone, f"✅ *'{name}' added to your shop!*\n💰 Price: KES {price}\n📊 Stock: {stock}\n🔖 Code: {code}\n\nNeed to add another? Send *ADD* again, or *LIST* to see all products.")
                else:
                    self.send_whatsapp_message(phone, "❌ Please use format: `Name, Price, Stock`\nExample: `Wheat Flour, 250, 50`\n\nSend *CANCEL* to cancel")
            except:
                self.send_whatsapp_message(phone, "❌ Invalid format. Use: Name, Price, Stock\nExample: `Wheat Flour, 250, 50`")
            return True
        
        # EDIT - select product
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
                self.send_whatsapp_message(phone, f"✏️ *Editing {selected['name']}*\n💰 Current price: KES {selected['price']}\n📊 Current stock: {selected['stock']}\n\nSend new price and stock: `price, stock`\nExample: `300, 75`\n\nSend *CANCEL* to cancel")
            else:
                self.send_whatsapp_message(phone, "❌ Product not found. Send the NUMBER or CODE from the list.\n\nSend *CANCEL* to cancel")
            return True
        
        # EDIT - get new values
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
                        conn.execute('UPDATE products SET price = ?, stock = ? WHERE id = ?', (new_price, new_stock, product['id']))
                        conn.commit()
                        self.sessions[phone]['admin_state'] = ''
                        self.send_whatsapp_message(phone, f"✅ *{product['name']} updated!*\n💰 New price: KES {new_price}\n📊 New stock: {new_stock}\n\nSend *LIST* to see all products.")
                    else:
                        self.send_whatsapp_message(phone, "❌ Error. Please try *EDIT* again.")
                else:
                    self.send_whatsapp_message(phone, "❌ Send: `price, stock`\nExample: `300, 75`")
            except:
                self.send_whatsapp_message(phone, "❌ Invalid. Send: `price, stock`\nExample: `300, 75`")
            return True
        
        # STOCK - select product
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
                self.send_whatsapp_message(phone, f"📊 *Stock update for {selected['name']}*\n📊 Current stock: {selected['stock']}\n\nSend the NEW stock quantity.\nExample: `100`\n\nSend *CANCEL* to cancel")
            else:
                self.send_whatsapp_message(phone, "❌ Product not found. Send the NUMBER or CODE.\n\nSend *CANCEL* to cancel")
            return True
        
        # STOCK - set quantity
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
                    self.sessions[phone]['admin_state'] = ''
                    self.send_whatsapp_message(phone, f"✅ *Stock updated for {product['name']}*\n📊 New stock: {new_stock}\n\nSend *LIST* to see all products.")
                else:
                    self.send_whatsapp_message(phone, "❌ Error. Try *STOCK* again.")
            except:
                self.send_whatsapp_message(phone, "❌ Send a valid number for stock quantity.")
            return True
        
        # DELETE - select product
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
                self.send_whatsapp_message(phone, f"⚠️ *Confirm deletion*\n\nAre you sure you want to remove *{selected['name']}*?\n💰 Price: KES {selected['price']}\n📊 Stock: {selected['stock']}\n\nReply *YES* to delete or *NO* to cancel.")
            else:
                self.send_whatsapp_message(phone, "❌ Product not found. Send the NUMBER or CODE.\n\nSend *CANCEL* to cancel")
            return True
        
        # DELETE - confirm
        if admin_state == 'awaiting_delete_confirm':
            if message_lower == 'yes':
                product = self.sessions[phone].get('admin_delete_product')
                if product:
                    conn = self.db.get_connection()
                    conn.execute('DELETE FROM products WHERE id = ?', (product['id'],))
                    conn.commit()
                    self.sessions[phone]['admin_state'] = ''
                    self.send_whatsapp_message(phone, f"✅ *{product['name']} removed from your shop!*")
                else:
                    self.send_whatsapp_message(phone, "❌ Error. Try *DELETE* again.")
            elif message_lower == 'no' or message_lower == 'cancel':
                self.sessions[phone]['admin_state'] = ''
                self.send_whatsapp_message(phone, "❌ Deletion cancelled.")
            else:
                self.send_whatsapp_message(phone, "❌ Reply *YES* to delete or *NO* to cancel.")
            return True
        
        # SHOP NAME - interactive
        if admin_state == 'awaiting_shop_name':
            if message_lower == 'cancel':
                self.sessions[phone]['admin_state'] = ''
                self.show_admin_menu(phone)
                return True
            new_name = message.strip()
            old_name = self.get_shop_name()
            self.set_shop_name(new_name)
            self.sessions[phone]['admin_state'] = ''
            self.send_whatsapp_message(phone, f"✅ *Shop name changed!*\nOld: {old_name}\nNew: {new_name}\n\nCustomers will now see '{new_name}' in your shop.")
            return True
        
        # REGULAR COMMANDS
        if message_lower in ['add', '1']:
            self.sessions[phone]['admin_state'] = 'awaiting_product_details'
            self.send_whatsapp_message(phone, "📦 *Add a new product*\n\nSend product details:\n`Name, Price, Stock`\n\nExample: `Wheat Flour, 250, 50`\n\nSend *CANCEL* to cancel")
            return True
        
        if message_lower in ['list', '2']:
            products = self.db.get_products()
            if not products:
                self.send_whatsapp_message(phone, "📋 Your shop is empty. Send *ADD* to add products.")
            else:
                response = f"📋 *Your products in {self.get_shop_name()}*\n\n"
                for p in products:
                    response += f"🔖 *{p['name']}*\n"
                    response += f"   Code: {p['code']}\n"
                    response += f"   Price: KES {p['price']}\n"
                    response += f"   Stock: {p['stock']}\n\n"
                self.send_whatsapp_message(phone, response)
            return True
        
        if message_lower in ['edit', '3']:
            products = self.db.get_products()
            if not products:
                self.send_whatsapp_message(phone, "No products to edit. Send *ADD* first.")
                return True
            self.sessions[phone]['admin_state'] = 'awaiting_edit_selection'
            response = "✏️ *Edit product*\n\nWhich product?\n\n"
            for idx, p in enumerate(products, 1):
                response += f"{idx}. {p['name']} - KES {p['price']} (Stock: {p['stock']})\n"
            response += "\nSend the product NUMBER or CODE.\nExample: `1` or `MF001`\n\nSend *CANCEL* to cancel"
            self.send_whatsapp_message(phone, response)
            return True
        
        if message_lower in ['stock', '4']:
            products = self.db.get_products()
            if not products:
                self.send_whatsapp_message(phone, "No products. Send *ADD* first.")
                return True
            self.sessions[phone]['admin_state'] = 'awaiting_stock_selection'
            response = "📊 *Update stock*\n\nWhich product?\n\n"
            for idx, p in enumerate(products, 1):
                response += f"{idx}. {p['name']} - Current stock: {p['stock']}\n"
            response += "\nSend the product NUMBER or CODE.\nExample: `1` or `MF001`\n\nSend *CANCEL* to cancel"
            self.send_whatsapp_message(phone, response)
            return True
        
        if message_lower in ['delete', '5']:
            products = self.db.get_products()
            if not products:
                self.send_whatsapp_message(phone, "No products to delete. Send *ADD* first.")
                return True
            self.sessions[phone]['admin_state'] = 'awaiting_delete_selection'
            response = "🗑️ *Delete product*\n\nWhich product?\n\n"
            for idx, p in enumerate(products, 1):
                response += f"{idx}. {p['name']} - KES {p['price']}\n"
            response += "\nSend the product NUMBER or CODE.\nExample: `1` or `MF001`\n\nSend *CANCEL* to cancel"
            self.send_whatsapp_message(phone, response)
            return True
        
        if message_lower.startswith('shop name'):
            parts = message.split(' ', 2)
            if len(parts) >= 3:
                new_name = parts[2].strip()
                old_name = self.get_shop_name()
                self.set_shop_name(new_name)
                self.send_whatsapp_message(phone, f"✅ *Shop name changed!*\nOld: {old_name}\nNew: {new_name}")
            else:
                self.sessions[phone]['admin_state'] = 'awaiting_shop_name'
                self.send_whatsapp_message(phone, f"🏪 *Change shop name*\n\nCurrent name: {self.get_shop_name()}\n\nSend the new shop name.\nExample: `Mike's Groceries`\n\nSend *CANCEL* to cancel")
            return True
        
        # If nothing matched, show menu
        self.show_admin_menu(phone)
        return True
    
    def process_message(self, phone, message):
        """Intelligent message processing with cart management"""
        message = message.strip()
        message_lower = message.lower()
        
        # Check for admin login
        if message_lower.startswith('admin'):
            parts = message.split()
            if len(parts) >= 2:
                if parts[1] == self.admin_password:
                    self.admin_sessions[phone] = datetime.now() + timedelta(hours=1)
                    self.send_whatsapp_message(phone, f"🔐 *Welcome back, Admin!* You're now managing {self.get_shop_name()}.\n\n{self.get_admin_greeting()}")
                    self.show_admin_menu(phone)
                else:
                    self.send_whatsapp_message(phone, "❌ *Invalid password*.\n\nSend *ADMIN your_password* to access admin panel.")
                return
            else:
                self.send_whatsapp_message(phone, "🔐 *Admin access*\n\nSend: `ADMIN your_password` to manage your shop.")
                return
        
        # Check if admin and logged in
        if self.is_admin(phone):
            if self.handle_admin_command(phone, message):
                return
        
        # Initialize customer session
        if phone not in self.sessions:
            self.sessions[phone] = {
                'cart': [], 
                'state': 'main_menu', 
                'order_id': None, 
                'total': 0,
                'last_activity': datetime.now()
            }
            self.send_whatsapp_message(phone, self.get_welcome_message())
            return
        
        session = self.sessions[phone]
        
        # Check if cart has expired
        if self.is_cart_expired(session) and session['cart']:
            self.clear_cart(phone)
            self.send_whatsapp_message(phone, "🕐 *Cart Expired*\n\nYour cart has been cleared due to inactivity (>2 hours).\n\nSend *MENU* to start fresh!")
            return
        
        # Update last activity
        self.update_activity(phone)
        
        state = session['state']
        
        # Check if this is a location message
        is_location = self.is_location_message(message)
        
        # Intelligent greeting responses
        if message_lower in ['hi', 'hello', 'hey', 'hola', 'jambo', 'sasa', 'hi there', 'good morning', 'good afternoon', 'good evening']:
            response = f"👋 *Hello!* Welcome to {self.get_shop_name()}! 😊\n\n{self.show_main_menu(phone)}"
            self.send_whatsapp_message(phone, response)
            return
        
        if message_lower in ['thank you', 'thanks', 'asante', 'thx']:
            response = f"🙏 *You're welcome!* Thank you for shopping at {self.get_shop_name()}.\n\nAnything else you'd like? Send *MENU* to continue."
            self.send_whatsapp_message(phone, response)
            return
        
        if message_lower in ['bye', 'goodbye', 'kwaheri']:
            response = f"👋 *Goodbye!* Thank you for visiting {self.get_shop_name()}.\n\nCome back anytime!"
            self.send_whatsapp_message(phone, response)
            return
        
        # CLEAR CART command
        if message_lower == 'clear' or message_lower == 'clear cart':
            if self.clear_cart(phone):
                self.send_whatsapp_message(phone, "🗑️ *Cart Cleared!*\n\nYour shopping cart has been emptied.\n\nSend *MENU* to start fresh.")
            else:
                self.send_whatsapp_message(phone, "🛒 Your cart is already empty. Send *MENU* to start shopping.")
            return
        
        # MAIN MENU
        if state == 'main_menu':
            if message_lower in ['menu', 'start', 'shop', 'products', 'catalog']:
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
            
            # Natural language understanding
            if 'want' in message_lower or 'order' in message_lower or 'buy' in message_lower:
                response = "🛒 I'd love to help you order!\n\nSend *MENU* to see our products, then just send the product number and quantity.\n\nExample: Send `2` then `3` for 3 items.\n\nTo clear your cart, send *CLEAR*"
                self.send_whatsapp_message(phone, response)
                return
            
            response = f"🤔 I didn't understand '*{message}*'.\n\n{self.show_main_menu(phone)}"
            self.send_whatsapp_message(phone, response)
            return
        
        # AWAITING QUANTITY
        if state == 'awaiting_quantity':
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
        
        # IN CART
        if state == 'in_cart':
            if message_lower == 'checkout':
                response = self.start_checkout(phone)
                self.send_whatsapp_message(phone, response)
                return
            if message_lower == 'menu':
                response = self.show_main_menu(phone)
                self.send_whatsapp_message(phone, response)
                return
            if message_lower == 'cart':
                response = self.show_cart(phone)
                self.send_whatsapp_message(phone, response)
                return
            if message_lower == 'clear':
                self.clear_cart(phone)
                self.send_whatsapp_message(phone, "🗑️ *Cart Cleared!*\n\nYour cart is now empty. Send *MENU* to start fresh.")
                return
            response = self.show_cart(phone)
            self.send_whatsapp_message(phone, response)
            return
        
        # AWAITING ADDRESS
        if state == 'awaiting_address':
            if message_lower == 'cancel':
                session['state'] = 'main_menu'
                self.send_whatsapp_message(phone, "❌ Checkout cancelled. Send *MENU* to continue.")
                return
            
            if is_location:
                address = self.format_location_address(message)
                response = self.save_address_and_payment(phone, address)
                self.send_whatsapp_message(phone, response)
                return
            
            if message_lower == 'share location' or message_lower == 'share my location':
                self.send_whatsapp_message(phone, "📍 *Share Your Location*\n\nPlease tap the attachment icon 📎 in WhatsApp, then select 'Location' and share your current location.\n\nOr type your address manually.\n\nSend *CANCEL* to cancel.")
                return
            
            if len(message) > 5:
                response = self.save_address_and_payment(phone, message)
                self.send_whatsapp_message(phone, response)
                return
            else:
                self.send_whatsapp_message(phone, "📍 *Delivery Address*\n\nPlease send your full delivery address, or tap the attachment icon 📎 and share your current location.\n\nExample: Westlands, Mpaka Road, Nairobi\n\nSend *CLEAR* to clear cart\nSend *CANCEL* to cancel")
                return
        
        # AWAITING PAYMENT
        if state == 'awaiting_payment':
            if message_lower == 'pay':
                response = self.process_payment(phone)
                self.send_whatsapp_message(phone, response)
                # Clear cart after successful payment
                if 'order_confirmed' in session and session['state'] == 'order_confirmed':
                    self.clear_cart(phone)
                return
            if message_lower == 'cancel':
                session['state'] = 'main_menu'
                self.send_whatsapp_message(phone, "❌ Payment cancelled. Send *MENU* to continue.")
                return
            if message_lower == 'clear':
                self.clear_cart(phone)
                self.send_whatsapp_message(phone, "🗑️ *Cart Cleared!*\n\nYour cart has been emptied. Send *MENU* to start fresh.")
                return
            self.send_whatsapp_message(phone, "💳 Reply *PAY* to complete payment, *CLEAR* to clear cart, or *CANCEL* to cancel.")
            return
        
        # Default
        response = self.show_main_menu(phone)
        self.send_whatsapp_message(phone, response)
    
    def is_location_message(self, message):
        """Check if message contains location coordinates"""
        location_patterns = [
            r'https?://maps\.google\.com',
            r'https?://www\.google\.com/maps',
            r'@[-?\d.]+,[-?\d.]+',
            r'latitude.*longitude',
            r'location'
        ]
        
        for pattern in location_patterns:
            if re.search(pattern, message.lower()):
                return True
        return False
    
    def format_location_address(self, message):
        """Format location message into readable address"""
        coord_match = re.search(r'@([-\d.]+),([-\d.]+)', message)
        if coord_match:
            lat = coord_match.group(1)
            lng = coord_match.group(2)
            return f"📍 Shared Location (Lat: {lat}, Lng: {lng})"
        
        if 'maps.google.com' in message or 'google.com/maps' in message:
            return "📍 Shared Location - Customer shared their location via Google Maps"
        
        return "📍 Shared Location - Customer's current location"
    
    def get_welcome_message(self):
        return f"👋 *Welcome to {self.get_shop_name()}!*\n\nWe're excited to serve you! 😊\n\nSend *MENU* to see our products and start shopping.\n\n🛒 Send *CLEAR* to clear your cart at any time."
    
    def get_admin_greeting(self):
        return f"✨ You can now manage {self.get_shop_name()}.\n\nWhat would you like to do today?"
    
    def show_main_menu(self, phone):
        products = self.db.get_products()
        shop_name = self.get_shop_name()
        
        if not products:
            return f"📋 {shop_name} - No products available. Please check back later."
        
        session = self.sessions[phone]
        session['state'] = 'main_menu'
        
        menu = f"🛒 *{shop_name.upper()}* 🛒\n\n"
        menu += "*Our products:*\n\n"
        
        for idx, p in enumerate(products, 1):
            stock_status = "✅" if p['stock'] > 0 else "❌"
            menu += f"{idx}. *{p['name']}* - KES {p['price']} {stock_status}\n"
        
        menu += "\n" + "─" * 25 + "\n\n"
        menu += "📝 *To order:*\n"
        menu += "• Send the product *NUMBER*\n"
        menu += "• Then send the *QUANTITY*\n\n"
        menu += "*Commands:*\n"
        menu += "`CART` - View cart\n"
        menu += "`CHECKOUT` - Pay\n"
        menu += "`STATUS` - Your orders\n"
        menu += "`CLEAR` - Clear cart\n\n"
        menu += f"Send a number to start shopping at {shop_name}!"
        
        if session['cart']:
            total_items = sum(item['quantity'] for item in session['cart'])
            menu += f"\n\n🛒 *You have {total_items} item(s) in cart*\nSend *CLEAR* to empty cart"
        
        return menu
    
    def handle_product_selection(self, phone, product_number):
        products = self.db.get_products()
        
        if product_number < 1 or product_number > len(products):
            return "❌ Invalid selection. Send a number from the menu."
        
        selected = products[product_number - 1]
        
        if selected['stock'] <= 0:
            return f"❌ Sorry, {selected['name']} is out of stock."
        
        session = self.sessions[phone]
        session['pending_product'] = selected
        session['state'] = 'awaiting_quantity'
        
        return f"📦 *{selected['name']}*\n💰 Price: KES {selected['price']}\n📊 In stock: {selected['stock']}\n\n🔢 *How many would you like?*\nSend a number (e.g., 2)\n\nSend *CANCEL* to cancel"
    
    def add_to_cart(self, phone, quantity):
        session = self.sessions[phone]
        product = session.get('pending_product')
        
        if not product:
            session['state'] = 'main_menu'
            return "❌ Session expired. Send *MENU* to start over."
        
        if quantity < 1:
            return "❌ Quantity must be at least 1."
        
        if product['stock'] < quantity:
            return f"❌ Only {product['stock']} available. Please try a smaller quantity."
        
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
        
        return f"✅ *Added {quantity}x {product['name']} to your cart!*\n\n🛒 Cart: {total_items} item(s)\n💰 Subtotal: KES {session['total']}\n🚚 Delivery: KES 100\n💵 Total: KES {grand}\n\nSend *CHECKOUT* to pay, *MENU* for more, or *CLEAR* to clear cart"
    
    def show_cart(self, phone):
        session = self.sessions[phone]
        
        if not session['cart']:
            session['state'] = 'main_menu'
            return "🛒 Your cart is empty. Send *MENU* to start shopping!"
        
        cart = "🛒 *YOUR CART*\n\n"
        for i, item in enumerate(session['cart'], 1):
            cart += f"{i}. {item['product_name']}: {item['quantity']} x KES {item['price']} = KES {item['subtotal']}\n"
        
        grand = session['total'] + 100
        cart += f"\n💰 Subtotal: KES {session['total']}\n🚚 Delivery: KES 100\n💵 Total: KES {grand}\n\nSend *CHECKOUT* to complete order\nSend *CLEAR* to empty cart\nSend *MENU* to add more items"
        
        return cart
    
    def start_checkout(self, phone):
        session = self.sessions[phone]
        
        if not session['cart']:
            session['state'] = 'main_menu'
            return "🛒 Your cart is empty. Send *MENU* to add items."
        
        session['state'] = 'awaiting_address'
        grand_total = session['total'] + 100
        
        return f"📍 *Delivery Information*\n\nTotal: KES {grand_total}\n\n*How would you like to provide your address?*\n\n1️⃣ *Share Location* - Tap the attachment icon 📎 and select 'Location' to share your current location\n\n2️⃣ *Type Manually* - Send your full address\n\nExample: Westlands, Mpaka Road, Nairobi\n\nSend *CLEAR* to clear cart\nSend *CANCEL* to cancel"
    
    def save_address_and_payment(self, phone, address):
        session = self.sessions[phone]
        grand_total = session['total'] + 100
        
        order_id = str(uuid.uuid4())[:8].upper()
        session['order_id'] = order_id
        session['address'] = address
        
        items_text = ", ".join([f"{item['quantity']}x {item['product_name']}" for item in session['cart']])
        self.db.create_order(order_id, phone, items_text, grand_total, address)
        
        session['state'] = 'awaiting_payment'
        
        return f"✅ *Order #{order_id} created!*\n📍 Delivery: {address}\n💰 Total: KES {grand_total}\n\n💳 *Payment Options:*\n• M-PESA (STK Push)\n• Credit/Debit Card\n• Bank Transfer\n\nReply *PAY* to complete payment\nReply *CLEAR* to clear cart\nReply *CANCEL* to cancel"
    
    def process_payment(self, phone):
        session = self.sessions.get(phone)
        
        if not session or not session.get('order_id'):
            return "❌ No order found. Send *MENU* to start over."
        
        grand_total = session['total'] + 100
        
        if not self.paystack_secret_key:
            result = self.simulate_payment(phone)
            # Clear cart after successful payment
            self.clear_cart(phone)
            return result
        
        try:
            self.send_whatsapp_message(phone, "⏳ Processing your payment... Please wait.")
            
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
                    "channels": ["mobile_money", "card", "bank_transfer"]
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
                    
                    # Clear cart after successful payment
                    self.clear_cart(phone)
                    
                    return f"💰 *PAYMENT READY*\n\n📦 *Order:* {session['order_id']}\n💵 *Amount:* KES {grand_total}\n\n🔗 *Click the link below to complete payment:*\n{payment_link}\n\n📱 *On the Paystack page you can pay with:*\n• M-PESA (STK push to your phone)\n• Credit/Debit Card\n• Bank Transfer\n\n✅ Payment is automatic - your order will be confirmed instantly.\n\nSend *STATUS* to check order status."
                else:
                    return f"❌ Payment error: {data.get('message')}\n\nPlease try again or contact support."
            else:
                return "❌ Payment service error. Please try again."
        except Exception as e:
            print(f"Payment error: {e}")
            return "❌ Payment error. Please try again."
    
    def simulate_payment(self, phone):
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
        
        return f"💰 *PAYMENT CONFIRMED! (Demo Mode)*\n\n📦 *Order:* {session['order_id']}\n💵 *Amount:* KES {grand_total}\n📍 *Delivery:* {session.get('address', 'N/A')}\n\n✅ *Order confirmed!*\n🚚 We'll deliver within 2 hours.\n\nSend *MENU* to continue shopping or *STATUS* to track order."
    
    def show_status(self, phone):
        orders = self.db.get_customer_orders(phone)
        if not orders:
            return "No orders yet. Send *MENU* to start shopping!"
        
        response = f"📊 *YOUR ORDERS - {self.get_shop_name().upper()}*\n\n"
        for order in orders[:5]:
            status_icon = "✅" if order['status'] == 'paid' else "⏳"
            response += f"{status_icon} *{order['order_id']}*\n"
            response += f"   {order['items']}\n"
            response += f"   KES {order['amount']}\n\n"
        
        return response