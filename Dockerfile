# Base ইমেজ হিসেবে অফিসিয়াল পাইথন ব্যবহার করছি
FROM python:3.10-slim

# এনভায়রনমেন্ট ভ্যারিয়েবল সেট করা যাতে পাইথন আউটপুট ক্যাশ না করে
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# কন্টেইনারের ভেতরের ওয়ার্কিং ডিরেক্টরি
WORKDIR /app

# প্রয়োজনীয় ডিপেন্ডেন্সি ইনস্টল করা
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && rm -rf /var/lib/apt/lists/*

# requirements.txt কপি করে প্লাগইনগুলো ইনস্টল করা
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir gunicorn

# প্রজেক্টের বাকি সব কোড কন্টেইনারে কপি করা
COPY . /app/

# পোর্ট এক্সপোজ করা
EXPOSE 8000

# Gunicorn দিয়ে প্রোডাকশন সার্ভার রান করা (আপনার মেইন ফোল্ডার e_shop অনুযায়ী)
CMD ["gunicorn", "e_shop.wsgi:application", "--bind", "0.0.0.0:8000"]