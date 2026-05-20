import re
import uuid
import requests
import os
from datetime import datetime, timedelta
from database_supabase import Database
from flaresend_client import FlaresendClient

class WhatsAppHandler:
    def __init__(self):
        self.db = Database()
        self.sessions = {}
        self.admin_sessions = {}
        self.admin_password = os.getenv('ADMIN_PASSWORD', '1039')
        self.paystack_secret_key = os.getenv('PAYSTACK_SECRET_KEY', '')
        self.flaresend = FlaresendClient()
        self.cart_expiry_hours = 2
        
        print(f"✅ Intelligent WhatsApp Shop Agent Ready")
        print(f"🏪 Shop: {self.db.get_shop_name()}")
        print(f"⏰ Cart expires after {self.cart_expiry_hours} hours")
    
    def get_shop_name(self):
        return self.db.get_shop_name()
    
    def set_shop_name(self, new_name):
        self.db.set_shop_name(new_name)
    
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
        if 'last_activity' in session:
            if datetime.now() - session['last_activity'] > timedelta(hours=self.cart_expiry_hours):
                return True
        return False
    
    def clear_cart(self, phone):
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
        if phone in self.sessions:
            self.sessions[phone]['last_activity'] = datetime.now()
    
    def show_admin_menu(self, phone):
        menu = f"🔐 *ADMIN PORTAL - {self.get_shop_name().upper()}*\n\n"
        menu += "📦 ADD PRODUCT - Send: ADD\n"
        menu += "📋 VIEW PRODUCTS - Send: LIST\n"
        menu += "✏️ EDIT PRODUCT - Send: EDIT\n"
        menu += "📊 UPDATE STOCK - Send: STOCK\n"
        menu += "🗑️ DELETE PRODUCT - Send: DELETE\n"
        menu += "🏪 CHANGE SHOP NAME - Send: SHOP NAME\n"
        menu += "🔓 EXIT ADMIN - Send: LOGOUT\n"
        self.send_whatsapp_message(phone, menu)
    
    def handle_admin_command(self, phone, message):
        message_lower = message.lower().strip()
        
        # LOGOUT
        if message_lower in ['logout', '6', '7']:
            if phone in self.admin_sessions:
                del self.admin_sessions[phone]
            if phone in self.sessions:
                self.sessions[phone]['admin_state'] = ''
            self.send_whatsapp_message(phone, f"🔐 Logged out from {self.get_shop_name()}!")
            return True
        
        admin_state = self.sessions.get(phone, {}).get('admin_state', '')
        
        # AWAITING PRODUCT DETAILS (ADD)
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
                    self.db.add_product(name, price, stock)
                    self.sessions[phone]['admin_state'] = ''
                    self.send_whatsapp_message(phone, f"✅ '{name}' added! Price: KES {price}, Stock: {stock}")
                else:
                    self.send_whatsapp_message(phone, "❌ Format: Name, Price, Stock\nExample: Wheat Flour, 250, 50")
            except Exception as e:
                self.send_whatsapp_message(phone, f"❌ Error: {e}")
            return True
        
        # AWAITING EDIT SELECTION
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
                self.send_whatsapp_message(phone, f"✏️ Editing {selected['name']}\nCurrent: KES {selected['price']}, Stock: {selected['stock']}\nSend: price, stock\nExample: 300, 75")
            else:
                self.send_whatsapp_message(phone, "❌ Product not found. Send NUMBER or CODE.")
            return True
        
        # AWAITING EDIT DETAILS
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
                        self.db.update_product(product['id'], new_price, new_stock)
                        self.sessions[phone]['admin_state'] = ''
                        self.send_whatsapp_message(phone, f"✅ {product['name']} updated! New price: KES {new_price}, Stock: {new_stock}")
                    else:
                        self.send_whatsapp_message(phone, "❌ Error. Try EDIT again.")
                else:
                    self.send_whatsapp_message(phone, "❌ Send: price, stock\nExample: 300, 75")
            except:
                self.send_whatsapp_message(phone, "❌ Invalid. Send: price, stock")
            return True
        
        # AWAITING STOCK SELECTION
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
                self.send_whatsapp_message(phone, f"📊 Stock update for {selected['name']}\nCurrent stock: {selected['stock']}\nSend NEW stock quantity.\nExample: 100")
            else:
                self.send_whatsapp_message(phone, "❌ Product not found.")
            return True
        
        # AWAITING STOCK QUANTITY
        if admin_state == 'awaiting_stock_quantity':
            if message_lower == 'cancel':
                self.sessions[phone]['admin_state'] = ''
                self.show_admin_menu(phone)
                return True
            try:
                new_stock = int(message)
                product = self.sessions[phone].get('admin_stock_product')
                if product:
                    self.db.update_product(product['id'], None, new_stock)
                    self.sessions[phone]['admin_state'] = ''
                    self.send_whatsapp_message(phone, f"✅ Stock updated for {product['name']}! New stock: {new_stock}")
                else:
                    self.send_whatsapp_message(phone, "❌ Error. Try STOCK again.")
            except:
                self.send_whatsapp_message(phone, "❌ Send a valid number.")
            return True
        
        # AWAITING DELETE SELECTION
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
                self.send_whatsapp_message(phone, f"⚠️ Confirm deletion of {selected['name']}?\nPrice: KES {selected['price']}, Stock: {selected['stock']}\nReply YES to delete or NO to cancel.")
            else:
                self.send_whatsapp_message(phone, "❌ Product not found.")
            return True
        
        # AWAITING DELETE CONFIRM
        if admin_state == 'awaiting_delete_confirm':
            if message_lower == 'yes':
                product = self.sessions[phone].get('admin_delete_product')
                if product:
                    self.db.delete_product(product['id'])
                    self.sessions[phone]['admin_state'] = ''
                    self.send_whatsapp_message(phone, f"✅ {product['name']} removed from your shop!")
                else:
                    self.send_whatsapp_message(phone, "❌ Error.")
            elif message_lower == 'no' or message_lower == 'cancel':
                self.sessions[phone]['admin_state'] = ''
                self.send_whatsapp_message(phone, "❌ Deletion cancelled.")
            else:
                self.send_whatsapp_message(phone, "❌ Reply YES to delete or NO to cancel.")
            return True
        
        # AWAITING SHOP NAME
        if admin_state == 'awaiting_shop_name':
            if message_lower == 'cancel':
                self.sessions[phone]['admin_state'] = ''
                self.show_admin_menu(phone)
                return True
            new_name = message.strip()
            self.db.set_shop_name(new_name)
            self.sessions[phone]['admin_state'] = ''
            self.send_whatsapp_message(phone, f"✅ Shop name changed to: {new_name}")
            return True
        
        # REGULAR ADMIN COMMANDS
        if message_lower in ['add', '1']:
            self.sessions[phone]['admin_state'] = 'awaiting_product_details'
            self.send_whatsapp_message(phone, "📦 Send product details: Name, Price, Stock\nExample: Wheat Flour, 250, 50")
            return True
        
        if message_lower in ['list', '2']:
            products = self.db.get_products()
            if not products:
                self.send_whatsapp_message(phone, "📋 No products. Use ADD to add.")
            else:
                response = f"📋 *{self.get_shop_name()} Products*\n\n"
                for p in products:
                    response += f"🔖 {p['name']}\n   Code: {p['code']}\n   Price: KES {p['price']}\n   Stock: {p['stock']}\n\n"
                self.send_whatsapp_message(phone, response)
            return True
        
        if message_lower in ['edit', '3']:
            products = self.db.get_products()
            if not products:
                self.send_whatsapp_message(phone, "No products to edit. Use ADD first.")
                return True
            self.sessions[phone]['admin_state'] = 'awaiting_edit_selection'
            response = "✏️ Edit which product?\n\n"
            for idx, p in enumerate(products, 1):
                response += f"{idx}. {p['name']} - KES {p['price']} (Stock: {p['stock']})\n"
            response += "\nSend NUMBER or CODE.\nExample: 1 or MF001"
            self.send_whatsapp_message(phone, response)
            return True
        
        if message_lower in ['stock', '4']:
            products = self.db.get_products()
            if not products:
                self.send_whatsapp_message(phone, "No products. Use ADD first.")
                return True
            self.sessions[phone]['admin_state'] = 'awaiting_stock_selection'
            response = "📊 Update stock for which product?\n\n"
            for idx, p in enumerate(products, 1):
                response += f"{idx}. {p['name']} - Current stock: {p['stock']}\n"
            response += "\nSend NUMBER or CODE."
            self.send_whatsapp_message(phone, response)
            return True
        
        if message_lower in ['delete', '5']:
            products = self.db.get_products()
            if not products:
                self.send_whatsapp_message(phone, "No products to delete.")
                return True
            self.sessions[phone]['admin_state'] = 'awaiting_delete_selection'
            response = "🗑️ Delete which product?\n\n"
            for idx, p in enumerate(products, 1):
                response += f"{idx}. {p['name']} - KES {p['price']}\n"
            response += "\nSend NUMBER or CODE."
            self.send_whatsapp_message(phone, response)
            return True
        
        if message_lower.startswith('shop name'):
            parts = message.split(' ', 2)
            if len(parts) >= 3:
                new_name = parts[2].strip()
                self.db.set_shop_name(new_name)
                self.send_whatsapp_message(phone, f"✅ Shop name changed to: {new_name}")
            else:
                self.sessions[phone]['admin_state'] = 'awaiting_shop_name'
                self.send_whatsapp_message(phone, f"🏪 Current shop name: {self.get_shop_name()}\nSend new shop name.\nExample: Mike's Groceries")
            return True
        
        self.show_admin_menu(phone)
        return True
    
    def process_message(self, phone, message):
        message = message.strip()
        message_lower = message.lower()
        
        # ADMIN LOGIN
        if message_lower.startswith('admin'):
            parts = message.split()
            if len(parts) >= 2 and parts[1] == self.admin_password:
                self.admin_sessions[phone] = datetime.now() + timedelta(hours=1)
                self.send_whatsapp_message(phone, f"🔐 Welcome Admin! Managing {self.get_shop_name()}")
                self.show_admin_menu(phone)
                return
            elif len(parts) >= 2:
                self.send_whatsapp_message(phone, "❌ Invalid password.")
                return
            else:
                self.send_whatsapp_message(phone, "🔐 Send: ADMIN your_password")
                return
        
        # CHECK ADMIN SESSION
        if self.is_admin(phone) and self.handle_admin_command(phone, message):
            return
        
        # CUSTOMER SESSION
        if phone not in self.sessions:
            self.sessions[phone] = {'cart': [], 'state': 'main_menu', 'order_id': None, 'total': 0, 'last_activity': datetime.now()}
            self.send_whatsapp_message(phone, f"👋 Welcome to {self.get_shop_name()}! Send MENU to start.")
            return
        
        session = self.sessions[phone]
        
        if self.is_cart_expired(session) and session['cart']:
            self.clear_cart(phone)
            self.send_whatsapp_message(phone, "🕐 Cart expired due to inactivity. Send MENU to start fresh.")
            return
        
        self.update_activity(phone)
        state = session['state']
        
        # GREETINGS
        if message_lower in ['hi', 'hello', 'hey', 'jambo']:
            self.send_whatsapp_message(phone, f"👋 Hello! Welcome to {self.get_shop_name()}! Send MENU to see products.")
            return
        
        if message_lower == 'menu':
            response = self.show_main_menu(phone)
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
        
        if message_lower in ['clear', 'clear cart']:
            self.clear_cart(phone)
            self.send_whatsapp_message(phone, "🗑️ Cart cleared! Send MENU to shop.")
            return
        
        # ORDER FLOW
        if state == 'main_menu' and message.isdigit():
            response = self.handle_product_selection(phone, int(message))
            self.send_whatsapp_message(phone, response)
            return
        
        if state == 'awaiting_quantity':
            if message.isdigit():
                response = self.add_to_cart(phone, int(message))
                self.send_whatsapp_message(phone, response)
                return
            elif message_lower == 'cancel':
                session['state'] = 'main_menu'
                session['pending_product'] = None
                self.send_whatsapp_message(phone, "❌ Cancelled.")
                return
            else:
                self.send_whatsapp_message(phone, "❌ Send a NUMBER for quantity or CANCEL.")
                return
        
        if state == 'in_cart':
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
                self.clear_cart(phone)
                self.send_whatsapp_message(phone, "🗑️ Cart cleared!")
                return
            else:
                response = self.show_cart(phone)
                self.send_whatsapp_message(phone, response)
                return
        
        if state == 'awaiting_address':
            if message_lower == 'cancel':
                session['state'] = 'main_menu'
                self.send_whatsapp_message(phone, "❌ Checkout cancelled.")
                return
            if len(message) > 5:
                response = self.save_address_and_payment(phone, message)
                self.send_whatsapp_message(phone, response)
                return
            else:
                self.send_whatsapp_message(phone, "📍 Send full delivery address (street, area, city)\nExample: Westlands, Mpaka Road, Nairobi")
                return
        
        if state == 'awaiting_payment':
            if message_lower in ['pay', 'yes']:
                response = self.process_payment(phone)
                self.send_whatsapp_message(phone, response)
                self.clear_cart(phone)
                return
            if message_lower == 'cancel':
                session['state'] = 'main_menu'
                self.send_whatsapp_message(phone, "❌ Payment cancelled.")
                return
            self.send_whatsapp_message(phone, "💳 Reply PAY to complete payment or CANCEL.")
            return
        
        self.send_whatsapp_message(phone, self.show_main_menu(phone))
    
    def show_main_menu(self, phone):
        products = self.db.get_products()
        shop_name = self.get_shop_name()
        
        if not products:
            return f"📋 {shop_name} - No products yet."
        
        session = self.sessions[phone]
        session['state'] = 'main_menu'
        menu = f"🛒 *{shop_name.upper()}* 🛒\n\n"
        for idx, p in enumerate(products, 1):
            menu += f"{idx}. {p['name']} - KES {p['price']}\n"
        menu += "\nSend NUMBER to order\nCART - View cart\nCHECKOUT - Pay\nSTATUS - Your orders\nCLEAR - Clear cart"
        
        if session['cart']:
            total_items = sum(item['quantity'] for item in session['cart'])
            menu += f"\n\n🛒 {total_items} item(s) in cart"
        return menu
    
    def handle_product_selection(self, phone, product_number):
        products = self.db.get_products()
        if product_number < 1 or product_number > len(products):
            return "❌ Invalid number. Send a number from the menu."
        
        selected = products[product_number - 1]
        if selected['stock'] <= 0:
            return f"❌ {selected['name']} is out of stock."
        
        session = self.sessions[phone]
        session['pending_product'] = selected
        session['state'] = 'awaiting_quantity'
        return f"📦 {selected['name']} - KES {selected['price']}\n📊 Stock: {selected['stock']}\n\n🔢 How many? (Send number)\nSend CANCEL to cancel"
    
    def add_to_cart(self, phone, quantity):
        session = self.sessions[phone]
        product = session.get('pending_product')
        if not product:
            session['state'] = 'main_menu'
            return "❌ Session expired. Send MENU to start over."
        
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
        return f"✅ Added {quantity}x {product['name']}\n🛒 Cart: {total_items} item(s) | KES {session['total']} + 100 delivery = KES {grand}\n\nSend CHECKOUT to pay"
    
    def show_cart(self, phone):
        session = self.sessions[phone]
        if not session['cart']:
            session['state'] = 'main_menu'
            return "🛒 Your cart is empty. Send MENU to shop."
        
        cart = "🛒 *YOUR CART*\n\n"
        for item in session['cart']:
            cart += f"• {item['product_name']}: {item['quantity']} x KES {item['price']} = KES {item['subtotal']}\n"
        grand = session['total'] + 100
        cart += f"\n💰 Subtotal: KES {session['total']}\n🚚 Delivery: KES 100\n💵 Total: KES {grand}\n\nSend CHECKOUT to pay"
        return cart
    
    def start_checkout(self, phone):
        session = self.sessions[phone]
        if not session['cart']:
            session['state'] = 'main_menu'
            return "🛒 Your cart is empty. Send MENU to add items."
        
        session['state'] = 'awaiting_address'
        grand_total = session['total'] + 100
        return f"📍 *Delivery Address*\n\nTotal: KES {grand_total}\n\nSend your delivery address.\nExample: Westlands, Mpaka Road, Nairobi\n\nSend CANCEL to cancel"
    
    def save_address_and_payment(self, phone, address):
        session = self.sessions[phone]
        grand_total = session['total'] + 100
        order_id = str(uuid.uuid4())[:8].upper()
        session['order_id'] = order_id
        session['address'] = address
        
        items_text = ", ".join([f"{item['quantity']}x {item['product_name']}" for item in session['cart']])
        self.db.create_order(order_id, phone, items_text, grand_total, address)
        session['state'] = 'awaiting_payment'
        
        return f"✅ *Order #{order_id} created!*\n📍 {address}\n💰 Total: KES {grand_total}\n\n💳 Reply PAY to complete payment"
    
    def process_payment(self, phone):
        session = self.sessions.get(phone)
        if not session or not session.get('order_id'):
            return "❌ No order found."
        
        grand_total = session['total'] + 100
        if not self.paystack_secret_key:
            return self.simulate_payment(phone)
        
        try:
            reference = f"ORDER_{session['order_id']}_{int(datetime.now().timestamp())}"
            clean_phone = phone.replace('+', '').replace('254', '')
            customer_email = f"customer_{clean_phone}@whatsappshop.com"
            
            response = requests.post(
                "https://api.paystack.co/transaction/initialize",
                json={
                    "email": customer_email,
                    "amount": int(grand_total * 100),
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
                    for item in session['cart']:
                        self.db.update_stock(item['product_name'], item['quantity'])
                    self.db.update_order_status(session['order_id'], 'paid')
                    session['state'] = 'order_confirmed'
                    return f"💰 *PAYMENT READY*\n\nOrder: {session['order_id']}\nAmount: KES {grand_total}\n\n🔗 Click to pay: {data['data']['authorization_url']}\n\nPay with M-PESA, Card, or Bank Transfer"
                else:
                    return f"❌ Payment error: {data.get('message')}"
            else:
                return "❌ Payment service error."
        except Exception as e:
            return f"❌ Payment error: {e}"
    
    def simulate_payment(self, phone):
        session = self.sessions.get(phone)
        if not session or not session.get('order_id'):
            return "❌ No order found."
        
        grand_total = session['total'] + 100
        for item in session['cart']:
            self.db.update_stock(item['product_name'], item['quantity'])
        self.db.update_order_status(session['order_id'], 'paid')
        session['state'] = 'order_confirmed'
        return f"💰 *PAYMENT CONFIRMED! (Demo)*\n\nOrder: {session['order_id']}\nAmount: KES {grand_total}\n\n✅ Order confirmed! Delivery in 2 hours."
    
    def show_status(self, phone):
        orders = self.db.get_customer_orders(phone)
        if not orders:
            return "No orders yet. Send MENU to shop."
        
        response = f"📊 *YOUR ORDERS - {self.get_shop_name().upper()}*\n\n"
        for order in orders[:5]:
            status_icon = "✅" if order['status'] == 'paid' else "⏳"
            response += f"{status_icon} {order['order_id']}\n   {order['items']}\n   KES {order['amount']}\n\n"
        return response