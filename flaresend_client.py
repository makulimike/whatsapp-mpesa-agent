import requests
import os
from dotenv import load_dotenv

load_dotenv()

class FlaresendClient:
    def __init__(self):
        self.api_key = os.getenv('FLARESEND_API_KEY')
        self.api_url = "https://api.flaresend.com/send-message"
        
        # Create persistent session for connection pooling
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        })
        
        # Set timeouts
        self.timeout = 5
        
        if self.api_key:
            print(f"✅ Flaresend ready (connection pool active)")
    
    def send_message(self, to_number: str, message: str):
        """Fast message sending with connection reuse"""
        if not self.api_key:
            return None
        
        try:
            to_number = to_number.replace('whatsapp:', '').replace('+', '')
            to_number = ''.join(filter(str.isdigit, to_number))
            
            # Truncate long messages
            if len(message) > 1600:
                message = message[:1597] + "..."
            
            payload = {
                "recipients": [to_number],
                "type": "text",
                "text": message
            }
            
            # Reuse session
            response = self.session.post(self.api_url, json=payload, timeout=self.timeout)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    return result
                    
        except Exception as e:
            print(f"Send error: {e}")
        
        return None