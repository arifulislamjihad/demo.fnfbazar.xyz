from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import VendorWebhook, Order, SiteSettings
from .utils import send_facebook_purchase_event

# 1. Vendor Webhook
@receiver(post_save, sender=User)
def create_vendor_webhook(sender, instance, created, **kwargs):
    if created:
        VendorWebhook.objects.create(user=instance)

# 2. FACEBOOK PURCHASE TRIGGER (MANUAL MODE)
@receiver(post_save, sender=Order)
def facebook_purchase_trigger(sender, instance, created, **kwargs):
    """
    Logic:
    - If Mode is 'Manual' AND Status is 'Confirmed'/'Shipped'/'Delivered'
    - Send Purchase Event to Facebook.
    """
    # created=True means new order. Views.py handles Lead/Purchase there.
    # We only care about updates (Admin changing status).
    if created:
        return

    try:
        config = SiteSettings.objects.first()
        if not config:
            return

        # Check if mode is MANUAL
        if config.facebook_pixel_mode == 'manual':
            # Check if status is a "Purchased" state
            if instance.status in ['confirmed', 'shipped', 'delivered']:
                print(f"🚀 [SIGNAL] Order #{instance.id} updated to {instance.status}. Sending FB Purchase Event...")
                
                # utils.py now has logic to send event_id for deduplication
                success, response = send_facebook_purchase_event(instance)
                
                if success:
                    print("✅ [SIGNAL] Event Sent Successfully!")
                else:
                    print(f"❌ [SIGNAL] Failed: {response}")

    except Exception as e:
        print(f"❌ [SIGNAL ERROR] {e}")