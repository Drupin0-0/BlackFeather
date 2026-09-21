from django.urls import path

from .views import test_chat


urlpatterns = [
    path(
        "projetos/<int:project_id>/",
        test_chat,
        name="project_chat",
    ),
]