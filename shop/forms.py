from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Rating, Order


# -------------------------
#  USER REGISTRATION FORM
# -------------------------
class RegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(required=True)
    last_name = forms.CharField(required=True)

    class Meta:
        model = User
        fields = [
            "username",
            "first_name",
            "last_name",
            "email",
            "password1",
            "password2",
        ]


# -------------------------
#  PRODUCT RATING FORM
# -------------------------
class RatingForm(forms.ModelForm):
    class Meta:
        model = Rating
        fields = ["rating", "comment"]
        widgets = {
            "rating": forms.Select(choices=[(i, i) for i in range(1, 6)]),
            "comment": forms.Textarea(attrs={"rows": 4}),
        }


# -------------------------
#  CHECKOUT FORM (Name, Phone, Address, Delivery, Payment)
# -------------------------
class CheckoutForm(forms.ModelForm):
    # Choices model থেকে নিলাম
    DELIVERY_CHOICES = Order.DELIVERY_AREAS
    PAYMENT_CHOICES = Order.PAYMENT_METHODS

    name = forms.CharField(
        label="Name",
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Your name",
                "class": "w-full border rounded-lg px-4 py-2 focus:ring-2 focus:ring-purple-300",
            }
        ),
    )

    phone = forms.CharField(
        label="Phone",
        max_length=20,
        widget=forms.TextInput(
            attrs={
                "placeholder": "01XXXXXXXXX",
                "class": "w-full border rounded-lg px-4 py-2 focus:ring-2 focus:ring-purple-300",
            }
        ),
    )

    address = forms.CharField(
        label="Address",
        widget=forms.Textarea(
            attrs={
                "placeholder": "Full address…",
                "rows": 3,
                "class": "w-full border rounded-lg px-4 py-2 focus:ring-2 focus:ring-purple-300",
            }
        ),
    )

    delivery_area = forms.ChoiceField(
        label="Delivery Area",
        choices=DELIVERY_CHOICES,
        widget=forms.Select(
            attrs={
                "class": "w-full border rounded-lg px-4 py-2 focus:ring-2 focus:ring-purple-300",
            }
        ),
    )

    payment_method = forms.ChoiceField(
        label="Payment Method",
        choices=PAYMENT_CHOICES,
        initial="cod",
        widget=forms.RadioSelect(attrs={"class": "space-y-2"}),
    )

    class Meta:
        model = Order
        fields = ["name", "phone", "address", "delivery_area", "payment_method"]

    # ------- simple validation ----------
    def clean_phone(self):
        phone = self.cleaned_data.get("phone", "").strip()
        if not phone:
            raise forms.ValidationError("Phone is required.")
        digits = [ch for ch in phone if ch.isdigit()]
        if len(digits) < 10:
            raise forms.ValidationError("Enter a valid phone number.")
        return phone

    def clean_name(self):
        name = self.cleaned_data.get("name", "").strip()
        if not name:
            raise forms.ValidationError("Name is required.")
        return name
