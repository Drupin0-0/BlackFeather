from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import ProjectViewSet, TaskViewSet

router = DefaultRouter()
router.register(r'projetos', ProjectViewSet, basename='projeto')
router.register(r'tarefas', TaskViewSet, basename='tarefas')

urlpatterns = [
    path('', include(router.urls)),
]