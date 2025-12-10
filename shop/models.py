from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator


# ===============================
# CATEGORY MODEL
# ===============================
class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name


# ===============================
# PRODUCT MODEL
# ===============================
class Product(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="products",
    )
    description = models.TextField()
    # main/base price (variant থাকলে ওটা override করবে)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.PositiveBigIntegerField(default=1)
    available = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    image = models.ImageField(upload_to="products/%Y/%m/%d")

    def __str__(self):
        return self.name

    def average_rating(self):
        ratings = self.ratings.all()
        if ratings.count() > 0:
            return sum(r.rating for r in ratings) / ratings.count()
        return 0

    @property
    def has_variants(self):
        """Template থেকে সহজে চেক করার জন্য।"""
        return self.variants.exists()

    def base_price(self):
        return self.price


# ===============================
# RATING MODEL
# ===============================
class Rating(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="ratings",
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField()
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("product", "user")

    def __str__(self):
        return f"{self.user.username} - {self.product.name} - {self.rating}"


# ===============================
# PRODUCT ATTRIBUTES
# ===============================
class Attribute(models.Model):
    TEXT = "text"
    COLOR = "color"
    SIZE = "size"
    WEIGHT = "weight"

    TYPE_CHOICES = (
        (TEXT, "Text"),
        (COLOR, "Color"),
        (SIZE, "Size"),
        (WEIGHT, "Weight"),
    )

    # e.g. Weight, Size, Color
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True)
    type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default=TEXT,
        help_text="Attribute type (text/size/color/weight)",
    )

    class Meta:
        verbose_name = "Attribute"
        verbose_name_plural = "Attributes"

    def __str__(self):
        return self.name


class AttributeValue(models.Model):
    attribute = models.ForeignKey(
        Attribute,
        on_delete=models.CASCADE,
        related_name="values",
    )
    # e.g. 500gm, 1kg, Red, XL
    value = models.CharField(max_length=100)
    color_code = models.CharField(
        max_length=7,
        blank=True,
        help_text="Only for color attributes (e.g. #FF0000)",
    )

    class Meta:
        verbose_name = "Attribute value"
        verbose_name_plural = "Attribute values"
        unique_together = ("attribute", "value")

    def __str__(self):
        return f"{self.attribute.name}: {self.value}"


class ProductVariant(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="variants",
    )
    name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Optional. If empty, name will be built from attribute values.",
    )
    sku = models.CharField(
        max_length=100,
        blank=True,
        help_text="Optional SKU/code for this variant.",
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Leave empty to use main product price.",
    )
    stock = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    attribute_values = models.ManyToManyField(
        AttributeValue,
        related_name="variants",
        blank=True,
        help_text="Tick the values for this variant (e.g. 500gm + Red + XL).",
    )

    class Meta:
        verbose_name = "Product variant"
        verbose_name_plural = "Product variants"

    def __str__(self):
        if self.name:
            return self.name
        attrs = ", ".join(v.value for v in self.attribute_values.all())
        return f"{self.product.name} ({attrs})" if attrs else self.product.name

    def get_price(self):
        """Variant এর নিজস্ব price থাকলে সেটা, না থাকলে product.price."""
        return self.price if self.price is not None else self.product.price


# ===============================
# CART MODEL
# ===============================
class Cart(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Cart for {self.user.username}"

    def get_total_price(self):
        return sum(item.get_cost() for item in self.items.all())

    def get_total_items(self):
        return sum(item.quantity for item in self.items.all())


# ===============================
# CART ITEM
# ===============================
class CartItem(models.Model):
    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name="items",
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE)

    # কোন variant (optional)
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cart_items",
    )

    quantity = models.PositiveIntegerField(default=1)

    def __str__(self):
        if self.variant:
            return f"{self.quantity} × {self.product.name} ({self.variant})"
        return f"{self.quantity} × {self.product.name}"

    def get_unit_price(self):
        if self.variant:
            return self.variant.get_price()
        return self.product.price

    def get_cost(self):
        return self.get_unit_price() * self.quantity


# ===============================
# ORDER MODEL
# ===============================
class Order(models.Model):

    DELIVERY_AREAS = (
        ("dhaka", "Dhaka City – ৳70"),
        ("outside", "Outside Dhaka – ৳120"),
    )

    PAYMENT_METHODS = (
        ("cod", "Cash On Delivery"),
        ("sslcommerz", "SSLCommerz Online Payment"),
    )

    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("shipped", "Shipped"),
        ("delivered", "Delivered"),
        ("canceled", "Canceled"),
    )

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )

    # Main customer fields
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20)
    address = models.TextField()

    delivery_area = models.CharField(
        max_length=20,
        choices=DELIVERY_AREAS,
        default="dhaka",
    )
    delivery_charge = models.PositiveIntegerField(default=70)

    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHODS,
        default="cod",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )
    paid = models.BooleanField(default=False)
    transaction_id = models.CharField(max_length=200, blank=True)

    # -------- Steadfast integration fields --------
    steadfast_invoice = models.CharField(
        max_length=100,
        blank=True,
        help_text="Invoice string sent to Steadfast (e.g. ORD-123).",
    )
    steadfast_consignment_id = models.CharField(
        max_length=50,
        blank=True,
        help_text="Consignment id returned by Steadfast.",
    )
    steadfast_tracking_code = models.CharField(
        max_length=50,
        blank=True,
        help_text="Tracking code returned by Steadfast.",
    )
    steadfast_status = models.CharField(
        max_length=50,
        blank=True,
        help_text="Latest delivery status from Steadfast.",
    )
    # ---------------------------------------------

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return f"Order #{self.id}"

    def get_subtotal(self):
        return sum(item.get_cost() for item in self.items.all())

    def get_total_cost(self):
        return self.get_subtotal() + self.delivery_charge


# ===============================
# ORDER ITEM
# ===============================
class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE)

    # কোন variant ছিল (optional)
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_items",
    )

    quantity = models.PositiveIntegerField(default=1)
    # snapshot of unit price
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        if self.variant:
            return f"{self.quantity} × {self.product.name} ({self.variant})"
        return f"{self.quantity} × {self.product.name}"

    def get_cost(self):
        return self.price * self.quantity


# ===============================
# SITE SETTINGS (Logo + Site Name)
# ===============================
class SiteSettings(models.Model):
    site_name = models.CharField(
        max_length=200,
        default="E-Shop",
        help_text="Website name shown in navbar and footer.",
    )
    logo = models.ImageField(
        upload_to="site_logo/",
        blank=True,
        null=True,
        help_text="Upload the main logo for the site.",
    )

    class Meta:
        verbose_name = "Site Settings"
        verbose_name_plural = "Site Settings"

    def __str__(self):
        return "Website Settings"
