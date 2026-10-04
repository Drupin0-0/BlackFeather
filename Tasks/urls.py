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
    update_task_view,
    delete_task_view   , 
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
    path('tarefas/<int:task_id>/excluir/', delete_task_view, name='task_delete'),
    path('tarefas/<int:task_id>/editar/',  update_task_view, name='task_update'),
    path('projetos/<int:project_id>/configuracoes/', views.project_settings_view, name='project_settings'),
    path('projetos/<int:project_id>/membros/<int:user_id>/remover/', views.remove_member_view, name='project_member_remove'),
    path('projetos/<int:project_id>/membros/<int:user_id>/promover/', views.promote_member_view, name='project_member_promote'),
    path('projetos/<int:project_id>/membros/<int:user_id>/rebaixar/', views.demote_member_view, name='project_member_demote'),
    path('projetos/<int:project_id>/membros/<int:user_id>/permissoes/', views.update_member_permissions_view, name='project_member_permissions'),
    path('projetos/<int:project_id>/permissoes-padrao/', views.update_default_member_permissions_view, name='project_default_member_permissions'),
    path('projetos/<int:project_id>/transferir-posse/', views.transfer_ownership_view, name='project_transfer_ownership'),
    path('projetos/<int:project_id>/excluir/', views.delete_project_view, name='project_delete'),
    path('', include(router.urls)),
]