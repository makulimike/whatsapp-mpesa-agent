from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
import uvicorn
import os
import logging

from whatsapp_handler import WhatsAppHandler

# Load .env file only if it exists (local development)
if os.path.exists('.env'):
    load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
handler = WhatsAppHandler()

@app.get("/")
def root():
    return {
        "status": "WhatsApp Shop Agent Running",
        "version": "4.0",
        "database": "SQLite",
        "payment": "Paystack",
        "whatsapp_provider": "Flaresend"
    }

@app.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request):
    """Handle incoming WhatsApp messages"""
    try:
        # Log the raw request body
        body = await request.body()
        print(f"\n📥 RAW WEBHOOK BODY: {body}")
        
        payload = await request.json()
        print(f"📥 PARSED PAYLOAD: {payload}")
        
        if payload.get('event') != 'message_received':
            print(f"⏭️ Ignoring event: {payload.get('event')}")
            return JSONResponse({"status": "ignored"})
        
        data = payload.get('data', {})
        from_raw = data.get('from', '')
        message_data = data.get('message', {})
        message_body = message_data.get('conversation', '')
        
        print(f"📱 FROM: {from_raw}, MSG: {message_body}")
        
        if from_raw and message_body:
            from_number = from_raw.replace('@s.whatsapp.net', '')
            from_number = ''.join(filter(str.isdigit, from_number))
            
            print(f"\n📱 Processing message from {from_number}: {message_body}")
            
            # Process message
            handler.process_message(from_number, message_body)
            
            return JSONResponse({"status": "success"})
        
        print(f"⚠️ Could not extract message")
        return JSONResponse({"status": "ignored"})
    
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse({"status": "error", "message": str(e)})

@app.post("/paystack-webhook")
async def paystack_webhook(request: Request):
    try:
        payload = await request.json()
        event = payload.get('event')
        data = payload.get('data')
        
        print(f"💰 Paystack webhook: {event}")
        
        if event == 'charge.success':
            reference = data.get('reference')
            amount = data.get('amount', 0) / 100
            channel = data.get('channel')
            
            for phone, session in handler.sessions.items():
                if session.get('order_id') and f"ORDER_{session['order_id']}" in reference:
                    handler.db.update_order_status(session['order_id'], 'paid')
                    handler.send_whatsapp_message(phone, f"✅ Payment confirmed! Order #{session['order_id']}")
                    break
        
        return JSONResponse({"status": "success"})
    except Exception as e:
        print(f"💰 Error: {e}")
        return JSONResponse({"status": "error"})

@app.get("/admin/orders")
async def admin_orders():
    orders = handler.db.get_all_orders(limit=50)
    return {"total_orders": len(orders), "orders": orders}

@app.get("/admin/products")
async def admin_products():
    products = handler.db.get_products()
    return {"total_products": len(products), "products": products}

@app.get("/health")
@app.head("/health")
async def health_check():
    return {"status": "healthy", "sessions": len(handler.sessions)}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print("\n" + "="*60)
    print("🚀 WhatsApp Shop Agent Running on Render")
    print("="*60)
    print(f"\n✅ Port: {port}")
    print("✅ Webhook ready")
    print("✅ Health check supports GET and HEAD")
    print("\n📝 Send MENU to start")
    print("="*60 + "\n")
    
    uvicorn.run(app, host="0.0.0.0", port=port)