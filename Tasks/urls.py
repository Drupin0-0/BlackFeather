from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import ProjectViewSet, TaskViewSet, create_project_view, create_task_view, update_task_status_view

router = DefaultRouter()
router.register(r'projetos', ProjectViewSet, basename='projeto')
router.register(r'tarefas', TaskViewSet, basename='tarefas')

urlpatterns = [
    path('projetos/novo/', create_project_view, name='project_create'),
    path('tarefas/novo/', create_task_view, name='task_create'),
    path('tarefas/<int:task_id>/status/', update_task_status_view, name='task_update_status'),
    path('', include(router.urls)),
]