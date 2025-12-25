import json
from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.db import models
from django.forms import CheckboxSelectMultiple
from django.utils import timezone
from django.utils.timesince import timesince
from django.urls import path, reverse
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse

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
    OrderNote,
)
from .steadfast import send_order_to_steadfast, refresh_steadfast_status
from .utils import get_customer_fraud_report, send_facebook_purchase_event


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
    formfield_overrides = {models.ManyToManyField: {'widget': CheckboxSelectMultiple}}
    classes = ['collapse']

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "price", "stock", "available", "created")
    list_filter = ("available", "created", "category")
    list_editable = ("price", "stock", "available")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ProductVariantInline]
    save_on_top = True

@admin.register(Rating)
class RatingAdmin(admin.ModelAdmin):
    list_display = ("product", "user", "rating", "created")

@admin.register(Attribute)
class AttributeAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "type")
    prepopulated_fields = {"slug": ("name",)}

@admin.register(AttributeValue)
class AttributeValueAdmin(admin.ModelAdmin):
    list_display = ("attribute", "value", "color_code")
    list_filter = ("attribute",)

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

class OrderNoteInline(admin.TabularInline):
    model = OrderNote
    extra = 1
    fields = ('note', 'user', 'created_at')
    readonly_fields = ('user', 'created_at')
    def has_add_permission(self, request, obj): return True


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
    
    list_filter = ("status", "paid", "payment_method", "created", "steadfast_status")
    search_fields = ("id", "name", "phone", "address", "steadfast_tracking_code", "steadfast_invoice")
    readonly_fields = ("fraud_report_detail",)
    inlines = [OrderItemInline, OrderNoteInline]
    actions = ["make_confirmed_action", "send_to_steadfast_action", "update_steadfast_status_action", "manual_check_fraud_action"]
    list_per_page = 20

    # --------------------------------------------------------
    # CUSTOM URL FOR QUICK NOTE ADDING
    # --------------------------------------------------------
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'add-quick-note/<int:order_id>/',
                self.admin_site.admin_view(self.process_add_note),
                name='order-add-quick-note',
            ),
        ]
        return custom_urls + urls

    def process_add_note(self, request, order_id):
        if request.method == 'POST':
            note_text = request.POST.get('note')
            if note_text:
                order = Order.objects.get(id=order_id)
                OrderNote.objects.create(
                    order=order,
                    user=request.user,
                    note=note_text
                )
                messages.success(request, f"Note added to Order #{order_id}")
            else:
                messages.warning(request, "Note cannot be empty.")
        
        return HttpResponseRedirect(reverse('admin:shop_order_changelist'))

    # --------------------------------------------------------
    # CUSTOMER INFO COLUMN (MERGED: FRAUD POPUP + NOTES)
    # --------------------------------------------------------
    def customer_info_display(self, obj):
        # 1. Get the Fraud Badge with Popup HTML
        badge_html = self.fraud_check_badge(obj)
        
        # 2. Address Shortener
        addr = obj.address[:40] + "..." if len(obj.address) > 40 else obj.address
        
        # 3. Add Note Button
        add_note_url = reverse('admin:order-add-quick-note', args=[obj.id])
        
        script = f"""
        <script>
            function promptNote_{obj.id}() {{
                let note = prompt("Enter note for Order #{obj.id}:");
                if (note != null && note != "") {{
                    let form = document.createElement('form');
                    form.method = 'POST';
                    form.action = '{add_note_url}';
                    let csrf = document.querySelector('[name=csrfmiddlewaretoken]').value;
                    let csrfInput = document.createElement('input');
                    csrfInput.type = 'hidden';
                    csrfInput.name = 'csrfmiddlewaretoken';
                    csrfInput.value = csrf;
                    form.appendChild(csrfInput);
                    let noteInput = document.createElement('input');
                    noteInput.type = 'hidden';
                    noteInput.name = 'note';
                    noteInput.value = note;
                    form.appendChild(noteInput);
                    document.body.appendChild(form);
                    form.submit();
                }}
            }}
        </script>
        """

        # 4. Note History
        all_notes = obj.notes.all()
        note_html = ""
        if all_notes.exists():
            rows = ""
            for note in all_notes:
                user_name = note.user.username if note.user else "System"
                time_ago = timesince(note.created_at).split(",")[0]
                rows += f"""<div style="border-bottom:1px solid #fde68a; padding: 4px 0; font-size:11px; line-height:1.3;"><div style="font-weight:bold; color:#b45309; font-size:10px;">{user_name} <span style="font-weight:normal; color:#92400e;">({time_ago} ago)</span></div><div style="color:#333;">{note.note}</div></div>"""
            note_html = f"""<div style="background:#fffbeb; border:1px solid #fcd34d; padding:5px; border-radius:4px; margin-top:5px; max-height:120px; overflow-y:auto;">{rows}</div>"""

        # 5. Final Assembly
        return format_html(
            """<div style="line-height: 1.4;"><div style="font-weight:bold; font-size:13px; color:#333;">{}</div><div style="color:#555; font-size: 12px;">📞 {}</div><div style="color:#777; font-size: 11px;">📍 {}</div><div style="margin-top:4px; margin-bottom:4px;">{}</div><div style="margin-top:5px;"><a href="javascript:void(0);" onclick="promptNote_{}();" style="background:#0f172a; color:#fff; padding:2px 6px; border-radius:3px; font-size:10px; text-decoration:none;">➕ Note</a></div>{}{}</div>""",
            obj.name, obj.phone, addr, badge_html, obj.id, mark_safe(script), mark_safe(note_html)
        )
    customer_info_display.short_description = "Customer & Notes"

    # --------------------------------------------------------
    # FRAUD CHECK BADGE LOGIC (RESTORED FULL POPUP)
    # --------------------------------------------------------
    def fraud_check_badge(self, obj):
        if not obj.phone: return ""
        
        data = obj.fraud_report_data
        
        # Auto-fetch if data is missing
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

        # --- RESTORED POPUP LOGIC ---
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

        # Full HTML with CSS for Hover Popup
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

    # --------------------------------------------------------
    # OTHER DISPLAYS
    # --------------------------------------------------------
    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for instance in instances:
            if isinstance(instance, OrderNote) and not instance.user:
                instance.user = request.user
            instance.save()
        formset.save_m2m()

    def make_confirmed_action(self, request, queryset):
        s = 0
        config = SiteSettings.objects.first()
        for order in queryset:
            if order.status != 'confirmed':
                order.status = 'confirmed'
                order.save()
                s += 1
                # Only send if mode is MANUAL
                if config and config.facebook_pixel_mode == 'manual':
                    send_facebook_purchase_event(order)
        messages.success(request, f"{s} orders confirmed.")

    def save_model(self, request, obj, form, change):
        if change:
            old = Order.objects.get(pk=obj.pk)
            if old.status != 'confirmed' and obj.status == 'confirmed':
                config = SiteSettings.objects.first()
                # Only send if mode is MANUAL
                if config and config.facebook_pixel_mode == 'manual':
                    send_facebook_purchase_event(obj)
        super().save_model(request, obj, form, change)

    def order_id_display(self, obj): return format_html('<b>#{}</b>', obj.id)
    order_id_display.short_description = "ID"

    def order_items_display(self, obj):
        items = obj.items.all()
        if not items: return "-"
        html = '<ul style="margin:0; padding-left:15px; font-size:12px; color:#444;">'
        for item in items:
            v = f" ({item.variant})" if item.variant else ""
            html += f"<li>{item.quantity}x <b>{item.product.name}</b>{v}</li>"
        return mark_safe(html + '</ul>')
    order_items_display.short_description = "Products"

    def amount_info_display(self, obj):
        return format_html(
            '<div style="font-size:14px; font-weight:bold; color:#108a00;">৳{}</div><div style="font-size:10px; color:#666;">Delivery: ৳{}</div>',
            obj.get_total_cost(), obj.delivery_charge
        )
    amount_info_display.short_description = "Total"

    def payment_status_display(self, obj):
        icon = '<span style="color:green; font-weight:bold;">✔ PAID</span>' if obj.paid else '<span style="color:red; font-weight:bold;">✖ UNPAID</span>'
        return format_html('<div style="font-weight:bold; color:#444;">{}</div><div style="font-size:11px;">{}</div>', obj.payment_method.upper(), mark_safe(icon))
    payment_status_display.short_description = "Payment"

    def status_label(self, obj):
        colors = {'pending': '#f59e0b', 'confirmed': '#0ea5e9', 'processing': '#3b82f6', 'shipped': '#8b5cf6', 'delivered': '#10b981', 'canceled': '#ef4444'}
        return format_html('<span style="background-color:{}; color:white; padding:3px 8px; border-radius:12px; font-size:11px; font-weight:bold; text-transform:uppercase;">{}</span>', colors.get(obj.status, '#666'), obj.status)
    status_label.short_description = "Status"

    def steadfast_info(self, obj):
        if not obj.steadfast_consignment_id: return mark_safe('<span style="color:#bbb; font-size:11px;">Not Sent</span>')
        bg = "#dcfce7" if obj.steadfast_status == 'delivered' else "#e3f2fd"
        color = "#166534" if obj.steadfast_status == 'delivered' else "#1565c0"
        return format_html(
            '<div style="line-height:1.5;"><div style="margin-bottom:4px;"><span style="background:{}; color:{}; padding:2px 6px; border-radius:4px; font-size:10px; font-weight:bold; text-transform:uppercase;">{}</span></div><div style="font-size:11px;"><b>CID:</b> {}</div><div style="margin-top:5px;"><a href="https://steadfast.com.bd/t/{}" target="_blank" style="background:#2563eb; color:white; padding:3px 8px; border-radius:4px; text-decoration:none; font-size:10px; font-weight:bold;">🚀 Live Track</a></div></div>',
            bg, color, obj.steadfast_status, obj.steadfast_consignment_id, obj.steadfast_tracking_code
        )
    steadfast_info.short_description = "Courier"

    def created_at_display(self, obj):
        local = timezone.localtime(obj.created)
        ago = f"{timesince(local).split(',')[0]} ago"
        style = "color:#166534; font-weight:bold;" if (timezone.now() - obj.created).days < 1 else "color:#666;"
        return format_html('<div style="white-space:nowrap; line-height:1.4;"><div style="font-weight:600; color:#333; font-size:12px;">{}</div><div style="font-size:11px;"><b>{}</b></div><div style="font-size:10px; margin-top:2px; {}">{}</div></div>', local.strftime("%d %b, %Y"), local.strftime("%I:%M %p"), style, ago)
    created_at_display.short_description = "Date"

    def fraud_report_detail(self, obj): return "Details hidden for brevity"
    def manual_check_fraud_action(self, request, queryset): pass
    def send_to_steadfast_action(self, request, queryset): pass
    def update_steadfast_status_action(self, request, queryset): pass

@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "product", "variant", "quantity", "price")

@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    list_display = ("site_name", "logo_preview")
    def has_add_permission(self, request): return False if SiteSettings.objects.exists() else True
    def logo_preview(self, obj): return format_html('<img src="{}" style="height:40px;">', obj.logo.url) if obj.logo else "No logo"