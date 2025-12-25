import json
import hashlib
import requests
from django.conf import settings
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone

# ==========================================
# SSLCOMMERZ PAYMENT
# ==========================================
def generate_sslcommerz_payment(order, request):
    """Generate SSLCommerz payment URL"""
    post_data = {
        'store_id': settings.SSLCOMMERZ_STORE_ID,
        'store_passwd': settings.SSLCOMMERZ_STORE_PASSWORD,
        'total_amount': float(order.get_total_cost()),
        'currency': 'BDT',
        'tran_id': str(order.id),
        'success_url': request.build_absolute_uri(f'/payment/success/{order.id}/'),
        'fail_url': request.build_absolute_uri(f'/payment/fail/{order.id}/'),
        'cancel_url': request.build_absolute_uri(f'/payment/cancel/{order.id}/'),
        'cus_name': f"{order.name}",
        'cus_email': getattr(order, 'email', 'customer@example.com'),
        'cus_add1': order.address,
        'cus_city': 'Dhaka',
        'cus_postcode': '1200',
        'cus_country': 'Bangladesh',
        'shipping_method': 'NO',
        'product_name': 'Products from our store',
        'product_category': 'General',
        'product_profile': 'general',
    }

    try:
        response = requests.post(settings.SSLCOMMERZ_PAYMENT_URL, data=post_data)
        return json.loads(response.text)
    except Exception as e:
        return {'status': 'FAILED', 'failedreason': str(e)}


# ==========================================
# EMAIL CONFIRMATION
# ==========================================
def send_order_confirmation_email(order):
    if not hasattr(order, 'email') or not order.email:
        return
        
    subject = f"Order Confirmation - Order #{order.id}"
    message = render_to_string('shop/email/order_confirmation.html', {'order': order})
    to = order.email
    send_email = EmailMultiAlternatives(subject, '', to=[to])
    send_email.attach_alternative(message, "text/html")
    send_email.send()


# ==========================================
# FACEBOOK CAPI (CENTRALIZED WITH DEBUGGING)
# ==========================================
def send_facebook_purchase_event(order):
    """
    Robust Facebook CAPI Function with Debugging Prints
    """
    # Import inside function to avoid circular imports with models
    from .models import SiteSettings
    
    print(f"\n--- [DEBUG] Starting FB Event for Order #{order.id} ---")

    config = SiteSettings.objects.first()
    if not config or not config.facebook_pixel_id or not config.facebook_access_token:
        print("--- [DEBUG] Error: FB Config Missing in SiteSettings ---")
        return False, "FB Config Missing"

    # 1. Phone Number Normalization & Hashing
    phone = str(order.phone).strip()
    if phone.startswith('0'):
        phone = '88' + phone
    elif not phone.startswith('88'):
        phone = '88' + phone 
    
    try:
        phone_hash = hashlib.sha256(phone.encode('utf-8')).hexdigest()
    except:
        phone_hash = ""

    # 2. Advanced Matching Data
    user_data = {
        "ph": [phone_hash],
        "external_id": [str(order.id)]
    }

    try:
        country_hash = hashlib.sha256("bd".encode('utf-8')).hexdigest()
        user_data["country"] = [country_hash]
    except:
        pass

    if order.fbp: user_data["fbp"] = order.fbp
    if order.fbc: user_data["fbc"] = order.fbc
    if order.ip_address: user_data["client_ip_address"] = order.ip_address
    if order.user_agent: user_data["client_user_agent"] = order.user_agent

    # 3. Event Data Construction
    event_data = {
        "event_name": "Purchase",
        "event_time": int(timezone.now().timestamp()),
        "action_source": "website",
        "user_data": user_data,
        "custom_data": {
            "currency": "BDT",
            "value": float(order.get_total_cost()),
            "order_id": str(order.id),
            "content_ids": [str(item.product.id) for item in order.items.all()],
            "content_type": "product",
            "num_items": order.items.count()
        }
    }

    payload = {"data": [event_data], "access_token": config.facebook_access_token}
    
    # Test Code Logic (For testing in Events Manager)
    if config.facebook_test_event_code:
        test_code = config.facebook_test_event_code.strip()
        payload["test_event_code"] = test_code
        print(f"--- [DEBUG] Using Test Code: {test_code} ---")

    # 4. Send Request
    url = f"https://graph.facebook.com/v19.0/{config.facebook_pixel_id}/events"
    
    try:
        print(f"--- [DEBUG] Sending Request to Facebook API... ---")
        response = requests.post(url, json=payload, timeout=10)
        
        # Print Response Details
        print(f"--- [DEBUG] FB Response Code: {response.status_code} ---")
        print(f"--- [DEBUG] FB Response Body: {response.text} ---")

        if response.status_code == 200:
            return True, "Event Sent"
        else:
            error_msg = response.json().get("error", {}).get("message", "Unknown Error")
            return False, error_msg
            
    except Exception as e:
        print(f"--- [DEBUG] EXCEPTION: {str(e)} ---")
        return False, str(e)


# ==========================================
# FRAUD CHECKER API
# ==========================================
def get_customer_fraud_report(phone):
    if not phone:
        return {"error": "No Phone Number"}

    API_KEY = "a0b8c804675841f04b816266"
    URL = "https://fraudchecker.onecodesoft.com/api/fraudchecker"

    headers = {
        "Authorization": API_KEY,
        "X-Domain": "127.0.0.1" 
    }
    
    params = {
        "phone": phone
    }

    try:
        response = requests.get(URL, headers=headers, params=params, timeout=8)
        
        if response.status_code == 200:
            return response.json()
        
        if response.status_code == 403:
            return {"error": "API Auth Failed (403)"}
            
        return {"error": f"API Error: {response.status_code}"}

    except requests.exceptions.RequestException as e:
        return {"error": "Connection Failed"}
    except Exception as e:
        return {"error": "Internal Error"}