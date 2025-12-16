import json
import time
import hashlib
import requests
from django.conf import settings
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives


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
# FACEBOOK CAPI
# ==========================================
def send_facebook_purchase_capi(order, request):
    pixel_id = getattr(settings, "FACEBOOK_PIXEL_ID", "")
    access_token = getattr(settings, "FACEBOOK_CAPI_ACCESS_TOKEN", "")

    if not pixel_id or not access_token:
        return

    client_ip = request.META.get("REMOTE_ADDR")
    client_ua = request.META.get("HTTP_USER_AGENT", "")

    content_ids = [str(item.product.id) for item in order.items.all()]

    user_phone_hash = None
    if getattr(order, "phone", None):
        try:
            user_phone_hash = hashlib.sha256(order.phone.encode("utf-8")).hexdigest()
        except:
            pass

    user_data = {
        "client_ip_address": client_ip,
        "client_user_agent": client_ua,
    }
    if user_phone_hash:
        user_data["ph"] = [user_phone_hash]

    payload = {
        "data": [
            {
                "event_name": "Purchase",
                "event_time": int(time.time()),
                "event_source_url": request.build_absolute_uri(),
                "action_source": "website",
                "user_data": user_data,
                "custom_data": {
                    "currency": "BDT",
                    "value": float(order.get_total_cost()),
                    "content_type": "product",
                    "content_ids": content_ids,
                },
            }
        ]
    }

    url = f"https://graph.facebook.com/v19.0/{pixel_id}/events"
    try:
        requests.post(
            url,
            params={"access_token": access_token},
            json=payload,
            timeout=10,
        )
    except Exception:
        pass


# ==========================================
# FRAUD CHECKER API (OneCodeSoft) - FIXED
# ==========================================
def get_customer_fraud_report(phone):
    """
    Fetch customer delivery history from OneCodeSoft FraudChecker API.
    """
    if not phone:
        return {"error": "No Phone Number"}

    API_KEY = "a0b8c804675841f04b816266"
    URL = "https://fraudchecker.onecodesoft.com/api/fraudchecker"

    # [FIXED] X-Domain হেডার যোগ করা হয়েছে
    # আপনি যখন লাইভ সার্ভারে দেবেন, তখন '127.0.0.1' এর বদলে আপনার আসল ডোমেইন (যেমন: myshop.com) দেবেন।
    headers = {
        "Authorization": API_KEY,
        "X-Domain": "127.0.0.1" 
    }
    
    params = {
        "phone": phone
    }

    try:
        response = requests.get(URL, headers=headers, params=params, timeout=8)
        
        # --- DEBUGGING PRINT ---
        print(f"--- Fraud Check for {phone} ---")
        print(f"Status Code: {response.status_code}")
        # -----------------------

        if response.status_code == 200:
            return response.json()
        
        if response.status_code == 403:
            return {"error": "API Auth Failed (403) - Check Domain Whitelist"}
            
        return {"error": f"API Error: {response.status_code}"}

    except requests.exceptions.RequestException as e:
        return {"error": "Connection Failed"}
    except Exception as e:
        return {"error": "Internal Error"}