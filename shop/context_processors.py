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
    
    # Guest cart count (Session based)
    guest_cart = request.session.get("guest_cart", {})
    count = sum(guest_cart.values())
    return {"cart_items_count": count}


def site_settings(request):
    """
    সব template এ site_settings নামে object পাঠায়,
    যাতে logo এবং site_name সহজে ব্যবহার করা যায়।
    """
    try:
        settings_obj = SiteSettings.objects.first()
    except:
        settings_obj = None
    return {"site_settings": settings_obj}


def facebook_pixel(request):
    """
    ডাটাবেস থেকে FACEBOOK_PIXEL_ID এবং TEST_EVENT_CODE নিয়ে সব টেমপ্লেটে পাঠায়।
    """
    config = SiteSettings.objects.first()
    pixel_id = ""
    test_code = ""
    
    if config:
        if config.facebook_pixel_id:
            pixel_id = config.facebook_pixel_id.strip()
        if config.facebook_test_event_code:
            test_code = config.facebook_test_event_code.strip()
        
    return {
        "FACEBOOK_PIXEL_ID": pixel_id,
        "FACEBOOK_TEST_EVENT_CODE": test_code
    }