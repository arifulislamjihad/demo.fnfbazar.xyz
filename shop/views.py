import json
import re 
from datetime import timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import Q
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.http import JsonResponse 

from .models import (
    Category, Product, Cart, CartItem, Rating, Order, OrderItem,
    ProductVariant, DeliveryOption, SiteSettings
)
from .forms import RegistrationForm, RatingForm
from .utils import generate_sslcommerz_payment, send_order_confirmation_email, send_facebook_purchase_event, send_facebook_lead_event

# ============================================================
# AUTH VIEWS
# ============================================================
def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect("shop:profile")
        else: messages.error(request, "Invalid username or password")
    return render(request, "shop/login.html")

def register_view(request):
    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Registration Successful!")
            return redirect("shop:profile")
    else: form = RegistrationForm()
    return render(request, "shop/register.html", {"form": form})

def logout_view(request):
    logout(request)
    return redirect("shop:login")

# ============================================================
# HOME & PRODUCT VIEWS
# ============================================================
def home(request):
    flash_sale_products = Product.objects.filter(is_flash_sale=True, available=True).order_by("-updated")[:12]
    featured_categories = Category.objects.filter(is_featured=True)[:14]
    if not featured_categories: featured_categories = Category.objects.all()[:14]
    just_for_you = Product.objects.filter(available=True).order_by("-created")[:30]

    if flash_sale_products.exists():
        featured_products = flash_sale_products
    else:
        featured_products = just_for_you[:12]

    return render(
        request,
        "shop/home.html",
        {
            "featured_products": featured_products,
            "flash_sale_products": flash_sale_products,
            "categories": featured_categories,
            "just_for_you": just_for_you,
        },
    )

def product_list(request, category_slug=None):
    category = None
    categories = Category.objects.all()
    products = Product.objects.filter(available=True)
    if category_slug:
        category = get_object_or_404(Category, slug=category_slug)
        products = products.filter(category=category)
    if request.GET.get("search"):
        q = request.GET.get("search")
        products = products.filter(Q(name__icontains=q)|Q(description__icontains=q)|Q(category__name__icontains=q))
    return render(request, "shop/product_list.html", {"category": category, "categories": categories, "products": products})

def product_detail(request, slug):
    product = get_object_or_404(Product, slug=slug, available=True)
    related_products = Product.objects.filter(category=product.category, available=True).exclude(id=product.id)[:4]
    
    user_rating = None
    if request.user.is_authenticated:
        try: user_rating = Rating.objects.get(product=product, user=request.user)
        except Rating.DoesNotExist: user_rating = None
    rating_form = RatingForm(instance=user_rating)
    
    # Variant Logic (Fixed for Error 500)
    variants = product.variants.filter(is_active=True).prefetch_related('attribute_values__attribute')
    variant_attributes = {}
    variant_map = {}
    
    if product.has_variants:
        for variant in variants:
            # Safer Image Handling
            variant_image_url = ""
            try:
                if variant.image:
                    variant_image_url = variant.image.url
            except ValueError:
                variant_image_url = "" # Handle missing file case

            temp_key = []
            for val in variant.attribute_values.all():
                attr = val.attribute
                if attr.id not in variant_attributes:
                    variant_attributes[attr.id] = {'attribute': attr, 'values': []}
                
                existing_ids = [v.id for v in variant_attributes[attr.id]['values']]
                if val.id not in existing_ids:
                    if variant_image_url: val.image_src = variant_image_url
                    variant_attributes[attr.id]['values'].append(val)
                
                temp_key.append(f"{attr.id}:{val.id}")
            
            temp_key.sort()
            final_key = "|".join(temp_key)
            
            variant_map[final_key] = {
                'id': variant.id, 
                'price': float(variant.get_price()), 
                'stock': variant.stock, 
                'image': variant_image_url
            }

    context = {
        "product": product, 
        "related_products": related_products, 
        "user_rating": user_rating, 
        "rating_form": rating_form, 
        "variant_attributes": variant_attributes, 
        "variant_map_json": json.dumps(variant_map)
    }
    return render(request, "shop/product_detail.html", context)

# ============================================================
# CART LOGIC
# ============================================================
def _get_cart(request):
    if request.user.is_authenticated:
        cart, _ = Cart.objects.get_or_create(user=request.user)
        return cart
    cart_data = request.session.get("guest_cart", {})
    class GuestItem:
        def __init__(self, product, variant, qty):
            self.product = product
            self.variant = variant
            self.quantity = qty
        def get_unit_price(self):
            if self.variant: return self.variant.get_price()
            return self.product.price
        @property
        def get_cost(self): return self.get_unit_price() * self.quantity
    class GuestCart:
        def __init__(self, d):
            items = []
            for key, qty in d.items():
                try:
                    if ":" in key:
                        pid, vid = key.split(":", 1)
                        product = Product.objects.get(id=int(pid))
                        variant = ProductVariant.objects.get(id=int(vid), product=product)
                    else:
                        product = Product.objects.get(id=int(key))
                        variant = None
                    items.append(GuestItem(product, variant, qty))
                except: continue
            self.items = items
        def get_total_price(self): return sum(i.get_cost for i in self.items)
        def get_total_items(self): return sum(i.quantity for i in self.items)
    return GuestCart(cart_data)

