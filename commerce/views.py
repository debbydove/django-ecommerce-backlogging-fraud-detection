from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.db.models import Q
from django.shortcuts import render
from .models import Payment
import csv
import ipinfo
import os
from django.http import HttpResponse
from django.views.generic import View
from .models import *
from .forms import *

# Create your views here.

@login_required
def OrderedProductView(request):
    obj = Cart.objects.filter(buyer=request.user, ordered=True).order_by('-date_ordered')
    context = {'obj':obj}
    return render(request, 'carted.html', context)


def CancelTransactionView(request):
    # Your cancellation logic goes here
    return render(request, 'cancel_transaction.html') 

@login_required
def VerifyPaymentView(request, ref, pk):
    payment = Payment.objects.get(ref=ref)
    verified = payment.verify_payment()  # Assuming this method verifies the payment status

    if verified:
        # Fraud detection logic based on previous payments and user location
        try:
            # Read data from the user's CSV file for fraud detection
            user_csv_path = os.path.join(settings.BASE_DIR, f'{request.user.username}_payments.csv')
            ls = []
            with open(user_csv_path, 'r') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    amt = float(row["Amount"])
                    ls.append(amt)

            # Check if the current payment amount exceeds 1.5 times the highest past payment
            amount = payment.price
            highest_past_payment = max(ls) if ls else 0  # Get the highest past payment, default to 0 if no past payments
            limit = int(1.5 * highest_past_payment)

            warning_message = None

            if amount > limit:
                # Payment amount exceeds the limit, flag as potential fraud
                warning_message = "Warning: This transaction may be fraudulent."

            # Get user location based on IP address
            access_token = 'a466da308aaa2a'     # access token from ipinfo.io
            handler = ipinfo.getHandler(access_token)
            details = handler.getDetails()      # getting all the details about location

            # Check user location
            user_country = details.country
            if user_country != 'NG':
                # User location is not Nigeria, flag as potential fraud
                warning_message = "Warning: This transaction may be fraudulent."

            # If a warning message is present, redirect to the fraud_warning page
            if warning_message:
                return render(request, "fraud_warning.html", {"warning_message": warning_message})

            # Proceed with processing the order
            obj = Cart.objects.get(id=pk)
            obj.ordered = True
            obj.save()

            # Save payment details to CSV file
            save_payment_to_csv(request.user, payment, warning_message)

            return render(request, "success.html")

        except Exception as e:
            # Handle exceptions
            return render(request, "error.html")

    else:
        # Payment verification failed, handle accordingly
        return render(request, "error.html")

@login_required
def CheckOutView(request, id):
    obj = Cart.objects.get(id=id)
    form = CheckOutForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            data = form.save(commit=False)
            data.buyer = request.user
            data.cart = obj
            data.save()

            # Validate transaction data against fraud detection logic
            validated = validate_transaction(request.user, obj.get_price())
            if not validated:
                return render(request, "fraud_warning.html", {"warning_message": "Warning: This transaction may be fraudulent."})

            # Proceed with payment process if transaction data is valid
            pk = settings.PAYSTACK_PUBLIC_KEY
            payment = Payment.objects.create(price=obj.get_price(), email=data.email, buyer=request.user)
            payment.save()

            # Save payment details to CSV file
            save_payment_to_csv(request.user, payment)

            context = {
                'obj': obj,
                'payment': payment,
                'field_values': request.POST,
                'paystack_pub_key': pk,
                'price_value': payment.price_value(),
            }
            return render(request, 'payment.html', context)
    return render(request, 'check.html', {"form": form, 'obj': obj}) 

def validate_transaction(user, amount):
    try:
        # Read data from the user's CSV file for fraud detection
        user_csv_path = os.path.join(settings.BASE_DIR, f'{user.username}_payments.csv')
        ls = []
        with open(user_csv_path, 'r') as file:
            reader = csv.DictReader(file)
            for row in reader:
                amt = float(row["Amount"])
                ls.append(amt)

        # Check if the current payment amount exceeds 1.5 times the highest past payment
        highest_past_payment = max(ls) if ls else 0  # Get the highest past payment, default to 0 if no past payments
        limit = int(1.5 * highest_past_payment)

        if amount > limit:
            return False

        # Get user location based on IP address
        access_token = 'a466da308aaa2a'     # access token from ipinfo.io
        handler = ipinfo.getHandler(access_token)
        details = handler.getDetails()      # getting all the details about location

        # Check user location
        user_country = details.country
        if user_country != 'NG':
            return False

        return True

    except Exception as e:
        # Handle exceptions
        return False


