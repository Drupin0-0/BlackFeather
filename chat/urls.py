from django.urls import path

from .views import test_chat


urlpatterns = [
    path(
        "projetos/<str:project_code>/",
        test_chat,
        name="project_chat",
    ),
]