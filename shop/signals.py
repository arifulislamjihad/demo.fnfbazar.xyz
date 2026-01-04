from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import VendorWebhook

@receiver(post_save, sender=User)
def create_vendor_webhook(sender, instance, created, **kwargs):
    if created:
        VendorWebhook.objects.create(user=instance)