import requests

BASE = "http://localhost:8000"

def send_message(message, phone="254702973163"):
    """Test the Flaresend webhook format"""
    response = requests.post(
        f"{BASE}/webhook/whatsapp",
        json={
            "recipients": [phone],
            "type": "text",
            "text": message
        }
    )
    if response.status_code == 200:
        return response.json()
    else:
        return f"Error: {response.status_code} - {response.text}"

print("="*60)
print("TESTING WHATSAPP SHOP AGENT (with Flaresend & Paystack)")
print("="*60)

# Test 1: Menu
print("\n📋 1. Sending 'MENU':")
result = send_message("MENU")
print(result if result else "No response (check if server is running)")

# Test 2: Order
print("\n🛒 2. Sending '2 rice':")
result = send_message("2 rice")
print(result if result else "No response")

# Test 3: Address
print("\n📍 3. Sending address:")
result = send_message("Westlands, Mpaka Road, Nairobi")
print(result if result else "No response")

# Test 4: Initiate payment
print("\n💰 4. Sending 'PAY':")
result = send_message("PAY")
print(result if result else "No response")

# Test 5: Track order status
print("\n🔍 5. Sending 'status':")
result = send_message("status")
print(result if result else "No response")

print("\n" + "="*60)
print("✅ Test complete!")
print("="*60)