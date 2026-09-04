from django.urls import path
from .views import CustomLoginView, dashboard_view,  RegisterView

app_name = 'accounts'

urlpatterns = [
    path('login/', CustomLoginView.as_view(), name='login'),
    path('dashboard/', dashboard_view, name='dashboard'),
    path('register/', RegisterView.as_view(), name='register'),
]