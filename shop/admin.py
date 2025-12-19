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
# FACEBOOK CAPI HELPER FUNCTION (FIXED)
# ============================================================
def send_facebook_purchase_event(order):
    """
    Sends Purchase Event to Facebook Conversion API
    """
    config = SiteSettings.objects.first()
    if not config or not config.facebook_pixel_id or not config.facebook_access_token:
        return False, "FB Pixel ID or Token missing in Site Settings"

    # 1. Phone Number Normalization & Hashing (FIXED)
    # ফেইসবুক চায় নম্বরটি যেন 8801... ফরম্যাটে থাকে
    phone = order.phone.strip()
    if phone.startswith('0'):
        phone = '88' + phone
    elif not phone.startswith('88'):
        phone = '88' + phone # Defaulting to BD if no country code
    
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

    # [FIXED] টেস্ট কোডটি এখন মেইন পে-লোডের বাইরে পাঠানো হচ্ছে
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
            # এরর ডিবাগ করার জন্য বিস্তারিত মেসেজ
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
    list_filter = ("available", "created", "updated", "category")
    list_editable = ("price", "stock", "available")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ProductVariantInline]
    save_on_top = True


@admin.register(Rating)
class RatingAdmin(admin.ModelAdmin):
    list_display = ("product", "user", "rating", "created")
    list_filter = ("rating", "created")


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
# PROFESSIONAL ORDER ADMIN
# ============================================================
@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
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
    
    list_filter = (
        "status",
        "paid",
        "payment_method",
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
        "steadfast_consignment_id",
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

    # ----------------------------------------------------------------
    # ACTION: Bulk Mark as Confirmed + Trigger FB Pixel
    # ----------------------------------------------------------------
    @admin.action(description="Mark selected orders as Confirmed")
    def make_confirmed_action(self, request, queryset):
        success_count = 0
        fb_sent_count = 0
        
        for order in queryset:
            # Only process if not already confirmed
            if order.status != 'confirmed':
                order.status = 'confirmed'
                order.save() # Save status to DB
                success_count += 1
                
                # Trigger Facebook Event
                sent, _ = send_facebook_purchase_event(order)
                if sent:
                    fb_sent_count += 1
        
        if success_count > 0:
            messages.success(request, f"{success_count} orders marked as Confirmed. ({fb_sent_count} sent to Facebook)")
        else:
            messages.info(request, "No eligible orders were updated.")

    # ----------------------------------------------------------------
    # SINGLE EDIT: Override Save Model to Trigger FB Pixel
    # ----------------------------------------------------------------
    def save_model(self, request, obj, form, change):
        # Only proceed if editing an existing object
        if change:
            try:
                old_obj = Order.objects.get(pk=obj.pk)
                
                # Logic: If status changed TO 'confirmed' FROM something else
                if old_obj.status != 'confirmed' and obj.status == 'confirmed':
                    success, msg = send_facebook_purchase_event(obj)
                    if success:
                        messages.success(request, f"Facebook 'Purchase' Event sent for Order #{obj.id}")
                    else:
                        messages.warning(request, f"Failed to send FB Event: {msg}")
                        
            except Order.DoesNotExist:
                pass
        
        super().save_model(request, obj, form, change)

    # --- 1. Order ID ---
    def order_id_display(self, obj):
        return format_html('<b>#{}</b>', obj.id)
    order_id_display.short_description = "ID"

    # --- 2. Customer Info (With History) ---
    def customer_info_display(self, obj):
        badge = self.fraud_check_badge(obj)
        addr = obj.address
        if len(addr) > 40:
            addr = addr[:40] + "..."

        history_html = ""
        if obj.phone:
            previous_orders = Order.objects.filter(phone=obj.phone).exclude(id=obj.id).order_by('-created')[:3]
            
            if previous_orders.exists():
                history_rows = ""
                for po in previous_orders:
                    date_str = po.created.strftime("%d %b")
                    s_color = "gray"
                    if po.status == 'delivered': s_color = "green"
                    elif po.status == 'canceled': s_color = "red"
                    elif po.status == 'confirmed': s_color = "blue"
                    
                    products = po.items.all()[:2] 
                    prod_names = ", ".join([p.product.name for p in products])
                    if len(prod_names) > 25: 
                        prod_names = prod_names[:25] + ".."
                    
                    history_rows += f"""
                    <div style="font-size:10px; color:#555; border-bottom:1px solid #eee; padding:3px 0;">
                        <span style="color:#000; font-weight:600;">#{po.id}</span>
                        <span style="color:{s_color}; font-weight:bold; font-size:9px; text-transform:uppercase;">[{po.status}]</span>
                        <br>
                        <span style="color:#333;">🛒 {prod_names}</span>
                        <span style="color:#999; float:right;">{date_str}</span>
                    </div>
                    """
                
                history_html = f"""
                <div style="margin-top:8px; background:#fff; padding:6px; border-radius:4px; border:1px solid #d1d5db; box-shadow: 0 1px 2px rgba(0,0,0,0.05);">
                    <div style="font-size:10px; font-weight:bold; color:#374151; border-bottom:1px solid #e5e7eb; margin-bottom:4px; padding-bottom:2px;">
                        📜 Previous History
                    </div>
                    {history_rows}
                </div>
                """

        return format_html(
            """
            <div style="line-height: 1.4;">
                <div style="font-weight:bold; font-size:13px; color:#333;">{}</div>
                <div style="color:#555; font-size: 12px;">📞 {}</div>
                <div style="color:#777; font-size: 11px;">📍 {}</div>
                <div style="margin-top:4px;">{}</div>
                {}
            </div>
            """,
            obj.name,
            obj.phone,
            addr,
            badge,
            mark_safe(history_html)
        )
    customer_info_display.short_description = "Customer Details"

    # --- 3. Product Summary ---
    def order_items_display(self, obj):
        items = obj.items.all()
        if not items:
            return "-"
        
        html_content = '<ul style="margin: 0; padding-left: 15px; font-size: 12px; color: #444;">'
        for item in items:
            variant_txt = f" ({item.variant})" if item.variant else ""
            html_content += f"<li>{item.quantity}x <b>{item.product.name}</b>{variant_txt}</li>"
        html_content += '</ul>'
        
        return mark_safe(html_content)
    order_items_display.short_description = "Products"

    # --- 4. Amount Info ---
    def amount_info_display(self, obj):
        total = obj.get_total_cost()
        return format_html(
            """
            <div style="font-size:14px; font-weight:bold; color:#108a00;">৳{}</div>
            <div style="font-size:10px; color:#666;">Delivery: ৳{}</div>
            """,
            total,
            obj.delivery_charge
        )
    amount_info_display.short_description = "Total"

    # --- 5. Payment Status ---
    def payment_status_display(self, obj):
        method_map = {'cod': 'COD', 'sslcommerz': 'Online'}
        method = method_map.get(obj.payment_method, obj.payment_method)
        
        if obj.paid:
            status_icon = '<span style="color:green; font-weight:bold;">✔ PAID</span>'
        else:
            status_icon = '<span style="color:red; font-weight:bold;">✖ UNPAID</span>'
            
        return format_html(
            '<div style="font-weight:bold; color:#444;">{}</div><div style="font-size:11px;">{}</div>',
            method,
            mark_safe(status_icon)
        )
    payment_status_display.short_description = "Payment"

    # --- 6. Order Status Label ---
    def status_label(self, obj):
        colors = {
            'pending': '#f59e0b',
            'confirmed': '#0ea5e9', # Sky Blue
            'processing': '#3b82f6',
            'shipped': '#8b5cf6',
            'delivered': '#10b981',
            'canceled': '#ef4444',
        }
        color = colors.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background-color:{}; color:white; padding:3px 8px; border-radius:12px; font-size:11px; font-weight:bold; text-transform:uppercase;">{}</span>',
            color,
            obj.status
        )
    status_label.short_description = "Status"

    # --- 7. Courier Info ---
    def steadfast_info(self, obj):
        if not obj.steadfast_consignment_id:
            return mark_safe('<span style="color:#bbb; font-size:11px;">Not Sent</span>')

        st_color = "#1565c0"
        bg_color = "#e3f2fd"
        if obj.steadfast_status == 'delivered':
            st_color = "#166534"
            bg_color = "#dcfce7"
        elif obj.steadfast_status == 'cancelled':
            st_color = "#991b1b"
            bg_color = "#fee2e2"
            
        status_html = f'<span style="background:{bg_color}; color:{st_color}; padding:2px 6px; border-radius:4px; font-size:10px; font-weight:bold; text-transform:uppercase; border: 1px solid {st_color}40;">{obj.steadfast_status}</span>'
        track_url = f"https://steadfast.com.bd/t/{obj.steadfast_tracking_code}"
        
        return format_html(
            """
            <div style="line-height: 1.5;">
                <div style="margin-bottom:4px;">{}</div>
                <div style="font-size: 11px; color: #333;"><b>CID:</b> {}</div>
                <div style="margin-top:5px;">
                    <a href="{}" target="_blank" style="background:#2563eb; color:white; padding:3px 8px; border-radius:4px; text-decoration:none; font-size:10px; font-weight:bold;">
                       🚀 Live Track
                    </a>
                </div>
            </div>
            """,
            mark_safe(status_html),
            obj.steadfast_consignment_id,
            track_url
        )
    steadfast_info.short_description = "Courier"

    # --- 8. Date & Time ---
    def created_at_display(self, obj):
        local_time = timezone.localtime(obj.created)
        date_str = local_time.strftime("%d %b, %Y")
        time_str = local_time.strftime("%I:%M %p")
        ago_full = timesince(local_time).split(",")[0]
        ago_str = f"{ago_full} ago"
        
        diff = timezone.now() - obj.created
        if diff.days < 1:
            ago_style = "color:#166534; font-weight:bold;"
        else:
            ago_style = "color:#666;"

        return format_html(
            """
            <div style="white-space:nowrap; line-height:1.4;">
                <div style="font-weight:600; color:#333; font-size:12px;">{}</div>
                <div style="font-size:11px; color:#555;">{}</div>
                <div style="font-size:10px; margin-top:2px; {}">{}</div>
            </div>
            """,
            date_str,
            time_str,
            ago_style,
            ago_str
        )
    created_at_display.short_description = "Date & Time"

    # ============================================================
    # FRAUD CHECK LOGIC
    # ============================================================
    def fraud_check_badge(self, obj):
        if not obj.phone: return ""
        
        data = obj.fraud_report_data
        
        if not data:
            if obj.status == 'pending':
                try:
                    api_response = get_customer_fraud_report(obj.phone)
                    if api_response and "total_parcel" in api_response:
                        obj.fraud_report_data = api_response
                        obj.save(update_fields=['fraud_report_data'])
                        data = api_response
                except:
                    pass
        
        if not data or "total_parcel" not in data:
            return mark_safe('<span style="color:#bbb; font-size:10px;">Check Needed</span>')

        try:
            total = int(float(data.get("total_parcel", 0)))
            canceled = int(float(data.get("cancel_parcel", 0)))
            success = int(float(data.get("success_parcel", 0)))
        except:
            return ""

        if total == 0:
            return mark_safe('<span style="color:blue; font-weight:bold; font-size:10px;">New Customer</span>')

        cancel_rate = (canceled / total) * 100 if total > 0 else 0
        success_rate = (success / total) * 100 if total > 0 else 0

        # Popup Logic
        courier_data = data.get("response", {})
        popup_rows = ""
        has_data = False
        for courier_name, info in courier_data.items():
            stats = info.get("data", {}) if isinstance(info, dict) else {}
            if stats:
                c_total = int(float(stats.get('total', 0)))
                c_cancel = int(float(stats.get('cancel', 0)))
                c_success = int(float(stats.get('success', 0)))
                if c_total > 0:
                    has_data = True
                    popup_rows += f"""
                        <tr style="border-bottom: 1px solid #eee;">
                            <td style="padding:4px; text-transform:capitalize; color:#000;">{courier_name}</td>
                            <td style="padding:4px; text-align:center; color:#000;">{c_total}</td>
                            <td style="padding:4px; text-align:center; color:green; font-weight:bold;">{c_success}</td>
                            <td style="padding:4px; text-align:center; color:red; font-weight:bold;">{c_cancel}</td>
                        </tr>
                    """
        if not has_data:
            popup_rows = "<tr><td colspan='4' style='padding:5px; text-align:center;'>No details.</td></tr>"

        if cancel_rate > 30:
            badge = f'<div style="background:#ffebee; color:#c62828; padding:2px 6px; border-radius:10px; border:1px solid #c62828; font-weight:bold; font-size:10px; cursor:pointer; display:inline-block;">⚠️ Risky ({int(cancel_rate)}%)</div>'
        else:
            badge = f'<div style="background:#e8f5e9; color:#2e7d32; padding:2px 6px; border-radius:10px; border:1px solid #2e7d32; font-weight:bold; font-size:10px; cursor:pointer; display:inline-block;">✅ Safe ({int(success_rate)}%)</div>'

        html = f"""
        <style>
            .fraud-wrapper {{ position: relative; display: inline-block; }}
            .fraud-wrapper .fraud-popup {{ 
                visibility: hidden; opacity: 0; position: fixed; 
                top: 50%; left: 50%; transform: translate(-50%, -50%); 
                z-index: 999999; width: 300px; background: #fff; 
                border-radius: 8px; box-shadow: 0 0 0 100vw rgba(0,0,0,0.5), 0 10px 30px rgba(0,0,0,0.5); 
                border: 1px solid #ccc; transition: 0.2s; 
            }}
            .fraud-wrapper:hover .fraud-popup {{ visibility: visible; opacity: 1; }}
            .popup-table {{ width: 100%; border-collapse: collapse; font-size:11px; }}
            .popup-table th {{ background: #f3f4f6; padding: 5px; text-align: center; }}
        </style>
        <div class="fraud-wrapper">
            {badge}
            <div class="fraud-popup">
                <div style="background:#333; color:#fff; padding:8px; border-radius:6px 6px 0 0; display:flex; text-align:center;">
                    <div style="flex:1;">Total: {total}</div>
                    <div style="flex:1; color:#4ade80;">Success: {success}</div>
                    <div style="flex:1; color:#f87171;">Cancel: {canceled}</div>
                </div>
                <table class="popup-table">
                    <thead><tr><th style="text-align:left;">Courier</th><th>Total</th><th>Ok</th><th>X</th></tr></thead>
                    <tbody>{popup_rows}</tbody>
                </table>
            </div>
        </div>
        """
        return mark_safe(html)

    def fraud_report_detail(self, obj):
        if not obj.phone: return "Phone number missing"
        data = obj.fraud_report_data
        if not data:
            data = get_customer_fraud_report(obj.phone)
            if data and "total_parcel" in data:
                obj.fraud_report_data = data
                obj.save(update_fields=['fraud_report_data'])
        if not data or "error" in data: return "No data available."
        
        try:
            total_p = int(float(data.get("total_parcel", 0)))
            success_p = int(float(data.get("success_parcel", 0)))
            cancel_p = int(float(data.get("cancel_parcel", 0)))
            score = data.get("score", 0)
            status = data.get("status", "Unknown")
        except: return "Data format error"

        courier_data = data.get("response", {})
        rows = ""
        for courier_name, info in courier_data.items():
            stats = info.get("data", {}) if isinstance(info, dict) else {}
            if stats:
                c_total = int(float(stats.get('total', 0)))
                c_success = int(float(stats.get('success', 0)))
                c_cancel = int(float(stats.get('cancel', 0)))
                return_rate = (c_cancel / c_total * 100) if c_total > 0 else 0
                rows += f"""<tr style="border-bottom: 1px solid #eee;"><td style="padding: 10px; font-weight: bold; text-transform: capitalize;">{courier_name}</td><td style="padding: 10px; text-align: center;">{c_total}</td><td style="padding: 10px; text-align: center; color: green;">{c_success}</td><td style="padding: 10px; text-align: center; color: red;">{c_cancel}</td><td style="padding: 10px; text-align: center;">{return_rate:.1f}%</td></tr>"""

        table = f"""<div style="max-width: 800px; margin-top:10px;"><div style="display: flex; gap: 15px; margin-bottom: 20px;"><div style="background: #f0fdf4; border: 1px solid #bbf7d0; padding: 15px; border-radius: 8px; flex: 1; text-align: center;"><h3 style="margin: 0; color: #166534; font-size: 20px;">{total_p}</h3><p style="margin: 0; color: #15803d; font-size: 12px;">মোট অর্ডার</p></div><div style="background: #ecfccb; border: 1px solid #d9f99d; padding: 15px; border-radius: 8px; flex: 1; text-align: center;"><h3 style="margin: 0; color: #3f6212; font-size: 20px;">{success_p}</h3><p style="margin: 0; color: #4d7c0f; font-size: 12px;">সফল ডেলিভারি</p></div><div style="background: #fef2f2; border: 1px solid #fecaca; padding: 15px; border-radius: 8px; flex: 1; text-align: center;"><h3 style="margin: 0; color: #991b1b; font-size: 20px;">{cancel_p}</h3><p style="margin: 0; color: #b91c1c; font-size: 12px;">মোট বাতিল</p></div></div><div style="border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden;"><table style="width: 100%; border-collapse: collapse; font-size: 13px;"><thead><tr style="background-color: #064e3b; color: white;"><th style="padding: 10px; text-align: left;">কুরিয়ার</th><th style="padding: 10px; text-align: center;">মোট</th><th style="padding: 10px; text-align: center;">সফল</th><th style="padding: 10px; text-align: center;">বাতিল</th><th style="padding: 10px; text-align: center;">রেট</th></tr></thead><tbody style="background: white;">{rows}</tbody></table></div><div style="margin-top: 10px; padding: 10px; background: #f3f4f6; border-radius: 6px; text-align: center; font-size: 12px;">Status: <strong>{status}</strong> | Score: <strong>{score}</strong></div></div>"""
        return mark_safe(table)

    fraud_report_detail.short_description = "Fraud Check Report"
    fraud_report_detail.allow_tags = True

    @admin.action(description="Check Fraud Status")
    def manual_check_fraud_action(self, request, queryset):
        count = 0
        for order in queryset:
            if not order.fraud_report_data:
                data = get_customer_fraud_report(order.phone)
                if data and "total_parcel" in data:
                    order.fraud_report_data = data
                    order.save(update_fields=['fraud_report_data'])
                    count += 1
        messages.success(request, f"Updated {count} orders.")

    @admin.action(description="Send to Steadfast")
    def send_to_steadfast_action(self, request, queryset):
        s = 0
        f = 0
        for order in queryset:
            ok, info = send_order_to_steadfast(order)
            if ok: s += 1
            else: 
                f += 1
                messages.error(request, f"Order #{order.id}: {info}")
        if s: messages.success(request, f"{s} orders sent.")

    @admin.action(description="Update Steadfast Status")
    def update_steadfast_status_action(self, request, queryset):
        u = 0
        for order in queryset:
            ok, _ = refresh_steadfast_status(order)
            if ok: u += 1
        messages.success(request, f"Updated {u} orders.")


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "product", "variant", "quantity", "price")


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    list_display = ("site_name", "logo_preview")
    def has_add_permission(self, request):
        if SiteSettings.objects.exists(): return False
        return super().has_add_permission(request)
    def logo_preview(self, obj):
        if obj.logo: return format_html('<img src="{}" style="height:40px;">', obj.logo.url)
        return "No logo"
    logo_preview.short_description = "Logo"