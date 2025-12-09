from django.conf import settings
from .models import Cart, SiteSettings


def cart_items_count(request):
    """
    Navbar e cart icon er পাশে মোট কতটি item আছে সেটা দেখানোর জন্য।
    """
    if request.user.is_authenticated:
        try:
            cart = Cart.objects.get(user=request.user)
            return {"cart_items_count": cart.get_total_items()}
        except Cart.DoesNotExist:
            return {"cart_items_count": 0}
    return {"cart_items_count": 0}


def site_settings(request):
    """
    সব template এ site_settings নামে object পাঠায়,
    যাতে logo এবং site_name সহজে ব্যবহার করা যায়।
    """
    settings_obj = SiteSettings.objects.first()
    return {"site_settings": settings_obj}


def facebook_pixel(request):
    """
    সব template এ FACEBOOK_PIXEL_ID পাঠানোর জন্য।
    Pixel না থাকলে simply খালি string যাবে।
    """
    pixel_id = getattr(settings, "FACEBOOK_PIXEL_ID", "")
    return {"FACEBOOK_PIXEL_ID": pixel_id}
