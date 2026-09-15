from django.urls import path
from django.contrib.auth.views import LogoutView
from .views import (
    CustomLoginView,
    dashboard_view,
    RegisterView,
    solicitar_codigo_view,
    verificar_codigo_view,
    delete_account_view,
    delete_account_page,
)

app_name = "accounts"

urlpatterns = [
    path('', CustomLoginView.as_view(), name='login'),
    path('dashboard/', dashboard_view, name='dashboard'),
    path('register/', RegisterView.as_view(), name='register'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('esqueci-senha/', solicitar_codigo_view, name='solicitar_codigo'),
    path('verificar-codigo/', verificar_codigo_view, name='verificar_codigo'),
    path('deletar-conta/', delete_account_page, name='delete_account_page'),
    path('deletar-conta/confirmar/', delete_account_view, name='delete_account'),
]

