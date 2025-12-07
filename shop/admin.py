from django.contrib import admin
from .models import Category, Product, Rating, Cart, CartItem, Order, OrderItem


# ===============================
# CATEGORY
# ===============================
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


# ===============================
# PRODUCT
# ===============================
@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "price", "stock", "available", "created")
    list_filter = ("available", "created", "updated", "category")
    list_editable = ("price", "stock", "available")
    prepopulated_fields = {"slug": ("name",)}


# ===============================
# RATING
# ===============================
@admin.register(Rating)
class RatingAdmin(admin.ModelAdmin):
    list_display = ("product", "user", "rating", "created")
    list_filter = ("rating", "created")


# ===============================
# CART + ITEMS
# ===============================
class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at", "updated_at")
    inlines = [CartItemInline]


# ===============================
# ORDER + ITEMS
# ===============================
class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "name",              # new field (single name)
        "phone",
        "delivery_area",
        "delivery_charge",
        "payment_method",
        "status",
        "paid",
        "created",
    )
    list_filter = (
        "status",
        "paid",
        "payment_method",
        "delivery_area",
        "created",
    )
    search_fields = ("id", "name", "phone", "address")
    inlines = [OrderItemInline]


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "product", "quantity", "price")
