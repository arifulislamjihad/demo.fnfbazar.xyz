import json

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib import messages
from django.db.models import Q
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required

from .models import (
    Category,
    Product,
    Cart,
    CartItem,
    Rating,
    Order,
    OrderItem,
    ProductVariant,
)
from .forms import RegistrationForm, RatingForm, CheckoutForm
from .utils import generate_sslcommerz_payment, send_order_confirmation_email


# ============================================================
# USER AUTH
# ============================================================
def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)

        if user:
            login(request, user)
            return redirect("shop:profile")
        else:
            messages.error(request, "Invalid username or password")

    return render(request, "shop/login.html")


def register_view(request):
    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Registration Successful!")
            return redirect("shop:profile")
    else:
        form = RegistrationForm()

    return render(request, "shop/register.html", {"form": form})


def logout_view(request):
    logout(request)
    return redirect("shop:login")


# ============================================================
# HOME + PRODUCT LIST
# ============================================================
def home(request):
    featured_products = Product.objects.filter(available=True).order_by("-created")[:8]
    categories = Category.objects.all()

    return render(
        request,
        "shop/home.html",
        {"featured_products": featured_products, "categories": categories},
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
        products = products.filter(
            Q(name__icontains=q)
            | Q(description__icontains=q)
            | Q(category__name__icontains=q)
        )

    return render(
        request,
        "shop/product_list.html",
        {
            "category": category,
            "categories": categories,
            "products": products,
        },
    )


# ============================================================
# PRODUCT DETAIL (FIXED LOGIC FOR ATTRIBUTES)
# ============================================================
def product_detail(request, slug):
    product = get_object_or_404(Product, slug=slug, available=True)
    
    related_products = Product.objects.filter(
        category=product.category, available=True
    ).exclude(id=product.id)[:4]

    # User rating
    user_rating = None
    if request.user.is_authenticated:
        try:
            user_rating = Rating.objects.get(product=product, user=request.user)
        except Rating.DoesNotExist:
            user_rating = None

    rating_form = RatingForm(instance=user_rating)

    # ---------------------------------------------------------
    # VARIANT ATTRIBUTE LOGIC
    # ---------------------------------------------------------
    
    # ১. সব অ্যাক্টিভ ভেরিয়েন্ট বের করি এবং তাদের অ্যাট্রিবিউটগুলো লোড করি
    variants = product.variants.filter(is_active=True).prefetch_related('attribute_values__attribute')

    # Frontend-এ দেখানোর জন্য ডিকশনারি
    # Structure: { attr_id: { 'attribute': AttributeObj, 'values': [ValueObj, ValueObj] } }
    variant_attributes = {}
    
    # JavaScript এর জন্য ম্যাপিং (Price/Stock update করার জন্য)
    variant_map = {}

    if product.has_variants:
        for variant in variants:
            # JS Map এর জন্য Key তৈরি (যেমন: "color_id:red_id|size_id:xl_id")
            temp_key = []
            
            # এই ভেরিয়েন্টের সব অ্যাট্রিবিউট ভ্যালু চেক করি
            for val in variant.attribute_values.all():
                attr = val.attribute
                
                # --- Template Data সাজানো ---
                if attr.id not in variant_attributes:
                    variant_attributes[attr.id] = {
                        'attribute': attr,
                        'values': []
                    }
                
                # ডুপ্লিকেট ভ্যালু আটকাতে চেক করি (যেমন Red দুইবার না আসে)
                existing_ids = [v.id for v in variant_attributes[attr.id]['values']]
                if val.id not in existing_ids:
                    variant_attributes[attr.id]['values'].append(val)
                
                # --- JS Key তৈরি ---
                temp_key.append(f"{attr.id}:{val.id}")

            # Key গুলো sort করি যাতে উল্টাপাল্টা না হয়
            temp_key.sort()
            final_key = "|".join(temp_key)

            # JS Map এ তথ্য রাখি
            variant_map[final_key] = {
                'id': variant.id,
                'price': float(variant.get_price()),
                'stock': variant.stock
            }

    context = {
        "product": product,
        "related_products": related_products,
        "user_rating": user_rating,
        "rating_form": rating_form,
        "variant_attributes": variant_attributes, # এই variable টি টেম্পলেটে লুপ হবে
        "variant_map_json": json.dumps(variant_map),
    }

    return render(request, "shop/product_detail.html", context)


# ============================================================
# CART SYSTEM
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
            if self.variant:
                return self.variant.get_price()
            return self.product.price

        @property
        def get_cost(self):
            return self.get_unit_price() * self.quantity

    class GuestCart:
        def __init__(self, d):
            items = []
            for key, qty in d.items():
                try:
                    if ":" in key:
                        pid, vid = key.split(":", 1)
                        product = Product.objects.get(id=int(pid))
                        variant = ProductVariant.objects.get(
                            id=int(vid), product=product
                        )
                    else:
                        product = Product.objects.get(id=int(key))
                        variant = None
                    items.append(GuestItem(product, variant, qty))
                except (Product.DoesNotExist, ProductVariant.DoesNotExist, ValueError):
                    continue
            self.items = items

        def get_total_price(self):
            return sum(i.get_cost for i in self.items)

        def get_total_items(self):
            return sum(i.quantity for i in self.items)

    return GuestCart(cart_data)


def cart_detail(request):
    return render(request, "shop/cart.html", {"cart": _get_cart(request)})


def cart_add(request, product_id):
    product = get_object_or_404(Product, id=product_id, available=True)
    quantity = int(request.POST.get("quantity", 1) or 1)
    if quantity < 1:
        quantity = 1

    variant_id = request.POST.get("variant_id")
    variant = None
    if variant_id:
        variant = get_object_or_404(
            ProductVariant,
            id=variant_id,
            product=product,
            is_active=True,
        )

    if request.user.is_authenticated:
        cart, _ = Cart.objects.get_or_create(user=request.user)
        item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            variant=variant,
        )
        if created:
            item.quantity = quantity
        else:
            item.quantity += quantity
        item.save()
    else:
        cart = request.session.get("guest_cart", {})
        if variant:
            key = f"{product_id}:{variant.id}"
        else:
            key = str(product_id)
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
        keys_to_remove = [
            k for k in list(cart.keys()) if k.split(":")[0] == str(product_id)
        ]
        for k in keys_to_remove:
            cart.pop(k, None)
        request.session["guest_cart"] = cart

    return redirect("shop:cart_detail")


