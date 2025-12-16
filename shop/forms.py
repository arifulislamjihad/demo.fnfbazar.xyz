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
#  CHECKOUT FORM
# -------------------------
class CheckoutForm(forms.ModelForm):
    # PAYMENT_CHOICES মডেল থেকে নেওয়া নিরাপদ
    PAYMENT_CHOICES = Order.PAYMENT_METHODS

    name = forms.CharField(
        label="Name",
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Your name",
                "class": "w-full border rounded-lg px-4 py-2 focus:ring-2 focus:ring-purple-300 outline-none",
            }
        ),
    )

    phone = forms.CharField(
        label="Phone",
        max_length=20,
        widget=forms.TextInput(
            attrs={
                "placeholder": "01XXXXXXXXX",
                "class": "w-full border rounded-lg px-4 py-2 focus:ring-2 focus:ring-purple-300 outline-none",
            }
        ),
    )

    address = forms.CharField(
        label="Address",
        widget=forms.Textarea(
            attrs={
                "placeholder": "Full address…",
                "rows": 3,
                "class": "w-full border rounded-lg px-4 py-2 focus:ring-2 focus:ring-purple-300 outline-none",
            }
        ),
    )

    # [NOTE] delivery_area এখান থেকে বাদ দেওয়া হয়েছে কারণ 
    # সেটি এখন ডায়নামিক এবং HTML টেমপ্লেটে সরাসরি রেন্ডার করা হয়।
    
    payment_method = forms.ChoiceField(
        label="Payment Method",
        choices=PAYMENT_CHOICES,
        initial="cod",
        widget=forms.Select( # রেডিও বাটনের বদলে ড্রপডাউন বা সিলেক্ট দেওয়া হলো স্টাইলের জন্য
            attrs={
                "class": "w-full border rounded-lg px-4 py-2 focus:ring-2 focus:ring-purple-300 outline-none bg-white"
            }
        ),
    )

    class Meta:
        model = Order
        # delivery_area বাদ দেওয়া হয়েছে কারণ ভিউ সেটি ম্যানুয়ালি হ্যান্ডেল করবে
        fields = ["name", "phone", "address", "payment_method"]

    # ------- Simple Validation ----------
    def clean_phone(self):
        phone = self.cleaned_data.get("phone", "").strip()
        if not phone:
            raise forms.ValidationError("Phone is required.")
        # বাংলাদশি নাম্বারের জন্য সাধারণ চেক (ঐচ্ছিক)
        digits = [ch for ch in phone if ch.isdigit()]
        if len(digits) < 10:
            raise forms.ValidationError("Enter a valid phone number.")
        return phone

    def clean_name(self):
        name = self.cleaned_data.get("name", "").strip()
        if not name:
            raise forms.ValidationError("Name is required.")
        return name