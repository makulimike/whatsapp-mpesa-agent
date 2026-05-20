from supabase import create_client
from datetime import datetime
import os

class Database:
    def __init__(self):
        self.supabase = create_client(
            os.getenv('SUPABASE_URL'),
            os.getenv('SUPABASE_KEY')
        )
        print(f"✅ Supabase connected")
    
    def get_products(self):
        """Get all products"""
        result = self.supabase.table('products')\
            .select('*')\
            .order('name')\
            .execute()
        return result.data
    
    def get_product_by_name(self, product_name):
        """Find product by name"""
        try:
            # Try exact match first
            result = self.supabase.table('products')\
                .select('*')\
                .ilike('name', product_name)\
                .execute()
            
            if result.data:
                return result.data[0]
            
            # Try partial match
            result = self.supabase.table('products')\
                .select('*')\
                .ilike('name', f'%{product_name}%')\
                .limit(1)\
                .execute()
            
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error: {e}")
            return None
    
    def add_product(self, name, price, stock):
        """Add new product"""
        try:
            code = name[:3].upper() + str(int(datetime.now().timestamp()))[-4:]
            result = self.supabase.table('products').insert({
                'code': code,
                'name': name,
                'price': price,
                'stock': stock
            }).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error adding product: {e}")
            return None
    
    def update_product(self, product_id, price=None, stock=None):
        """Update product price and/or stock"""
        try:
            update_data = {}
            if price is not None:
                update_data['price'] = price
            if stock is not None:
                update_data['stock'] = stock
            if update_data:
                result = self.supabase.table('products')\
                    .update(update_data)\
                    .eq('id', product_id)\
                    .execute()
                return result.data[0] if result.data else None
            return None
        except Exception as e:
            print(f"Error updating product: {e}")
            return None
    
    def delete_product(self, product_id):
        """Delete product"""
        try:
            result = self.supabase.table('products')\
                .delete()\
                .eq('id', product_id)\
                .execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error deleting product: {e}")
            return None
    
    def create_order(self, order_id, phone, items, amount, address):
        """Create new order"""
        try:
            result = self.supabase.table('orders').insert({
                'order_id': order_id,
                'phone': phone,
                'items': items,
                'amount': amount,
                'address': address,
                'status': 'pending',
                'created_at': datetime.now().isoformat()
            }).execute()
            return True
        except Exception as e:
            print(f"Error creating order: {e}")
            return False
    
    def update_order_status(self, order_id, status):
        """Update order status"""
        try:
            self.supabase.table('orders')\
                .update({'status': status})\
                .eq('order_id', order_id)\
                .execute()
            return True
        except Exception as e:
            print(f"Error updating order: {e}")
            return False
    
    def get_order(self, order_id):
        """Get order by ID"""
        try:
            result = self.supabase.table('orders')\
                .select('*')\
                .eq('order_id', order_id)\
                .execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error getting order: {e}")
            return None
    
    def get_customer_orders(self, phone):
        """Get all orders for a customer"""
        try:
            result = self.supabase.table('orders')\
                .select('*')\
                .eq('phone', phone)\
                .order('created_at', desc=True)\
                .execute()
            return result.data
        except Exception as e:
            print(f"Error getting customer orders: {e}")
            return []
    
    def get_all_orders(self, limit=50):
        """Get all orders for admin"""
        try:
            result = self.supabase.table('orders')\
                .select('*')\
                .order('created_at', desc=True)\
                .limit(limit)\
                .execute()
            return result.data
        except Exception as e:
            print(f"Error getting all orders: {e}")
            return []
    
    def update_stock(self, product_name, quantity):
        """Update product stock after order"""
        try:
            product = self.get_product_by_name(product_name)
            if product:
                new_stock = product['stock'] - quantity
                self.supabase.table('products')\
                    .update({'stock': new_stock})\
                    .eq('id', product['id'])\
                    .execute()
                return True
            return False
        except Exception as e:
            print(f"Error updating stock: {e}")
            return False
    
    def get_shop_name(self):
        """Get shop name from settings"""
        try:
            result = self.supabase.table('settings')\
                .select('value')\
                .eq('key', 'shop_name')\
                .execute()
            if result.data:
                return result.data[0]['value']
            return 'Our Shop'
        except:
            return 'Our Shop'
    
    def set_shop_name(self, name):
        """Set shop name"""
        try:
            self.supabase.table('settings')\
                .update({'value': name, 'updated_at': datetime.now().isoformat()})\
                .eq('key', 'shop_name')\
                .execute()
        except Exception as e:
            print(f"Error setting shop name: {e}")
    
    def close(self):
        """Compatibility method"""
        pass