def cart_update(request, product_id):
    qty = int(request.POST.get("quantity", 1) or 1)

    if request.user.is_authenticated:
        cart = Cart.objects.get(user=request.user)
        item = CartItem.objects.get(cart=cart, product_id=product_id)
        if qty <= 0:
            item.delete()
        else:
            item.quantity = qty
            item.save()
    else:
        cart = request.session.get("guest_cart", {})
        matching_keys = [
            k for k in list(cart.keys()) if k.split(":")[0] == str(product_id)
        ]
        if qty <= 0:
            for k in matching_keys:
                cart.pop(k, None)
        else:
            if matching_keys:
                first = matching_keys[0]
                cart[first] = qty
                for k in matching_keys[1:]:
                    cart.pop(k, None)
        request.session["guest_cart"] = cart

    return redirect("shop:cart_detail")


# ============================================================
# CHECKOUT
# ============================================================
@csrf_exempt
def checkout(request):
    buy_now_id = request.GET.get("buy_now_id")
    buy_now_variant_id = request.GET.get("variant_id")

    if buy_now_id:
        request.session["buy_now_id"] = str(buy_now_id)
        if buy_now_variant_id:
            request.session["buy_now_variant_id"] = str(buy_now_variant_id)

    buy_now_id = request.session.get("buy_now_id")
    buy_now_variant_id = request.session.get("buy_now_variant_id")
    product_for_buy_now = None
    variant_for_buy_now = None

    if buy_now_id:
        product_for_buy_now = get_object_or_404(Product, id=buy_now_id, available=True)

        if buy_now_variant_id:
            try:
                variant_for_buy_now = ProductVariant.objects.get(
                    id=buy_now_variant_id,
                    product=product_for_buy_now,
                    is_active=True,
                )
            except ProductVariant.DoesNotExist:
                variant_for_buy_now = None

        class BuyNowItem:
            def __init__(self, product, variant=None):
                self.product = product
                self.variant = variant
                self.quantity = 1

            def get_unit_price(self):
                if self.variant:
                    return self.variant.get_price()
                return self.product.price

            @property
            def get_cost(self):
                return self.get_unit_price() * self.quantity

        class BuyNowCart:
            def __init__(self, product, variant=None):
                self.items = [BuyNowItem(product, variant)]

            def get_total_price(self):
                return self.items[0].get_cost

            def get_total_items(self):
                return 1

        cart = BuyNowCart(product_for_buy_now, variant_for_buy_now)
        is_buy_now = True
    else:
        cart = _get_cart(request)
        is_buy_now = False

        if not getattr(cart, "items", None):
            messages.warning(request, "Your cart is empty.")
            return redirect("shop:cart_detail")

    subtotal = cart.get_total_price()
    delivery_preview = 70
    total_preview = subtotal + delivery_preview

    if request.method == "POST":
        form = CheckoutForm(request.POST)

        if form.is_valid():
            order = form.save(commit=False)

            if order.delivery_area == "dhaka":
                order.delivery_charge = 70
            else:
                order.delivery_charge = 120

            if request.user.is_authenticated:
                order.user = request.user

            order.save()

            if is_buy_now:
                if variant_for_buy_now:
                    unit_price = variant_for_buy_now.get_price()
                else:
                    unit_price = product_for_buy_now.price

                OrderItem.objects.create(
                    order=order,
                    product=product_for_buy_now,
                    variant=variant_for_buy_now,
                    quantity=1,
                    price=unit_price,
                )
                request.session.pop("buy_now_id", None)
                request.session.pop("buy_now_variant_id", None)
            else:
                for item in cart.items:
                    unit_price = (
                        item.get_unit_price()
                        if hasattr(item, "get_unit_price")
                        else item.product.price
                    )
                    OrderItem.objects.create(
                        order=order,
                        product=item.product,
                        variant=getattr(item, "variant", None),
                        quantity=item.quantity,
                        price=unit_price,
                    )

                if request.user.is_authenticated:
                    CartItem.objects.filter(cart__user=request.user).delete()
                else:
                    request.session["guest_cart"] = {}

            if order.payment_method == "cod":
                return render(request, "shop/payment_success.html", {"order": order})

            request.session["order_id"] = order.id
            return redirect("shop:payment_process")

    else:
        form = CheckoutForm()

    return render(
        request,
        "shop/checkout.html",
        {
            "cart": cart,
            "form": form,
            "subtotal": subtotal,
            "delivery_preview": delivery_preview,
            "total_preview": total_preview,
            "is_buy_now": is_buy_now,
        },
    )