def save_payment_to_csv(user, payment, warning_message=None):
    # Define the path for the user's CSV file
    user_csv_path = os.path.join(settings.BASE_DIR, f'{user.username}_payments.csv')

    # Check if the CSV file exists, if not, create it and write the header row
    if not os.path.exists(user_csv_path):
        with open(user_csv_path, 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['Date', 'Amount', 'Reference', 'Email', 'Verified', 'Warning Message'])

    # Append payment details to the CSV file
    with open(user_csv_path, 'a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([payment.date_created, payment.price, payment.ref, payment.email, payment.verified, warning_message])

def CategoryView(request, category):
    obj = Product.objects.filter(category__name=category)
    obj_c = Product.objects.filter(category__name=category).count()
    context = {'obj':obj, 'obj_c':obj_c}
    return render(request, 'category.html', context)

@login_required
def QueryView(request, pk):
    obj = Cart.objects.filter(buyer=request.user).get(id=pk)
    form = QueryForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            data = form.save(commit=False)
            data.buyer = request.user
            data.order = obj
            data.save()
            obj.queried = True
            obj.save()
            return render(request, 'queried.html')
    context = {'form':form, 'obj':obj}
    return render(request, 'addreview.html', context)

@login_required
def AddReviewView(request, pk):
    obj = Product.objects.get(id=pk)
    form = ReviewForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            data=form.save(commit=False)
            data.buyer = request.user
            data.product=obj
            data.save()
            return redirect(reverse('detail', args=[obj.pk]))
    context = {'form':form, 'obj':obj}
    return render(request, 'addreview.html', context)

@login_required
def LikeView(request, pk):
    obj = Product.objects.get(id=pk)
    if obj.likes.filter(id=request.user.id).exists():
        obj.likes.remove(request.user)
    else:
        obj.likes.add(request.user)
    return redirect(reverse('detail', args=[obj.pk]))

def PrivacyView(request):
    return render(request, 'privacy.html')

def TermView(request):
    return render(request, 'term.html')

def AboutView(request):
    return render(request, 'about.html')

def ContactView(request):
    return render(request, 'contact.html')

def RegisterView(request):
    form = RegisterForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            return redirect('login')
    context = {'form':form}
    return render(request, 'registration/register.html', context)

@login_required
def CartView(request):
    obj = Cart.objects.filter(buyer=request.user, ordered=False).order_by('-date_ordered')
    context = {'obj':obj}
    return render(request, 'cart.html', context)

@login_required
def AddCartView(request, name):
    obj = Product.objects.get(name = name)
    form = CartForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            data = form.save(commit=False)
            data.buyer = request.user
            data.product = obj
            data.price = obj.price
            data.save()
            return redirect("orders")
    context = {'form':form, 'obj':obj}
    return render(request, 'addcart.html', context)

def DetailView(request, pk):
    obj = Product.objects.all().get(id=pk)
    data = Review.objects.filter(product=obj)
    data_c = Review.objects.filter(product=obj).count()
    liked = False
    if obj.likes.filter(id=request.user.id).exists():
        liked = True
    context={'obj':obj, 'liked':liked, 'data':data, 'data_c':data_c}
    return render(request, 'detail.html', context)

def HomeView(request):    
    q = request.POST.get('q') if request.POST.get('q') != None else ''
    obj = Product.objects.filter( Q(search_tag1__icontains=q) | Q(search_tag2__icontains=q) | Q(search_tag3__icontains=q) | Q(category__name__icontains=q) | Q(name__icontains=q)).order_by('-date_updated')
    obj_c=Product.objects.all().count()
    data=Category.objects.all()
    data_c=Category.objects.all().count()
    context={'obj':obj, 'obj_c':obj_c, 'data_c':data_c, 'data':data}
    return render(request, 'index.html', context)
