import json
import time
import hashlib
import requests
from django.conf import settings
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives


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
        'cus_name': f"{order.first_name} {order.last_name}",
        'cus_email': order.email,
        'cus_add1': order.address,
        'cus_city': order.city,
        'cus_postcode': order.postal_code,
        'cus_country': 'Bangladesh',
        'shipping_method': 'NO',
        'product_name': 'Products from our store',
        'product_category': 'General',
        'product_profile': 'general',
    }

    response = requests.post(settings.SSLCOMMERZ_PAYMENT_URL, data=post_data)
    return json.loads(response.text)


def send_order_confirmation_email(order):
    subject = f"Order Confirmation - Order #{order.id}"
    message = render_to_string('shop/email/order_confirmation.html', {'order': order})
    to = order.email
    send_email = EmailMultiAlternatives(subject, '', to=[to])
    send_email.attach_alternative(message, "text/html")
    send_email.send()


# --------------------------
# FACEBOOK CONVERSIONS API (optional, pro-level)
# --------------------------
def send_facebook_purchase_capi(order, request):
    """
    Order confirm হওয়ার পরে Facebook Conversions API দিয়ে
    Purchase event পাঠাতে চাইলে এই ফাংশন ব্যবহার করবে।

    উদাহরণ (payment success view এ):
        from shop.utils import send_facebook_purchase_capi
        send_facebook_purchase_capi(order, request)
    """
    pixel_id = getattr(settings, "FACEBOOK_PIXEL_ID", "")
    access_token = getattr(settings, "FACEBOOK_CAPI_ACCESS_TOKEN", "")

    if not pixel_id or not access_token:
        # Pixel বা CAPI token কনফিগ না থাকলে কিছু করব না
        return

    client_ip = request.META.get("REMOTE_ADDR")
    client_ua = request.META.get("HTTP_USER_AGENT", "")

    content_ids = [str(item.product.id) for item in order.items.all()]

    user_phone_hash = None
    if getattr(order, "phone", None):
        user_phone_hash = hashlib.sha256(order.phone.encode("utf-8")).hexdigest()

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
        # চাইলে এখানে logger দিয়ে error log করতে পারো, আপাতত ignore করছি
        pass
