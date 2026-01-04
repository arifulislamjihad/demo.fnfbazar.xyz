import re 
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from ckeditor_uploader.fields import RichTextUploadingField
from django.conf import settings # Import settings

# ===============================
# CATEGORY MODEL
# ===============================
class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    icon = models.ImageField(upload_to="category_icons/", blank=True, null=True) # Daraz Icon
    is_featured = models.BooleanField(default=False)

    class Meta: verbose_name_plural = "Categories"
    def __str__(self): return self.name

# ===============================
# PRODUCT MODEL
# ===============================
class Product(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="products")
    description = RichTextUploadingField() # Rich Text Editor
    
    # Pricing
    price = models.DecimalField(max_digits=10, decimal_places=2)
    old_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    stock = models.PositiveBigIntegerField(default=1)
    available = models.BooleanField(default=True)
    is_flash_sale = models.BooleanField(default=False) # Flash Sale Logic
    
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    image = models.ImageField(upload_to="products/%Y/%m/%d")

    def __str__(self): return self.name
    def average_rating(self):
        ratings = self.ratings.all()
        return sum(r.rating for r in ratings) / ratings.count() if ratings.count() > 0 else 0
    
    def get_discount_percentage(self):
        if self.old_price and self.old_price > self.price:
            return int(((self.old_price - self.price) / self.old_price) * 100)
        return 0
    
    @property
    def has_variants(self): return self.variants.exists()
    def base_price(self): return self.price

# ===============================
# PRODUCT GALLERY IMAGES
# ===============================
class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to="products/gallery/", blank=True, null=True)
    video_file = models.FileField(upload_to="products/videos/", blank=True, null=True) 
    youtube_url = models.URLField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self): return f"Media for {self.product.name}"
    
    def get_youtube_embed_url(self):
        if not self.youtube_url: return None
        regex = r'(?:https?:\/\/)?(?:www\.|m\.)?(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?|shorts)\/|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})'
        match = re.search(regex, self.youtube_url)
        if match: return f"https://www.youtube.com/embed/{match.group(1)}"
        return None

# ===============================
# RATING, ATTRIBUTES, CART
# ===============================
class Rating(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="ratings")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField()
    created = models.DateTimeField(auto_now_add=True)
    class Meta: unique_together = ("product", "user")
    def __str__(self): return f"{self.user.username} - {self.product.name}"

class Attribute(models.Model):
    TEXT, COLOR, SIZE, WEIGHT = "text", "color", "size", "weight"
    TYPE_CHOICES = ((TEXT, "Text"), (COLOR, "Color"), (SIZE, "Size"), (WEIGHT, "Weight"))
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TEXT)
    class Meta: verbose_name_plural = "Attributes"
    def __str__(self): return self.name

class AttributeValue(models.Model):
    attribute = models.ForeignKey(Attribute, on_delete=models.CASCADE, related_name="values")
    value = models.CharField(max_length=100)
    color_code = models.CharField(max_length=7, blank=True)
    class Meta: unique_together = ("attribute", "value")
    def __str__(self): return f"{self.attribute.name}: {self.value}"

