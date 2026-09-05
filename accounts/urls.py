from django.urls import path
from .views import (
    CustomLoginView, 
    dashboard_view, 
    RegisterView, 
    solicitar_codigo_view, 
    verificar_codigo_view
)

app_name = "accounts"

urlpatterns = [
    path('login/', CustomLoginView.as_view(), name='login'),
    path('dashboard/', dashboard_view, name='dashboard'),
    path('register/', RegisterView.as_view(), name='register'),
    
    # Novas rotas de recuperação de senha com código
    path('esqueci-senha/', solicitar_codigo_view, name='solicitar_codigo'),
    path('verificar-codigo/', verificar_codigo_view, name='verificar_codigo'),
]
