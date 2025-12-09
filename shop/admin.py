from django.contrib import admin, messages
from django.utils.html import format_html
from django.db import models
from django.forms import CheckboxSelectMultiple

from .models import (
    Category,
    Product,
    Rating,
    Cart,
    CartItem,
    Order,
    OrderItem,
    SiteSettings,
    Attribute,
    AttributeValue,
    ProductVariant,
)
from .steadfast import send_order_to_steadfast, refresh_steadfast_status


# ===============================
# CATEGORY
# ===============================
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


# ===============================
# PRODUCT VARIANTS (inline)
# ===============================
class ProductVariantInline(admin.StackedInline):
    model = ProductVariant
    extra = 1
    fields = ("name", "sku", "price", "stock", "is_active", "attribute_values")
    formfield_overrides = {
        models.ManyToManyField: {"widget": CheckboxSelectMultiple},
    }


# ===============================
# PRODUCT
# ===============================
@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "price", "stock", "available", "created")
    list_filter = ("available", "created", "updated", "category")
    list_editable = ("price", "stock", "available")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ProductVariantInline]


# ===============================
# RATING
# ===============================
@admin.register(Rating)
class RatingAdmin(admin.ModelAdmin):
    list_display = ("product", "user", "rating", "created")
    list_filter = ("rating", "created")


# ===============================
# ATTRIBUTES
# ===============================
@admin.register(Attribute)
class AttributeAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "type")
    list_filter = ("type",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(AttributeValue)
class AttributeValueAdmin(admin.ModelAdmin):
    list_display = ("attribute", "value", "color_code")
    list_filter = ("attribute",)
    search_fields = ("value", "attribute__name")


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
        "name",
        "phone",
        "delivery_area",
        "delivery_charge",
        "payment_method",
        "status",
        "paid",
        "steadfast_status",
        "steadfast_tracking_code",
        "created",
    )
    list_filter = (
        "status",
        "paid",
        "payment_method",
        "delivery_area",
        "created",
        "steadfast_status",
    )
    search_fields = (
        "id",
        "name",
        "phone",
        "address",
        "steadfast_tracking_code",
        "steadfast_invoice",
    )
    inlines = [OrderItemInline]

    actions = ["send_to_steadfast_action", "update_steadfast_status_action"]

    @admin.action(description="Send selected orders to Steadfast")
    def send_to_steadfast_action(self, request, queryset):
        success_count = 0
        fail_count = 0

        for order in queryset:
            ok, info = send_order_to_steadfast(order)
            if ok:
                success_count += 1
            else:
                fail_count += 1
                messages.error(
                    request,
                    f"Order #{order.id} → Steadfast এ পাঠানো যায়নি: {info}",
                )

        if success_count:
            messages.success(
                request,
                f"{success_count}টি order সফলভাবে Steadfast-এ পাঠানো হয়েছে।",
            )
        if not success_count and not fail_count:
            messages.info(request, "কোনো order নির্বাচন করা হয়নি।")

    @admin.action(description="Update Steadfast delivery status")
    def update_steadfast_status_action(self, request, queryset):
        updated = 0
        for order in queryset:
            ok, info = refresh_steadfast_status(order)
            if ok:
                updated += 1
            else:
                messages.warning(
                    request,
                    f"Order #{order.id} → Steadfast status আপডেট হয়নি: {info}",
                )
        if updated:
            messages.success(
                request,
                f"{updated}টি order-এর Steadfast status রিফ্রেশ করা হয়েছে।",
            )


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "product", "variant", "quantity", "price")


# ===============================
# SITE SETTINGS (Logo in Admin)
# ===============================
@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    list_display = ("site_name", "logo_preview")

    def has_add_permission(self, request):
        """
        Normally শুধু ১টা SiteSettings object থাকবে।
        আগে যদি থাকে, নতুন আরেকটা add করতে দেবে না।
        """
        if SiteSettings.objects.exists():
            return False
        return super().has_add_permission(request)

    def logo_preview(self, obj):
        if obj.logo:
            return format_html('<img src="{}" style="height:40px;">', obj.logo.url)
        return "No logo"

    logo_preview.short_description = "Logo"
