from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import ProjectViewSet, TaskViewSet, create_project_view

router = DefaultRouter()
router.register(r'projetos', ProjectViewSet, basename='projeto')
router.register(r'tarefas', TaskViewSet, basename='tarefas')

urlpatterns = [
    path('projetos/novo/', create_project_view, name='project_create'),
    path('', include(router.urls)),
]