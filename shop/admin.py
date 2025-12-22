import hashlib
import requests
import json
from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.db import models
from django.forms import CheckboxSelectMultiple
from django.utils import timezone
from django.utils.timesince import timesince

# [NEW] Dropdown Filter Import
from django_admin_listfilter_dropdown.filters import (
    DropdownFilter,
    ChoiceDropdownFilter,
    RelatedDropdownFilter
)

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
    DeliveryOption,
)
from .steadfast import send_order_to_steadfast, refresh_steadfast_status
from .utils import get_customer_fraud_report


# ============================================================
# FACEBOOK CAPI HELPER FUNCTION
# ============================================================
def send_facebook_purchase_event(order):
    """
    Sends Purchase Event to Facebook Conversion API
    """
    config = SiteSettings.objects.first()
    if not config or not config.facebook_pixel_id or not config.facebook_access_token:
        return False, "FB Pixel ID or Token missing in Site Settings"

    # 1. Phone Number Normalization & Hashing
    phone = order.phone.strip()
    if phone.startswith('0'):
        phone = '88' + phone
    elif not phone.startswith('88'):
        phone = '88' + phone 
    
    try:
        phone_hash = hashlib.sha256(phone.encode('utf-8')).hexdigest()
    except:
        phone_hash = ""

    # 2. Event Data Construction
    event_data = {
        "event_name": "Purchase",
        "event_time": int(timezone.now().timestamp()),
        "action_source": "website",
        "user_data": {
            "ph": [phone_hash],
        },
        "custom_data": {
            "currency": "BDT",
            "value": float(order.get_total_cost()),
            "order_id": str(order.id),
            "content_ids": [str(item.product.id) for item in order.items.all()],
            "content_type": "product",
            "num_items": order.items.count()
        }
    }

    # 3. Final Payload Construction
    payload = {
        "data": [event_data],
        "access_token": config.facebook_access_token
    }

    if config.facebook_test_event_code:
        payload["test_event_code"] = config.facebook_test_event_code.strip()

    # 4. Send Request
    url = f"https://graph.facebook.com/v19.0/{config.facebook_pixel_id}/events"
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        res_data = response.json()
        if response.status_code == 200:
            return True, "Event Sent"
        else:
            error_msg = res_data.get("error", {}).get("message", "Unknown Error")
            return False, error_msg
    except Exception as e:
        return False, str(e)


# ============================================================
# ADMIN MODELS CONFIG
# ============================================================

@admin.register(DeliveryOption)
class DeliveryOptionAdmin(admin.ModelAdmin):
    list_display = ("location", "price", "is_active")
    list_editable = ("price", "is_active")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0
    fields = ("attribute_values", "price", "stock", "sku", "is_active")
    formfield_overrides = {
        models.ManyToManyField: {'widget': CheckboxSelectMultiple},
    }
    classes = ['collapse']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "price", "stock", "available", "created")
    # [NEW] Dropdown Filters
    list_filter = (
        ("available", DropdownFilter),
        ("category", RelatedDropdownFilter),
    )
    list_editable = ("price", "stock", "available")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ProductVariantInline]
    save_on_top = True


@admin.register(Rating)
class RatingAdmin(admin.ModelAdmin):
    list_display = ("product", "user", "rating", "created")
    list_filter = (("rating", DropdownFilter),)