# ============================================================
# PAYMENT
# ============================================================
def payment_process(request):
    order_id = request.session.get("order_id")
    order = get_object_or_404(Order, id=order_id)

    payment = generate_sslcommerz_payment(order, request)

    if payment["status"] == "SUCCESS":
        return redirect(payment["GatewayPageURL"])

    messages.error(request, "Payment gateway error.")
    return redirect("shop:checkout")


@csrf_exempt
def payment_success(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    order.paid = True
    order.status = "processing"
    order.transaction_id = order_id
    order.save()

    send_order_confirmation_email(order)
    return render(request, "shop/payment_success.html", {"order": order})


@csrf_exempt
def payment_fail(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    order.status = "canceled"
    order.save()
    return redirect("shop:checkout")


@csrf_exempt
def payment_cancel(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    order.status = "canceled"
    order.save()
    return redirect("shop:cart_detail")


# ============================================================
# PROFILE + RATING + 404
# ============================================================
def profile(request):
    if not request.user.is_authenticated:
        return redirect("shop:login")

    orders = Order.objects.filter(user=request.user).order_by("-created")
    return render(request, "shop/profile.html", {"orders": orders})


@login_required(login_url="/login/")
def rate_product(request, product_id):
    product = get_object_or_404(Product, id=product_id)

    purchased = OrderItem.objects.filter(
        order__user=request.user, order__paid=True, product=product
    ).exists()

    if not purchased:
        messages.error(request, "You can only review products you have purchased.")
        return redirect("shop:product_detail", slug=product.slug)

    try:
        rating = Rating.objects.get(product=product, user=request.user)
    except Rating.DoesNotExist:
        rating = None

    form = RatingForm(request.POST or None, instance=rating)

    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.product = product
        obj.user = request.user
        obj.save()
        messages.success(request, "Your review has been submitted.")
        return redirect("shop:product_detail", slug=product.slug)

    return render(request, "shop/rate_product.html", {"form": form, "product": product})


def custom_404_view(request, exception):
    return render(request, "shop/404.html", status=404)