class ProductVariant(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    name = models.CharField(max_length=200, blank=True)
    sku = models.CharField(max_length=100, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    stock = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    image = models.ImageField(upload_to="products/variants/", blank=True, null=True)
    attribute_values = models.ManyToManyField(AttributeValue, related_name="variants", blank=True)
    class Meta: verbose_name_plural = "Product variants"
    def __str__(self): return self.name or self.product.name
    def get_price(self): return self.price if self.price is not None else self.product.price

class Cart(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    def __str__(self): return f"Cart for {self.user.username}"
    def get_total_price(self): return sum(item.get_cost() for item in self.items.all())
    def get_total_items(self): return sum(item.quantity for item in self.items.all())

class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    variant = models.ForeignKey(ProductVariant, on_delete=models.SET_NULL, null=True, blank=True, related_name="cart_items")
    quantity = models.PositiveIntegerField(default=1)
    def __str__(self): return f"{self.quantity} x {self.product.name}"
    def get_unit_price(self): return self.variant.get_price() if self.variant else self.product.price
    def get_cost(self): return self.get_unit_price() * self.quantity

class DeliveryOption(models.Model):
    location = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=6, decimal_places=2)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return f"{self.location} - ৳{self.price}"

# ===============================
# ORDER MODEL (Updated for Vendor)
# ===============================
class Order(models.Model):
    PAYMENT_METHODS = (("cod", "Cash On Delivery"), ("sslcommerz", "SSLCommerz"))
    STATUS_CHOICES = (("pending", "Pending"), ("confirmed", "Confirmed"), ("processing", "Processing"), ("shipped", "Shipped"), ("delivered", "Delivered"), ("canceled", "Canceled"))
    
    # [UPDATED] Vendor Field for Multi-User System
    vendor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="vendor_orders")
    
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20)
    address = models.TextField()
    email = models.EmailField(blank=True, null=True) 
    
    delivery_area = models.CharField(max_length=100)
    delivery_charge = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default="cod")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    paid = models.BooleanField(default=False)
    transaction_id = models.CharField(max_length=200, blank=True)
    
    # Note for Webhook reference
    note = models.TextField(blank=True, null=True)

    # Steadfast Fields
    steadfast_invoice = models.CharField(max_length=100, blank=True)
    steadfast_consignment_id = models.CharField(max_length=50, blank=True)
    steadfast_tracking_code = models.CharField(max_length=50, blank=True)
    steadfast_status = models.CharField(max_length=50, blank=True)
    fraud_report_data = models.JSONField(blank=True, null=True)
    
    # [IMPORTANT] Facebook Advanced Matching Fields
    fbp = models.CharField(max_length=255, blank=True, null=True)
    fbc = models.CharField(max_length=255, blank=True, null=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True, null=True)
    
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    
    class Meta: ordering = ["-created"]
    def __str__(self): return f"Order #{self.id}"
    def get_subtotal(self): return sum(item.get_cost() for item in self.items.all())
    def get_total_cost(self): return self.get_subtotal() + self.delivery_charge

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    variant = models.ForeignKey(ProductVariant, on_delete=models.SET_NULL, null=True, blank=True, related_name="order_items")
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    def __str__(self): return f"{self.quantity} x {self.product.name}"
    def get_cost(self): return self.price * self.quantity

class SiteSettings(models.Model):
    site_name = models.CharField(max_length=200, default="E-Shop")
    logo = models.ImageField(upload_to="site_logo/", blank=True, null=True)
    about_text = models.TextField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    facebook = models.URLField(blank=True)
    instagram = models.URLField(blank=True)
    youtube = models.URLField(blank=True)
    twitter = models.URLField(blank=True)
    footer_text = models.CharField(max_length=255, blank=True, default="All Rights Reserved.")
    steadfast_api_key = models.CharField(max_length=255, blank=True)
    steadfast_secret_key = models.CharField(max_length=255, blank=True)
    facebook_pixel_id = models.CharField(max_length=50, blank=True)
    facebook_access_token = models.TextField(blank=True)
    PIXEL_MODES = (('manual', 'Manual'), ('automatic', 'Automatic'))
    facebook_pixel_mode = models.CharField(max_length=20, choices=PIXEL_MODES, default='manual')
    facebook_test_event_code = models.CharField(max_length=50, blank=True)
    class Meta: verbose_name_plural = "Site Settings"
    def __str__(self): return "Website Configuration"

class OrderNote(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='notes')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    note = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ['-created_at']
    def __str__(self): return f"Note for Order #{self.order.id}"

# ===============================
# VENDOR WEBHOOK SETTINGS (NEW)
# ===============================
class VendorWebhook(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='webhook_settings')
    is_active = models.BooleanField(default=True, verbose_name="Webhook Active?")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Webhook for {self.user.username}"