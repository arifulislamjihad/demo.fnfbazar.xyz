import logging
from typing import Tuple, Any

import requests
from django.conf import settings

from .models import Order, SiteSettings

logger = logging.getLogger(__name__)


def get_steadfast_config():
    """
    ডাটাবেস থেকে SiteSettings অবজেক্ট এবং API ক্রেডেনশিয়ালস রিটার্ন করে।
    """
    config = SiteSettings.objects.first()
    if not config:
        return None, None, "Site Settings not found in Admin Panel."
    
    api_key = config.steadfast_api_key
    secret_key = config.steadfast_secret_key
    
    if not api_key or not secret_key:
        return None, None, "Steadfast API Key or Secret Key is missing in Admin -> Site Settings."
        
    return api_key, secret_key, None


def _headers(api_key, secret_key):
    return {
        "Api-Key": api_key,
        "Secret-Key": secret_key,
        "Content-Type": "application/json",
    }


def _base_url():
    # Base URL সাধারণত চেঞ্জ হয় না, তাই এটি settings বা hardcode রাখা যায়
    return getattr(
        settings,
        "STEADFAST_BASE_URL",
        "https://portal.packzy.com/api/v1",
    )


def send_order_to_steadfast(order: Order) -> Tuple[bool, Any]:
    """
    Single order -> Steadfast /create_order
    """
    
    # [NEW] ডাটাবেস থেকে ক্রেডেনশিয়ালস চেক
    api_key, secret_key, error_msg = get_steadfast_config()
    if error_msg:
        return False, error_msg

    # আগেই consignment থাকলে চেক
    if order.steadfast_consignment_id:
        return False, "এই order আগেই Steadfast-এ পাঠানো হয়েছে"

    invoice = f"ORD-{order.id}"
    order_total = float(order.get_total_cost())

    # description
    item_desc_parts = [
        f"{item.product.name} x{item.quantity}" for item in order.items.all()
    ]
    item_description = ", ".join(item_desc_parts)[:240]

    payload = {
        "invoice": invoice,
        "recipient_name": order.name,
        "recipient_phone": order.phone,
        "recipient_address": order.address,
        "cod_amount": order_total,
        "note": f"Area: {order.delivery_area}", 
        "item_description": item_description,
    }

    url = f"{_base_url()}/create_order"

    try:
        # এখানে ডাটাবেস থেকে পাওয়া key গুলো ব্যবহার করা হচ্ছে
        response = requests.post(url, json=payload, headers=_headers(api_key, secret_key), timeout=15)
    except Exception as e:
        logger.exception("Error calling Steadfast create_order")
        return False, f"Request error: {e}"

    try:
        data = response.json()
    except ValueError:
        return False, f"Invalid JSON from Steadfast: {response.text[:200]}"

    if response.status_code != 200 or data.get("status") != 200:
        return False, data

    consignment = data.get("consignment", {})

    order.steadfast_invoice = consignment.get("invoice", invoice)
    order.steadfast_consignment_id = str(consignment.get("consignment_id", "") or "")
    order.steadfast_tracking_code = consignment.get("tracking_code", "") or ""
    order.steadfast_status = consignment.get("status", "") or ""
    order.save(
        update_fields=[
            "steadfast_invoice",
            "steadfast_consignment_id",
            "steadfast_tracking_code",
            "steadfast_status",
        ]
    )

    return True, data


def refresh_steadfast_status(order: Order) -> Tuple[bool, Any]:
    """
    Steadfast থেকে latest delivery_status এনে আপডেট করে।
    """
    
    # [NEW] ক্রেডেনশিয়ালস চেক
    api_key, secret_key, error_msg = get_steadfast_config()
    if error_msg:
        return False, error_msg

    if order.steadfast_consignment_id:
        path = f"/status_by_cid/{order.steadfast_consignment_id}"
    elif order.steadfast_invoice:
        path = f"/status_by_invoice/{order.steadfast_invoice}"
    elif order.steadfast_tracking_code:
        path = f"/status_by_trackingcode/{order.steadfast_tracking_code}"
    else:
        return False, "এই order Steadfast-এ এখনও পাঠানো হয়নি"

    url = f"{_base_url()}{path}"

    try:
        response = requests.get(url, headers=_headers(api_key, secret_key), timeout=15)
    except Exception as e:
        logger.exception("Error calling Steadfast status api")
        return False, f"Request error: {e}"

    try:
        data = response.json()
    except ValueError:
        return False, f"Invalid JSON from Steadfast: {response.text[:200]}"

    if response.status_code != 200 or data.get("status") != 200:
        return False, data

    delivery_status = data.get("delivery_status", "")

    order.steadfast_status = delivery_status
    order.save(update_fields=["steadfast_status"])

    return True, data