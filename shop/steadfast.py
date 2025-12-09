import logging
from typing import Tuple, Any

import requests
from django.conf import settings

from .models import Order

logger = logging.getLogger(__name__)


def _headers():
    return {
        "Api-Key": settings.STEADFAST_API_KEY,
        "Secret-Key": settings.STEADFAST_SECRET_KEY,
        "Content-Type": "application/json",
    }


def _base_url():
    return getattr(
        settings,
        "STEADFAST_BASE_URL",
        "https://portal.packzy.com/api/v1",
    )


def send_order_to_steadfast(order: Order) -> Tuple[bool, Any]:
    """
    Single order -> Steadfast /create_order

    success হলে:
      - steadfast_invoice
      - steadfast_consignment_id
      - steadfast_tracking_code
      - steadfast_status
    ফিল্ডগুলো আপডেট করে।
    """

    if not settings.STEADFAST_API_KEY or not settings.STEADFAST_SECRET_KEY:
        return False, "STEADFAST_API_KEY / STEADFAST_SECRET_KEY সেট করা নেই"

    # আগেই consignment থাকলে আবার না পাঠাতে চাইলে:
    if order.steadfast_consignment_id:
        return False, "এই order আগেই Steadfast-এ পাঠানো হয়েছে"

    # invoice uniq হওয়া দরকার
    invoice = f"ORD-{order.id}"
    order_total = float(order.get_total_cost())

    # description: "Product A x2, Product B x1"
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
        "note": "",
        "item_description": item_description,
    }

    url = f"{_base_url()}/create_order"

    try:
        response = requests.post(url, json=payload, headers=_headers(), timeout=15)
    except Exception as e:
        logger.exception("Error calling Steadfast create_order")
        return False, f"Request error: {e}"

    try:
        data = response.json()
    except ValueError:
        return False, f"Invalid JSON from Steadfast: {response.text[:200]}"

    # ডকে বলা আছে: success -> status: 200 এবং consignment object ফিরে আসে।
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
    Steadfast থেকে latest delivery_status এনে
    order.steadfast_status আপডেট করে।
    """

    if not settings.STEADFAST_API_KEY or not settings.STEADFAST_SECRET_KEY:
        return False, "STEADFAST_API_KEY / STEADFAST_SECRET_KEY সেট করা নেই"

    # priority: consignment_id -> invoice -> tracking_code
    if order.steadfast_consignment_id:
        path = f"/status_by_cid/{order.steadfast_consignment_id}"
    elif order.steadfast_invoice:
        path = f"/status_by_invoice/{order.steadfast_invoice}"
    elif order.steadfast_tracking_code:
        path = f"/status_by_trackingcode/{order.steadfast_tracking_code}"
    else:
        return False, "এই order Steadfast-এ এখনও পাঠানো হয়নি"

    url = f"{_base_url()}{path}"

    try:
        response = requests.get(url, headers=_headers(), timeout=15)
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