def cart_detail(request): return render(request, "shop/cart.html", {"cart": _get_cart(request)})

def cart_add(request, product_id):
    product = get_object_or_404(Product, id=product_id, available=True)
    quantity = int(request.POST.get("quantity", 1) or 1)
    if quantity < 1: quantity = 1
    variant_id = request.POST.get("variant_id")
    variant = None
    if variant_id: variant = get_object_or_404(ProductVariant, id=variant_id, product=product, is_active=True)
    
    if request.user.is_authenticated:
        cart, _ = Cart.objects.get_or_create(user=request.user)
        item, created = CartItem.objects.get_or_create(cart=cart, product=product, variant=variant)
        if created: item.quantity = quantity
        else: item.quantity += quantity
        item.save()
    else:
        cart = request.session.get("guest_cart", {})
        key = f"{product_id}:{variant.id}" if variant else str(product_id)
        cart[key] = cart.get(key, 0) + quantity
        request.session["guest_cart"] = cart
    messages.success(request, f"{product.name} added to cart.")
    return redirect("shop:product_detail", slug=product.slug)

def cart_remove(request, product_id):
    if request.user.is_authenticated:
        cart = Cart.objects.get(user=request.user)
        CartItem.objects.filter(cart=cart, product_id=product_id).delete()
    else:
        cart = request.session.get("guest_cart", {})
        keys_to_remove = [k for k in list(cart.keys()) if k.split(":")[0] == str(product_id)]
        for k in keys_to_remove: cart.pop(k, None)
        request.session["guest_cart"] = cart
    return redirect("shop:cart_detail")

def cart_update(request, product_id):
    qty = int(request.POST.get("quantity", 1) or 1)
    if request.user.is_authenticated:
        cart = Cart.objects.get(user=request.user)
        item = CartItem.objects.get(cart=cart, product_id=product_id)
        if qty <= 0: item.delete()
        else:
            item.quantity = qty
            item.save()
    else:
        cart = request.session.get("guest_cart", {})
        matching_keys = [k for k in list(cart.keys()) if k.split(":")[0] == str(product_id)]
        if qty <= 0:
            for k in matching_keys: cart.pop(k, None)
        else:
            if matching_keys:
                first = matching_keys[0]
                cart[first] = qty
                for k in matching_keys[1:]: cart.pop(k, None)
        request.session["guest_cart"] = cart
    return redirect("shop:cart_detail")

