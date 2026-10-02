from django.urls import path, include
from rest_framework.routers import DefaultRouter
from Tasks import views

from .views import (
    ProjectViewSet,
    TaskViewSet,
    project_list_view,
    my_tasks_view,
    create_project_view,
    create_task_view,
    update_task_status_view,
    suggest_project_ai_view,
    suggest_task_distribution_view,      
    confirm_task_distribution_view,      
)

router = DefaultRouter()
router.register(r'projetos', ProjectViewSet, basename='projeto')
router.register(r'tarefas', TaskViewSet, basename='tarefas')

urlpatterns = [
    path('meus-projetos/', project_list_view, name='project_list'),
    path('minhas-tarefas/', my_tasks_view, name='my_tasks'),
    path('projetos/novo/', create_project_view, name='project_create'),
    path('projetos/sugerir-ia/', suggest_project_ai_view, name='project_suggest_ai'),
    path('tarefas/novo/', create_task_view, name='task_create'),
    path('tarefas/<int:task_id>/status/', views.update_task_status_view, name='update_task_status'),
    path('projects/<int:project_id>/', views.project_detail, name='project_detail'),
    path('tarefas/<int:project_id>/sugerir-distribuicao/', suggest_task_distribution_view, name='task_suggest_distribution'),
    path('tarefas/<int:project_id>/confirmar-distribuicao/', confirm_task_distribution_view, name='task_confirm_distribution'),
    path('', include(router.urls)),
]