from django.urls import path
from .views import (
    CustomLoginView,
    RegisterView,
    dashboard_view,
    setup_profile_view,
    solicitar_codigo_view,
    verificar_codigo_view,
    delete_account_view,
    delete_account_page,
    view_profile_view,
    search_users,
    logout_view,
    bio_update,
    settings_view,
)

app_name = "accounts"

urlpatterns = [
    path('', CustomLoginView.as_view(), name='login'),
    path('register/', RegisterView.as_view(), name='register'),

    path('logout/', logout_view, name='logout'),
    path('dashboard/', dashboard_view, name='dashboard'),
    path('configuracoes/', settings_view, name='settings'),

    path('buscar-usuarios/', search_users, name='search_users'),

    path('perfil/configurar/', setup_profile_view, name='setup_profile'),
    path('perfil/bio/', bio_update, name='update_biography'),

    # Fluxo de recuperação de senha
    path('esqueci-senha/', solicitar_codigo_view, name='solicitar_codigo'),
    path('verificar-codigo/', verificar_codigo_view, name='verificar_codigo'),

    # Exclusão de conta
    path('deletar-conta/', delete_account_page, name='delete_account_page'),
    path('deletar-conta/confirmar/', delete_account_view, name='delete_account'),

    path('perfil/', view_profile_view, name='view_profile'),
]