@admin.register(Attribute)
class AttributeAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "type")
    list_filter = ("type",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(AttributeValue)
class AttributeValueAdmin(admin.ModelAdmin):
    list_display = ("attribute", "value", "color_code")
    list_filter = (("attribute", RelatedDropdownFilter),)
    search_fields = ("value", "attribute__name")
    ordering = ('attribute', 'value')


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at", "updated_at")
    inlines = [CartItemInline]


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product', 'variant', 'quantity', 'price')
    can_delete = False


# ============================================================
# PROFESSIONAL ORDER ADMIN (FILTERS ON TOP)
# ============================================================
@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    # [NEW] Date Hierarchy shows breadcrumbs at the top (Year > Month > Day)
    date_hierarchy = 'created'

    list_display = (
        "order_id_display",
        "customer_info_display",  
        "order_items_display",    
        "amount_info_display",    
        "payment_status_display", 
        "status_label",           
        "steadfast_info", 
        "created_at_display",
    )
    
    # [NEW] Filters (Will be moved to top via CSS below)
    list_filter = (
        ('status', ChoiceDropdownFilter),
        ('payment_method', ChoiceDropdownFilter),
        ('steadfast_status', ChoiceDropdownFilter),
        ('paid', DropdownFilter),
    )
    
    search_fields = (
        "id", "name", "phone", "address",
        "steadfast_tracking_code", "steadfast_invoice", "steadfast_consignment_id",
    )
    
    readonly_fields = ("fraud_report_detail",)
    inlines = [OrderItemInline]
    
    actions = [
        "make_confirmed_action",
        "send_to_steadfast_action", 
        "update_steadfast_status_action", 
        "manual_check_fraud_action"
    ]
    
    list_per_page = 20

    # -------------------------------------------------------------
    # [CRITICAL] CSS TO MOVE FILTERS TO TOP & FORCE FULL WIDTH
    # -------------------------------------------------------------
    class Media:
        # We inject CSS directly here to ensure it overrides default admin styles
        pass

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        # This CSS is injected into the admin page HEAD
        custom_css = """
        <style>
            /* 1. HIDE the default right sidebar area */
            #changelist-filter {
                position: relative !important;
                right: auto !important;
                top: auto !important;
                width: 98% !important; /* Full width */
                background: #f8f9fa;
                border: 1px solid #eaeaea;
                margin: 0 0 20px 0 !important;
                padding: 15px !important;
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: 20px;
                border-radius: 5px;
                box-shadow: none !important;
                order: -1; /* Move to top visually */
            }
            
            /* 2. Hide the 'Filter' title */
            #changelist-filter h2 {
                display: none;
            }
            
            /* 3. Make filter list horizontal */
            #changelist-filter ul {
                padding: 0;
                margin: 0;
                display: flex;
                flex-wrap: wrap;
                gap: 15px;
            }
            
            #changelist-filter li {
                list-style: none;
                margin-bottom: 0;
            }
            
            /* 4. Style the dropdowns */
            #changelist-filter select {
                padding: 6px;
                border: 1px solid #ccc;
                border-radius: 4px;
                min-width: 150px;
            }
            
            /* 5. Force the main table to be Full Width */
            #changelist {
                display: flex;
                flex-direction: column;
            }
            
            /* Overriding Django's default margin for sidebar */
            .change-list .filtered .results, 
            .change-list .filtered .paginator, 
            .filtered #toolbar, 
            .filtered div.xfull {
                margin-right: 0 !important;
                width: 100% !important;
            }
            
            div.results {
                width: 100% !important;
            }
        </style>
        """
        extra_context['title'] = mark_safe(f"Orders Management {custom_css}")
        return super().changelist_view(request, extra_context=extra_context)

    # ----------------------------------------------------------------
    # ACTION: Bulk Mark as Confirmed
    # ----------------------------------------------------------------
    @admin.action(description="Mark selected orders as Confirmed")
    def make_confirmed_action(self, request, queryset):
        success_count = 0
        fb_sent_count = 0
        for order in queryset:
            if order.status != 'confirmed':
                order.status = 'confirmed'
                order.save() 
                success_count += 1
                sent, _ = send_facebook_purchase_event(order)
                if sent: fb_sent_count += 1
        
        if success_count > 0:
            messages.success(request, f"{success_count} orders confirmed. ({fb_sent_count} to Facebook)")
        else:
            messages.info(request, "No updates made.")

    def save_model(self, request, obj, form, change):
        if change:
            try:
                old_obj = Order.objects.get(pk=obj.pk)
                if old_obj.status != 'confirmed' and obj.status == 'confirmed':
                    success, msg = send_facebook_purchase_event(obj)
                    if success:
                        messages.success(request, f"FB Event sent for Order #{obj.id}")
                    else:
                        messages.warning(request, f"FB Event failed: {msg}")
            except Order.DoesNotExist:
                pass
        super().save_model(request, obj, form, change)

    # --- UI DISPLAY HELPERS ---
    def order_id_display(self, obj):
        return format_html('<b>#{}</b>', obj.id)
    order_id_display.short_description = "ID"

    def customer_info_display(self, obj):
        badge = self.fraud_check_badge(obj)
        addr = obj.address[:35] + "..." if len(obj.address) > 35 else obj.address
        history_html = ""
        if obj.phone:
            prev = Order.objects.filter(phone=obj.phone).exclude(id=obj.id).order_by('-created')[:2]
            if prev.exists():
                rows = "".join([f'<div style="font-size:9px;">#{p.id} [{p.status}]</div>' for p in prev])
                history_html = f'<div style="margin-top:4px; padding:4px; border:1px solid #ddd; border-radius:4px; background:#fff;"><b>History:</b>{rows}</div>'

        return format_html(
            '<div style="line-height:1.2;"><b>{}</b><br><small>📞 {}</small><br><small>📍 {}</small><br>{}{}</div>',
            obj.name, obj.phone, addr, badge, mark_safe(history_html)
        )
    customer_info_display.short_description = "Customer Details"

    def order_items_display(self, obj):
        items = obj.items.all()
        if not items: return "-"
        li = "".join([f"<li>{i.quantity}x {i.product.name}</li>" for i in items])
        return mark_safe(f'<ul style="margin:0; padding-left:15px; font-size:11px;">{li}</ul>')
    order_items_display.short_description = "Products"

    def amount_info_display(self, obj):
        return format_html('<b>৳{}</b><br><small style="color:#666;">Del: ৳{}</small>', obj.get_total_cost(), obj.delivery_charge)
    amount_info_display.short_description = "Total"

    def payment_status_display(self, obj):
        m = "COD" if obj.payment_method == "cod" else "Online"
        s = '<span style="color:green;">✔ PAID</span>' if obj.paid else '<span style="color:red;">✖ UNPAID</span>'
        return format_html('<b>{}</b><br>{}', m, mark_safe(s))
    payment_status_display.short_description = "Payment"

    def status_label(self, obj):
        colors = {'pending': '#f59e0b', 'confirmed': '#0ea5e9', 'delivered': '#10b981', 'canceled': '#ef4444'}
        c = colors.get(obj.status, '#6b7280')
        return format_html('<span style="background:{}; color:white; padding:2px 6px; border-radius:10px; font-size:10px; font-weight:bold; text-transform:uppercase;">{}</span>', c, obj.status)
    status_label.short_description = "Status"

    def steadfast_info(self, obj):
        if not obj.steadfast_consignment_id: return mark_safe('<small style="color:#999;">Not Sent</small>')
        return format_html('<b>{}</b><br><a href="https://steadfast.com.bd/t/{}" target="_blank" style="font-size:10px; background:#2563eb; color:white; padding:2px 5px; border-radius:3px; text-decoration:none;">Track</a>', obj.steadfast_status, obj.steadfast_tracking_code)
    steadfast_info.short_description = "Courier"

    def created_at_display(self, obj):
        lt = timezone.localtime(obj.created)
        return format_html('<div style="font-size:11px;"><b>{}</b><br>{}<br><small>{} ago</small></div>', lt.strftime("%d %b, %y"), lt.strftime("%I:%M %p"), timesince(lt).split(",")[0])
    created_at_display.short_description = "Date"

    def fraud_check_badge(self, obj):
        if not obj.phone: return ""
        d = obj.fraud_report_data
        if not d: return mark_safe('<span style="color:#999; font-size:10px;">New</span>')
        try:
            total = int(float(d.get("total_parcel", 0)))
            cancel = int(float(d.get("cancel_parcel", 0)))
            rate = (cancel / total) * 100 if total > 0 else 0
            if rate > 30: return mark_safe(f'<span style="color:red; font-weight:bold; font-size:10px;">⚠️ Risky ({int(rate)}%)</span>')
            return mark_safe(f'<span style="color:green; font-weight:bold; font-size:10px;">✅ Safe</span>')
        except: return ""

    def fraud_report_detail(self, obj):
        return "Check list view for summary"
    fraud_report_detail.short_description = "Fraud Report"

    @admin.action(description="Check Fraud Status")
    def manual_check_fraud_action(self, request, queryset):
        for order in queryset:
            data = get_customer_fraud_report(order.phone)
            if data and "total_parcel" in data:
                order.fraud_report_data = data
                order.save(update_fields=['fraud_report_data'])
        messages.success(request, "Fraud status updated.")

    @admin.action(description="Send to Steadfast")
    def send_to_steadfast_action(self, request, queryset):
        for order in queryset:
            send_order_to_steadfast(order)
        messages.success(request, "Orders sent to Steadfast.")

    @admin.action(description="Update Steadfast Status")
    def update_steadfast_status_action(self, request, queryset):
        for order in queryset:
            refresh_steadfast_status(order)
        messages.success(request, "Steadfast statuses updated.")


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "product", "variant", "quantity", "price")


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    list_display = ("site_name", "logo_preview")
    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()
    def logo_preview(self, obj):
        if obj.logo: return format_html('<img src="{}" style="height:40px;">', obj.logo.url)
        return "No logo"