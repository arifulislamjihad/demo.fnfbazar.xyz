from .models import Cart, SiteSettings

def cart_items_count(request):
    """
    Navbar e cart icon er count show korar jonno.
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
    Ei function ti SiteSettings theke sob data (Logo, Pixel ID, Test Code)
    ekbare 'site_settings' variable hisebe template e pathay.
    """
    try:
        # Get the first settings object (Latest updated one is better, but .first() is standard)
        settings_obj = SiteSettings.objects.first()
    except:
        settings_obj = None
        
    return {"site_settings": settings_obj}

def facebook_pixel(request):
    """
    [OPTIONAL] Jorpurbo pixel id pathano jodi 'site_settings' fail kore.
    Tobe base.html e amra 'site_settings' use korchi, tai eta redundant.
    Tobuo rekhe dilam jate existing logic break na hoy.
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