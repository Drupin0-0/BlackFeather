from django.urls import path

from .views import test_chat, chat_list_view


urlpatterns = [
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
]