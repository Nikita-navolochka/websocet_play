from django.shortcuts import render

# Create your views here.


def idd(request):
    return render(request, "play/idd.html")