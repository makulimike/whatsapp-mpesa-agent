import re
import uuid
import requests
import os
from datetime import datetime
from database import Database
from flaresend_client import FlaresendClient

class WhatsAppHandler:
    def __init__(self):
        self.db = Database()
        self.sessions = {}
        self.paystack_secret_key = os.getenv('PAYSTACK_SECRET_KEY', '')
        self.flaresend = FlaresendClient()
        print(f"✅ WhatsApp Shop Agent Ready")
    
    def send_whatsapp_message(self, to_number: str, message: str):
        """Send message"""
        return self.flaresend.send_message(to_number, message)
    
    def process_message(self, phone, message):
        """Process message - Always friendly"""
        message = message.strip()
        message_lower = message.lower()
        
        # Initialize session if new
        if phone not in self.sessions:
            self.sessions[phone] = {
                'cart': [],
                'state': 'main_menu',
                'order_id': None,
                'total': 0
            }
        
        session = self.sessions[phone]
        state = session['state']
        
        # ============ GREETINGS & FRIENDLY RESPONSES ============
        if message_lower in ['hi', 'hello', 'hey', 'hola', 'jambo', 'sasa', 'hi there', 'good morning', 'good afternoon', 'good evening', 'yo', 'hallo']:
            response = f"👋 *Hello!* Welcome to our shop! 😊\n\n{self.show_main_menu(phone)}"
            self.send_whatsapp_message(phone, response)
            return
        
        if message_lower in ['thank you', 'thanks', 'asante', 'thx', 'thank']:
            response = "🙏 *You're welcome!* Happy to help. Anything else you'd like? Send *MENU* to see our products."
            self.send_whatsapp_message(phone, response)
            return
        
        if message_lower in ['bye', 'goodbye', 'kwaheri', 'see you later']:
            response = "👋 *Goodbye!* Thank you for visiting our shop. Come back anytime! Send *MENU* whenever you're ready to shop."
            self.send_whatsapp_message(phone, response)
            return
        
        if message_lower in ['help', 'support', '?']:
            response = "🆘 *Need help?*\n\n"
            response += "Here's what you can do:\n"
            response += "• Send *MENU* to see all products\n"
            response += "• Send *CART* to view your cart\n"
            response += "• Send *CHECKOUT* to complete order\n"
            response += "• Send *STATUS* to see your orders\n"
            response += "• Send *CLEAR* to clear cart\n\n"
            response += "Just send the number of the product you want to order!"
            self.send_whatsapp_message(phone, response)
            return
        
        # ============ MAIN MENU ============
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
            
            if message_lower == 'clear':
                session['cart'] = []
                session['total'] = 0
                self.send_whatsapp_message(phone, "🗑️ Your cart has been cleared. Send *MENU* to start shopping.")
                return
            
            # Friendly fallback for unknown messages
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
                    self.send_whatsapp_message(phone, "❌ Please enter a valid quantity (1 or more). Try again.")
                    return
            elif message_lower == 'cancel':
                session['state'] = 'main_menu'
                session['pending_product'] = None
                self.send_whatsapp_message(phone, "❌ Order cancelled. Send *MENU* to continue shopping.")
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
                self.send_whatsapp_message(phone, "🗑️ Your cart has been cleared. Send *MENU* to start shopping.")
                return
            elif message_lower == 'add':
                session['state'] = 'main_menu'
                response = self.show_main_menu(phone)
                self.send_whatsapp_message(phone, response)
                return
            else:
                response = self.show_cart(phone)
                self.send_whatsapp_message(phone, response)
                return
        
        # ============ AWAITING ADDRESS ============
        elif state == 'awaiting_address':
            if message_lower == 'cancel':
                session['state'] = 'main_menu'
                self.send_whatsapp_message(phone, "❌ Checkout cancelled. Send *MENU* to continue shopping.")
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
                self.send_whatsapp_message(phone, "❌ Payment cancelled. Send *MENU* to continue shopping.")
                return
            else:
                self.send_whatsapp_message(phone, "💳 Reply *PAY* to complete your payment or *CANCEL* to cancel.")
                return
        
        # ============ ORDER CONFIRMED ============
        elif state == 'order_confirmed':
            if message_lower == 'menu':
                session['state'] = 'main_menu'
                response = self.show_main_menu(phone)
                self.send_whatsapp_message(phone, response)
                return
            elif message_lower == 'status':
                response = self.show_status(phone)
                self.send_whatsapp_message(phone, response)
                return
            elif message_lower == 'track':
                orders = self.db.get_customer_orders(phone)
                if orders:
                    latest = orders[0]
                    response = self.track_order(phone, latest['order_id'])
                    self.send_whatsapp_message(phone, response)
                else:
                    self.send_whatsapp_message(phone, "No orders found. Send *MENU* to shop.")
                return
            else:
                self.send_whatsapp_message(phone, "✅ Your order is confirmed! Send *MENU* to shop more, *STATUS* to check orders.")
                return
        
        # Default fallback
        response = self.show_main_menu(phone)
        self.send_whatsapp_message(phone, response)
    
    def show_main_menu(self, phone):
        """Show friendly menu"""
        products = self.db.get_products()
        if not products:
            return "📋 No products available. Please check back later."
        
        self.sessions[phone]['state'] = 'main_menu'
        
        menu = "🛒 *WELCOME TO OUR SHOP* 🛒\n\n"
        menu += "*Here are our products:*\n\n"
        
        for idx, p in enumerate(products, 1):
            stock_status = "✅" if p['stock'] > 0 else "❌"
            menu += f"{idx}. *{p['name']}* - KES {p['stock']}\n\n"
        
        menu += "─" * 30 + "\n\n"
        menu += "📝 *How to order:*\n"
        menu += "• Send the *NUMBER* of the product you want\n"
        menu += "• Then send the *QUANTITY*\n"
        menu += "• Add multiple items to your cart\n\n"
        menu += "*Commands:*\n"
        menu += "• `CART` - View your cart\n"
        menu += "• `CHECKOUT` - Complete order\n"
        menu += "• `STATUS` - See your orders\n"
        menu += "• `CLEAR` - Clear cart\n"
        menu += "• `HELP` - Show help\n\n"
        menu += "💬 *Send a number to start shopping!*"
        
        session = self.sessions[phone]
        if session['cart']:
            total_items = sum(item['quantity'] for item in session['cart'])
            menu += f"\n\n🛒 *You have {total_items} item(s) in your cart*\nSend *CART* to view or *CHECKOUT* to pay"
        
        return menu
    
    def handle_product_selection(self, phone, product_number):
        """Select product"""
        products = self.db.get_products()
        
        if product_number < 1 or product_number > len(products):
            return "❌ Invalid selection. Please send a number from the menu."
        
        selected = products[product_number - 1]
        
        if selected['stock'] <= 0:
            return f"❌ Sorry, {selected['name']} is currently out of stock. Please choose another product."
        
        self.sessions[phone]['pending_product'] = selected
        self.sessions[phone]['state'] = 'awaiting_quantity'
        
        return f"📦 *{selected['name']}*\n💰 Price: KES {selected['price']}\n📊 In stock: {selected['stock']}\n\n🔢 *How many would you like?* (Send a number, e.g., 2)\n\nSend *CANCEL* to go back."
    
    def add_to_cart(self, phone, quantity):
        """Add to cart"""
        session = self.sessions[phone]
        product = session.get('pending_product')
        
        if not product:
            session['state'] = 'main_menu'
            return "❌ Session expired. Please send *MENU* to start over."
        
        if quantity < 1:
            return "❌ Quantity must be at least 1. Please try again."
        
        if product['stock'] < quantity:
            return f"❌ Sorry, only {product['stock']} units of {product['name']} available. Please enter a smaller quantity."
        
        # Add to cart
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
        
        return f"✅ *Added {quantity}x {product['name']} to your cart!*\n\n🛒 *Cart summary:* {total_items} item(s) | Subtotal: KES {session['total']}\n🚚 Delivery: KES 100\n💰 Grand total: KES {grand}\n\nWhat would you like to do?\n• Send *MENU* to add more items\n• Send *CART* to view cart\n• Send *CHECKOUT* to pay"
    
    def show_cart(self, phone):
        """Show cart"""
        session = self.sessions[phone]
        
        if not session['cart']:
            session['state'] = 'main_menu'
            return "🛒 *Your cart is empty*\n\nSend *MENU* to start shopping!"
        
        cart = "🛒 *YOUR SHOPPING CART*\n\n"
        for i, item in enumerate(session['cart'], 1):
            cart += f"{i}. *{item['product_name']}*\n"
            cart += f"   Quantity: {item['quantity']} x KES {item['price']} = KES {item['subtotal']}\n\n"
        
        cart += "─" * 30 + "\n"
        cart += f"💰 *Subtotal:* KES {session['total']}\n"
        cart += f"🚚 *Delivery fee:* KES 100\n"
        cart += f"💵 *Grand Total:* KES {session['total'] + 100}\n\n"
        cart += "📝 *What's next?*\n"
        cart += "• Send *MENU* to add more items\n"
        cart += "• Send *CHECKOUT* to complete order\n"
        cart += "• Send *CLEAR* to empty cart"
        
        return cart
    
    def start_checkout(self, phone):
        """Start checkout"""
        session = self.sessions[phone]
        
        if not session['cart']:
            session['state'] = 'main_menu'
            return "🛒 Your cart is empty. Send *MENU* to add items first."
        
        session['state'] = 'awaiting_address'
        grand_total = session['total'] + 100
        
        return f"📍 *DELIVERY ADDRESS REQUIRED*\n\n📦 Items in cart: {len(session['cart'])}\n💰 Total amount: KES {grand_total}\n\n🏠 *Please send your delivery address:*\nExample: Westlands, Mpaka Road, Nairobi, Landmark: Near Westgate\n\nSend *CANCEL* to cancel checkout"
    
    def save_address_and_payment(self, phone, address):
        """Save address"""
        session = self.sessions[phone]
        grand_total = session['total'] + 100
        
        order_id = str(uuid.uuid4())[:8].upper()
        session['order_id'] = order_id
        session['address'] = address
        
        # Save order
        items_text = ", ".join([f"{item['quantity']}x {item['product_name']}" for item in session['cart']])
        self.db.create_order(order_id, phone, items_text, grand_total, address)
        
        session['state'] = 'awaiting_payment'
        
        return f"✅ *ORDER #{order_id} SAVED!*\n\n📍 Delivery: {address}\n💰 Total: KES {grand_total}\n\n💳 *PAYMENT OPTIONS*\n• M-PESA (STK Push)\n• Credit/Debit Card\n• Bank Transfer\n\nReply *PAY* to complete your payment\nReply *CANCEL* to cancel order"
    
    def process_payment(self, phone):
        """Process payment"""
        session = self.sessions.get(phone)
        
        if not session or not session.get('order_id'):
            return "❌ No order found. Send *MENU* to start over."
        
        grand_total = session['total'] + 100
        
        # Check if Paystack is configured
        if not self.paystack_secret_key or self.paystack_secret_key == 'sk_live_your_key_here':
            return self.simulate_payment(phone)
        
        try:
            self.send_whatsapp_message(phone, "⏳ *Processing your payment...* Please wait.")
            
            reference = f"ORDER_{session['order_id']}_{int(datetime.now().timestamp())}"
            amount_in_cents = int(grand_total * 100)
            clean_phone = phone.replace('+', '').replace('254', '')
            customer_email = f"customer_{clean_phone}@whatsappshop.com"
            
            paystack_url = "https://api.paystack.co/transaction/initialize"
            headers = {
                "Authorization": f"Bearer {self.paystack_secret_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "email": customer_email,
                "amount": amount_in_cents,
                "currency": "KES",
                "reference": reference,
                "channels": ["mobile_money", "card"],
                "callback_url": os.getenv('PAYSTACK_CALLBACK_URL', ''),
                "metadata": {
                    "order_id": session['order_id'],
                    "phone": phone
                }
            }
            
            response = requests.post(paystack_url, json=payload, headers=headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('status'):
                    # Update stock
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
                    
                    return f"💰 *PAYMENT READY*\n\n📦 Order: {session['order_id']}\n💵 Amount: KES {grand_total}\n\n📱 *M-PESA:* You'll receive an STK push\n💳 *Card/Bank:* {payment_link}\n\n✅ After payment, order will be confirmed.\nSend *STATUS* to check order."
                else:
                    return f"❌ Payment error: {data.get('message')}\nPlease try again."
            else:
                return "❌ Payment service error. Please try again."
        except Exception as e:
            print(f"Payment error: {e}")
            return "❌ Payment error. Please try again."
    
    def simulate_payment(self, phone):
        """Simulate payment for testing"""
        session = self.sessions.get(phone)
        
        if not session or not session.get('order_id'):
            return "❌ No order found. Send *MENU* to start over."
        
        grand_total = session['total'] + 100
        
        # Update stock
        conn = self.db.get_connection()
        for item in session['cart']:
            product = self.db.get_product_by_name(item['product_name'])
            if product:
                new_stock = product['stock'] - item['quantity']
                conn.execute('UPDATE products SET stock = ? WHERE id = ?', (new_stock, product['id']))
                conn.commit()
        
        self.db.update_order_status(session['order_id'], 'paid')
        session['state'] = 'order_confirmed'
        
        return f"💰 *PAYMENT CONFIRMED!* (Demo Mode)\n\n📦 Order: {session['order_id']}\n💵 Amount: KES {grand_total}\n📍 Address: {session.get('address', 'N/A')}\n\n✅ Your order has been confirmed!\n🚚 We'll deliver within 2 hours.\n\nSend *STATUS* to check order, *MENU* to shop more."
    
    def track_order(self, phone, order_id):
        """Track order"""
        order = self.db.get_order(order_id)
        if not order:
            return f"❌ Order {order_id} not found."
        
        if order['phone'] != phone:
            return "❌ You don't have permission to track this order."
        
        status_map = {'pending': '⏳ Pending Payment', 'paid': '✅ Paid - Preparing for delivery', 'delivered': '🎉 Delivered!'}
        
        return f"🚚 *ORDER {order_id}*\n\nItems: {order['items']}\nAmount: KES {order['amount']}\nAddress: {order['address']}\nStatus: {status_map.get(order['status'], order['status'])}"
    
    def show_status(self, phone):
        """Show order history"""
        orders = self.db.get_customer_orders(phone)
        if not orders:
            return "📋 You have no orders yet. Send *MENU* to start shopping!"
        
        response = "📊 *YOUR ORDER HISTORY*\n\n"
        for order in orders[:5]:
            status_icon = "✅" if order['status'] == 'paid' else "⏳"
            response += f"{status_icon} *{order['order_id']}* - {order['items']} - KES {order['amount']}\n"
        return response