from django.apps import AppConfig

class ShopConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'shop'

    def ready(self):
        import shop.signals  # সিগন্যাল ফাইলটি কানেক্ট করা হলো