# ============================================================
# CHECKOUT & ORDER
# ============================================================
@csrf_exempt
def checkout(request):
    buy_now_id = request.GET.get("buy_now_id")
    buy_now_variant_id = request.GET.get("variant_id")
    if buy_now_id:
        request.session["buy_now_id"] = str(buy_now_id)
        if buy_now_variant_id: request.session["buy_now_variant_id"] = str(buy_now_variant_id)
    
    buy_now_id = request.session.get("buy_now_id")
    buy_now_variant_id = request.session.get("buy_now_variant_id")
    product_for_buy_now = None
    variant_for_buy_now = None

    class BuyNowItem:
        def __init__(self, product, variant=None):
            self.product = product
            self.variant = variant
            self.quantity = 1
        def get_unit_price(self): return self.variant.get_price() if self.variant else self.product.price
        @property
        def get_cost(self): return self.get_unit_price() * self.quantity

    class BuyNowCart:
        def __init__(self, product, variant=None): self.items = [BuyNowItem(product, variant)]
        def get_total_price(self): return self.items[0].get_cost
        def get_total_items(self): return 1

    if buy_now_id:
        product_for_buy_now = get_object_or_404(Product, id=buy_now_id, available=True)
        if buy_now_variant_id:
            try: variant_for_buy_now = ProductVariant.objects.get(id=buy_now_variant_id, product=product_for_buy_now, is_active=True)
            except ProductVariant.DoesNotExist: variant_for_buy_now = None
        cart = BuyNowCart(product_for_buy_now, variant_for_buy_now)
        is_buy_now = True
    else:
        cart = _get_cart(request)
        is_buy_now = False
        if not getattr(cart, "items", None):
            messages.warning(request, "Your cart is empty.")
            return redirect("shop:cart_detail")

    subtotal = cart.get_total_price()
    delivery_options = DeliveryOption.objects.filter(is_active=True)
    delivery_preview = delivery_options.first().price if delivery_options.exists() else 0
    total_preview = subtotal + delivery_preview

    if request.method == "POST":
        name = request.POST.get("name")
        phone = request.POST.get("phone", "").strip() 
        address = request.POST.get("address")
        delivery_option_id = request.POST.get("delivery_area")
        payment_method = request.POST.get("payment_method")
        
        phone_pattern = r'^01[3-9]\d{8}$'
        if not re.match(phone_pattern, phone):
            messages.error(request, "Invalid phone number.")
            return render(request, "shop/checkout.html", {"cart": cart, "subtotal": subtotal, "delivery_options": delivery_options, "delivery_preview": delivery_preview, "total_preview": total_preview, "is_buy_now": is_buy_now})

        one_hour_ago = timezone.now() - timedelta(minutes=60)
        if Order.objects.filter(phone=phone, created__gte=one_hour_ago).exists():
            messages.error(request, "Please wait before placing another order.")
            return render(request, "shop/checkout.html", {"cart": cart, "subtotal": subtotal, "delivery_options": delivery_options, "delivery_preview": delivery_preview, "total_preview": total_preview, "is_buy_now": is_buy_now})

        try:
            selected_option = DeliveryOption.objects.get(id=delivery_option_id)
            d_area_name = selected_option.location
            d_charge = selected_option.price
        except:
            d_area_name = "Unknown"
            d_charge = 0

        # Create Order
        order = Order.objects.create(
            user=request.user if request.user.is_authenticated else None,
            name=name,
            phone=phone,
            address=address,
            delivery_area=d_area_name,
            delivery_charge=d_charge,
            payment_method=payment_method,
            status="pending"
        )

        order.fbp = request.COOKIES.get('_fbp')
        order.fbc = request.COOKIES.get('_fbc')
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for: order.ip_address = x_forwarded_for.split(',')[0]
        else: order.ip_address = request.META.get('REMOTE_ADDR')
        order.user_agent = request.META.get('HTTP_USER_AGENT', '')
        order.save() 

        if is_buy_now:
            unit_price = variant_for_buy_now.get_price() if variant_for_buy_now else product_for_buy_now.price
            OrderItem.objects.create(order=order, product=product_for_buy_now, variant=variant_for_buy_now, quantity=1, price=unit_price)
            request.session.pop("buy_now_id", None)
            request.session.pop("buy_now_variant_id", None)
        else:
            for item in cart.items:
                unit_price = item.get_unit_price() if hasattr(item, "get_unit_price") else item.product.price
                OrderItem.objects.create(order=order, product=item.product, variant=getattr(item, "variant", None), quantity=item.quantity, price=unit_price)
            if request.user.is_authenticated: CartItem.objects.filter(cart__user=request.user).delete()
            else: request.session["guest_cart"] = {}

        # Server-side Event
        config = SiteSettings.objects.first()
        if config:
            if config.facebook_pixel_mode == 'automatic':
                send_facebook_purchase_event(order)
            elif config.facebook_pixel_mode == 'manual':
                send_facebook_lead_event(order)

        if order.payment_method == "cod":
            return render(request, "shop/payment_success.html", {"order": order, "config": config})

        request.session["order_id"] = order.id
        return redirect("shop:payment_process")

    return render(request, "shop/checkout.html", {"cart": cart, "subtotal": subtotal, "delivery_options": delivery_options, "delivery_preview": delivery_preview, "total_preview": total_preview, "is_buy_now": is_buy_now})

def payment_process(request): return redirect("shop:checkout") 

def payment_success(request, order_id): 
    order = get_object_or_404(Order, id=order_id)
    config = SiteSettings.objects.first()
    return render(request, "shop/payment_success.html", {"order": order, "config": config}) 

def payment_fail(request, order_id): return redirect("shop:checkout") 
def payment_cancel(request, order_id): return redirect("shop:cart_detail") 
def profile(request): return render(request, "shop/profile.html") 
def rate_product(request, product_id): return redirect("shop:home") 
def custom_404_view(request, exception): return render(request, "shop/404.html")
def steadfast_webhook(request): return JsonResponse({})

@csrf_exempt
def woocommerce_order_webhook(request, user_id):
    if request.method == "POST":
        try:
            try:
                vendor_user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return JsonResponse({'status': 'error', 'message': 'Vendor not found'}, status=404)

            data = json.loads(request.body)
            billing = data.get('billing', {})
            full_name = f"{billing.get('first_name', '')} {billing.get('last_name', '')}".strip()
            if not full_name: full_name = "Guest User"

            order = Order.objects.create(
                vendor=vendor_user,
                name=full_name,
                phone=billing.get('phone', ''),
                address=f"{billing.get('address_1', '')}, {billing.get('city', '')}",
                email=billing.get('email', ''),
                status="pending",
                note=f"WP Order #{data.get('id')}",
                payment_method='cod',
                ip_address=request.META.get('REMOTE_ADDR')
            )

            line_items = data.get('line_items', [])
            for item in line_items:
                product_name = item.get('name')
                quantity = item.get('quantity', 1)
                total = float(item.get('total', 0))
                unit_price = total / quantity if quantity > 0 else 0
                product = Product.objects.filter(name__iexact=product_name).first()
                if product:
                    OrderItem.objects.create(order=order, product=product, quantity=quantity, price=unit_price)

            config = SiteSettings.objects.first()
            if config:
                if config.facebook_pixel_mode == 'automatic':
                    send_facebook_purchase_event(order)
                elif config.facebook_pixel_mode == 'manual':
                    send_facebook_lead_event(order)

            return JsonResponse({'status': 'success', 'order_id': order.id}, status=200)

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

    return JsonResponse({'status': 'invalid method'}, status=405)