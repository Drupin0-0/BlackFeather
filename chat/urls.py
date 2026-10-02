from django.urls import path

from .views import test_chat, chat_list_view, request_project_join
from . import direct_views

  
urlpatterns = [
    path("projetos/entrar/", request_project_join, name="request_project_join"),
    path(
        "lista/",
        chat_list_view,
        name="chat_list",
    ),
    path(
        "projetos/<str:project_code>/",
        test_chat,
        name="project_chat",
    ),
     path("privado/", direct_views.direct_list, name="direct_list"),
    path("privado/abrir/<int:user_id>/", direct_views.direct_open, name="direct_open"),
    
]