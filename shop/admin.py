from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils.safestring import mark_safe
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
from .utils import get_customer_fraud_report


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


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "name",
        "phone",
        "fraud_check_badge", 
        "delivery_area",
        "delivery_charge",
        "payment_method",
        "status",
        "paid",
        "steadfast_status",
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
    
    readonly_fields = ("fraud_report_detail",)
    inlines = [OrderItemInline]

    # [NEW] Manual Action Added
    actions = ["send_to_steadfast_action", "update_steadfast_status_action", "manual_check_fraud_action"]

    # --- FEATURE 1: Smart Fraud Check (Cached + Center Popup) ---
    def fraud_check_badge(self, obj):
        if not obj.phone:
            return "-"

        # ১. ডাটাবেস চেক করা (Cache Check)
        data = obj.fraud_report_data

        # ২. যদি ক্যাশে না থাকে, তবে লজিক অ্যাপ্লাই করা
        if not data:
            # লজিক: শুধুমাত্র নতুন (Pending) অর্ডারের জন্য অটোমেটিক API কল হবে
            if obj.status == 'pending':
                api_response = get_customer_fraud_report(obj.phone)
                
                # API সফল হলে সেভ করা
                if api_response and "total_parcel" in api_response:
                    obj.fraud_report_data = api_response
                    obj.save(update_fields=['fraud_report_data'])
                    data = api_response
                elif isinstance(api_response, dict) and "error" in api_response:
                    return format_html('<span style="color:red; font-size:10px;">{}</span>', api_response["error"])
            else:
                # পুরোনো অর্ডারে ম্যানুয়াল চেক বাটন বা টেক্সট দেখানো
                return format_html(
                    '<span style="color:#888; font-size:11px; cursor:help;" title="Select and use action to check">Not Checked</span>'
                )

        # ৩. ডাটা যাচাই এবং ডিসপ্লে
        if not data or "total_parcel" not in data:
            return mark_safe('<span style="color:gray;">No Data</span>')

        try:
            total = int(float(data.get("total_parcel", 0)))
            canceled = int(float(data.get("cancel_parcel", 0)))
            success = int(float(data.get("success_parcel", 0)))
        except (ValueError, TypeError):
            return mark_safe('<span style="color:gray;">Data Error</span>')

        # নতুন কাস্টমার
        if total == 0:
            return mark_safe('<span style="color:blue; font-weight:bold;">New Customer</span>')

        # ক্যালকুলেশন
        cancel_rate = 0
        if total > 0:
            cancel_rate = (canceled / total) * 100

        # ব্যাজ ডিজাইন
        if cancel_rate > 30: 
            badge_html = f'''
                <div style="background-color:#ffebee; color:#c62828; padding:4px 8px; border-radius:15px; border:1px solid #c62828; font-weight:bold; text-align:center; cursor:pointer; font-size:12px; display:inline-block;">
                    ⚠️ Risky ({int(cancel_rate)}%)
                </div>
            '''
        else: 
            success_rate = (success / total) * 100
            badge_html = f'''
                <div style="background-color:#e8f5e9; color:#2e7d32; padding:4px 8px; border-radius:15px; border:1px solid #2e7d32; font-weight:bold; text-align:center; cursor:pointer; font-size:12px; display:inline-block;">
                    ✅ Safe ({int(success_rate)}%)
                </div>
            '''

        # --- Popup Table Content ---
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
                            <td style="padding:8px; text-transform:capitalize; color:#000; font-weight:600; text-align:left;">{courier_name}</td>
                            <td style="padding:8px; text-align:center; color:#000;">{c_total}</td>
                            <td style="padding:8px; text-align:center; color:#166534; font-weight:bold;">{c_success}</td>
                            <td style="padding:8px; text-align:center; color:#dc2626; font-weight:bold;">{c_cancel}</td>
                        </tr>
                    """
        
        if not has_data:
            popup_rows = "<tr><td colspan='4' style='padding:10px; text-align:center; color:#666;'>No courier details available</td></tr>"

        # --- FINAL HTML & CSS (Fixed Position & High Contrast) ---
        html = f"""
        <style>
            .fraud-wrapper {{
                position: relative;
                display: inline-block;
            }}
            /* Fixed Position Popup - Center Screen */
            .fraud-wrapper .fraud-popup {{
                visibility: hidden;
                opacity: 0;
                position: fixed; /* Screen এর সাপেক্ষে ফিক্সড */
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                z-index: 999999; /* সবার উপরে */
                
                width: 320px;
                background-color: #ffffff;
                border-radius: 8px;
                box-shadow: 0 0 0 100vw rgba(0,0,0,0.5), 0 10px 40px rgba(0,0,0,0.5); /* অন্ধকার ব্যাকগ্রাউন্ড */
                border: 1px solid #ccc;
                font-family: sans-serif;
                transition: opacity 0.2s;
            }}
            .fraud-wrapper:hover .fraud-popup {{
                visibility: visible;
                opacity: 1;
            }}
            /* Header */
            .popup-header {{
                display: flex;
                background-color: #1f2937; /* Dark Grey Header */
                color: #ffffff;
                padding: 12px 0;
                border-radius: 7px 7px 0 0;
            }}
            .stat-box {{
                flex: 1;
                text-align: center;
                border-right: 1px solid #374151;
            }}
            .stat-box:last-child {{ border: none; }}
            .stat-val {{ display: block; font-size: 18px; font-weight: bold; }}
            .stat-lbl {{ font-size: 10px; text-transform: uppercase; opacity: 0.8; }}
            
            /* Table */
            .popup-table {{
                width: 100%;
                border-collapse: collapse;
                background-color: #ffffff;
            }}
            .popup-table th {{
                background-color: #f3f4f6;
                color: #374151;
                font-size: 11px;
                padding: 8px;
                text-align: center;
                border-bottom: 1px solid #e5e7eb;
            }}
            .popup-table td {{
                font-size: 12px;
                color: #000000; /* FORCE BLACK TEXT */
            }}
            .popup-footer {{
                padding: 8px;
                text-align: center;
                font-size: 10px;
                color: #6b7280;
                background: #f9fafb;
                border-radius: 0 0 7px 7px;
            }}
        </style>

        <div class="fraud-wrapper">
            {badge_html}
            <div class="fraud-popup">
                <div class="popup-header">
                    <div class="stat-box"><span class="stat-val">{total}</span><span class="stat-lbl">Total</span></div>
                    <div class="stat-box"><span class="stat-val" style="color:#4ade80;">{success}</span><span class="stat-lbl">Success</span></div>
                    <div class="stat-box"><span class="stat-val" style="color:#f87171;">{canceled}</span><span class="stat-lbl">Cancel</span></div>
                </div>
                <table class="popup-table">
                    <thead><tr><th style="text-align:left; padding-left:12px;">Courier</th><th>Total</th><th>Done</th><th>Cancel</th></tr></thead>
                    <tbody>{popup_rows}</tbody>
                </table>
                <div class="popup-footer">Source: OneCodeSoft Database</div>
            </div>
        </div>
        """
        return mark_safe(html)

    fraud_check_badge.short_description = "Reliability"
    fraud_check_badge.allow_tags = True

    # --- FEATURE 2: Detail Report uses Cache ---
    def fraud_report_detail(self, obj):
        if not obj.phone: return "Phone number missing"
        
        # ক্যাশ চেক
        data = obj.fraud_report_data
        if not data:
            # যদি ডিটেইল ভিউতে থাকি এবং ডাটা না থাকে, তখন লোড করে সেভ করি
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
                rows += f"""
                    <tr style="border-bottom: 1px solid #eee;">
                        <td style="padding: 10px; font-weight: bold; text-transform: capitalize;">{courier_name}</td>
                        <td style="padding: 10px; text-align: center;">{c_total}</td>
                        <td style="padding: 10px; text-align: center; color: green;">{c_success}</td>
                        <td style="padding: 10px; text-align: center; color: red;">{c_cancel}</td>
                        <td style="padding: 10px; text-align: center;">{return_rate:.1f}%</td>
                    </tr>
                """

        table = f"""
        <div style="max-width: 800px; margin-top:10px;">
            <div style="display: flex; gap: 15px; margin-bottom: 20px;">
                <div style="background: #f0fdf4; border: 1px solid #bbf7d0; padding: 15px; border-radius: 8px; flex: 1; text-align: center;">
                    <h3 style="margin: 0; color: #166534; font-size: 20px;">{total_p}</h3><p style="margin: 0; color: #15803d; font-size: 12px;">মোট অর্ডার</p>
                </div>
                <div style="background: #ecfccb; border: 1px solid #d9f99d; padding: 15px; border-radius: 8px; flex: 1; text-align: center;">
                    <h3 style="margin: 0; color: #3f6212; font-size: 20px;">{success_p}</h3><p style="margin: 0; color: #4d7c0f; font-size: 12px;">সফল ডেলিভারি</p>
                </div>
                <div style="background: #fef2f2; border: 1px solid #fecaca; padding: 15px; border-radius: 8px; flex: 1; text-align: center;">
                    <h3 style="margin: 0; color: #991b1b; font-size: 20px;">{cancel_p}</h3><p style="margin: 0; color: #b91c1c; font-size: 12px;">মোট বাতিল</p>
                </div>
            </div>
            <div style="border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden;">
                <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                    <thead><tr style="background-color: #064e3b; color: white;"><th style="padding: 10px; text-align: left;">কুরিয়ার</th><th style="padding: 10px; text-align: center;">মোট</th><th style="padding: 10px; text-align: center;">সফল</th><th style="padding: 10px; text-align: center;">বাতিল</th><th style="padding: 10px; text-align: center;">রেট</th></tr></thead>
                    <tbody style="background: white;">{rows}</tbody>
                </table>
            </div>
            <div style="margin-top: 10px; padding: 10px; background: #f3f4f6; border-radius: 6px; text-align: center; font-size: 12px;">Status: <strong>{status}</strong> | Score: <strong>{score}</strong></div>
        </div>
        """
        return mark_safe(table)

    # --- Manual Action to Check Fraud Status ---
    @admin.action(description="Check Fraud Status for selected orders")
    def manual_check_fraud_action(self, request, queryset):
        count = 0
        updated_count = 0
        for order in queryset:
            count += 1
            # যদি আগে ডাটা না থাকে, তবেই চেক করবে
            if not order.fraud_report_data:
                data = get_customer_fraud_report(order.phone)
                if data and "total_parcel" in data:
                    order.fraud_report_data = data
                    order.save(update_fields=['fraud_report_data'])
                    updated_count += 1
        
        messages.success(request, f"Checked {count} orders. Updated API data for {updated_count} orders.")

    @admin.action(description="Send selected orders to Steadfast")
    def send_to_steadfast_action(self, request, queryset):
        success_count = 0
        fail_count = 0
        for order in queryset:
            ok, info = send_order_to_steadfast(order)
            if ok: success_count += 1
            else:
                fail_count += 1
                messages.error(request, f"Order #{order.id} → Steadfast এ পাঠানো যায়নি: {info}")
        if success_count: messages.success(request, f"{success_count}টি order সফলভাবে Steadfast-এ পাঠানো হয়েছে।")
        if not success_count and not fail_count: messages.info(request, "কোনো order নির্বাচন করা হয়নি।")

    @admin.action(description="Update Steadfast delivery status")
    def update_steadfast_status_action(self, request, queryset):
        updated = 0
        for order in queryset:
            ok, info = refresh_steadfast_status(order)
            if ok: updated += 1
            else: messages.warning(request, f"Order #{order.id} → Steadfast status আপডেট হয়নি: {info}")
        if updated: messages.success(request, f"{updated}টি order-এর Steadfast status রিফ্রেশ করা হয়েছে।")


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