from django.urls import path
from .views import idd

urlpatterns = [
    path('', idd, name='idd'),
]
