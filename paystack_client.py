from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from twilio.twiml.messaging_response import MessagingResponse
from dotenv import load_dotenv
import uvicorn
import os
import logging

from whatsapp_handler import WhatsAppHandler

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

app = FastAPI()
handler = WhatsAppHandler()

@app.get("/")
def root():
    return {
        "status": "WhatsApp Shop Agent Running",
        "version": "2.0",
        "database": "SQLite",
        "payments": "Paystack"
    }

@app.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request):
    """Handle incoming WhatsApp messages"""
    try:
        form_data = await request.form()
        
        from_number = form_data.get('From', '').replace('whatsapp:', '')
        message_body = form_data.get('Body', '').strip()
        
        logger.info(f"📱 Message from {from_number}: {message_body}")
        
        # Check if this is a payment reference confirmation
        if from_number in handler.pending_orders and message_body.startswith('PAY_'):
            response_text = handler.confirm_paystack_payment(from_number, message_body)
        # Check for payment intent
        elif from_number in handler.pending_orders and message_body.lower() == 'pay':
            response_text = handler.initiate_paystack_payment(from_number)
        # Special handling for address (not a command)
        elif from_number in handler.pending_orders and message_body.lower() not in ['yes', 'pay', 'menu', 'status', 'track', 'cancel']:
            response_text = handler.process_address(from_number, message_body)
        else:
            response_text = handler.process_message(from_number, message_body)
        
        resp = MessagingResponse()
        resp.message(response_text)
        
        return PlainTextResponse(str(resp), media_type="application/xml")
    
    except Exception as e:
        logger.error(f"Error in webhook: {e}")
        resp = MessagingResponse()
        resp.message("❌ An error occurred. Please try again.")
        return PlainTextResponse(str(resp), media_type="application/xml")

@app.post("/paystack-webhook")
async def paystack_webhook(request: Request):
    """Handle Paystack webhook events (automatic payment confirmation)"""
    try:
        payload = await request.json()
        
        # Verify webhook signature (optional but recommended)
        signature = request.headers.get('x-paystack-signature')
        
        event = payload.get('event')
        data = payload.get('data')
        
        logger.info(f"🔔 Paystack webhook: {event}")
        
        if event == 'charge.success':
            reference = data.get('reference')
            amount = data.get('amount', 0) / 100  # Convert from kobo/cents
            channel = data.get('channel')
            paid_at = data.get('paid_at')
            
            # Find and update order
            order_id = reference.replace('ORDER_', '').split('_')[0]
            
            # Find order by reference or order_id
            for phone, order in handler.pending_orders.items():
                if order.get('paystack_reference') == reference:
                    # Update order status in database
                    handler.db.update_order_status(order['order_id'], 'paid')
                    
                    # Update stock
                    product = order['product']
                    new_stock = product['stock'] - order['quantity']
                    handler.db.conn.execute(
                        'UPDATE products SET stock = ? WHERE id = ?',
                        (new_stock, product['id'])
                    )
                    handler.db.conn.commit()
                    
                    # Get customer to send confirmation
                    receipt_message = (
                        f"✅ *PAYMENT CONFIRMED!*\n\n"
                        f"Order: {order['order_id']}\n"
                        f"Amount: KES {amount}\n"
                        f"Paid via: {channel.upper()}\n\n"
                        f"🚚 We'll deliver your order within 2 hours.\n"
                        f"Track: `track {order['order_id']}`"
                    )
                    
                    # In production, send this WhatsApp message via Twilio
                    logger.info(f"✅ Payment confirmed for order {order['order_id']}")
                    
                    # Clean up
                    del handler.pending_orders[phone]
                    
                    break
        
        return {"status": "success"}
        
    except Exception as e:
        logger.error(f"Error in paystack webhook: {e}")
        return {"status": "error"}

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🚀 WhatsApp Shop Agent with Paystack Running!")
    print("="*60)
    print("\n✅ Features:")
    print("   • Product catalog")
    print("   • Order management")
    print("   • Paystack payment integration")
    print("   • Automatic webhook confirmation")
    print("   • Order tracking")
    print("\n📝 Commands:")
    print("   • MENU - View products")
    print("   • 2 rice - Place order")
    print("   • Address - Provide delivery location")
    print("   • PAY - Pay with Paystack")
    print("\n🔗 Webhook URL for Paystack:")
    print(f"   https://your-domain.com/paystack-webhook")
    print("\n" + "="*60 + "\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)