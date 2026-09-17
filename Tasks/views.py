from django.db.models import Q
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from django.http import JsonResponse
from .models import Project, Task
from .serializers import ProjectSerializer, TaskSerializer
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Project

class ProjectViewSet(viewsets.ModelViewSet):

    serializer_class = ProjectSerializer

    def get_queryset(self):
        return Project.objects.filter(
            Q(owner=self.request.user) | Q(members=self.request.user)
        )

    def perform_create(self, serializer):
        project = serializer.save(owner=self.request.user)
        project.members.add(self.request.user)
class TaskViewSet(viewsets.ModelViewSet):
    serializer_class = TaskSerializer
    def get_queryset(self):
        return Task.objects.filter(
            Q(project__owner=self.request.user) | Q(project__members=self.request.user)
        )   
    def perform_create(self, serializer):
        project = serializer.validated_data['project']
        if not (project.owner == self.request.user or self.request.user in project.members.all()):
            raise PermissionDenied("Você não tem acesso a esse projeto.")
        serializer.save()

@login_required
def create_project_view(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description')
        
        if title:
            # Cria o projeto definindo o dono e adicionando aos membros
            project = Project.objects.create(
                title=title,
                description=description,
                owner=request.user
            )
            project.members.add(request.user)
            return redirect('accounts:dashboard')  # Redireciona de volta para o painel
            
    return render(request, 'Project_add.html')


@login_required
def create_task_view(request):
    user_projects = Project.objects.filter(
        Q(owner=request.user) | Q(members=request.user)
    ).distinct().order_by('title')

    if request.method == 'POST':
        project_id = request.POST.get('project')
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        status = request.POST.get('status', 'pending')
        priority = request.POST.get('priority', 'medium')
        deadline = request.POST.get('deadline')
        responsible_id = request.POST.get('task_responsible')

        if not title or not project_id:
            return redirect('accounts:dashboard')

        project = get_object_or_404(Project, pk=project_id)
        if project.owner != request.user and request.user not in project.members.all():
            return redirect('accounts:dashboard')

        task = Task.objects.create(
            project=project,
            title=title,
            description=description or '',
            status=status,
            priority=priority,
            deadline=deadline or None,
            task_responsible=project.members.filter(pk=responsible_id).first() if responsible_id else None,
        )

        return redirect('accounts:dashboard')

    return render(request, 'task_create.html', {'projects': user_projects})


@login_required
def update_task_status_view(request, task_id):
    task = get_object_or_404(Task, pk=task_id)

    if task.project.owner != request.user and request.user not in task.project.members.all():
        return JsonResponse({'error': 'Você não tem acesso a esta tarefa.'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'error': 'Método inválido.'}, status=405)

    status = request.POST.get('status')
    valid_statuses = {choice[0] for choice in Task._meta.get_field('status').choices}

    if status not in valid_statuses:
        return JsonResponse({'error': 'Status inválido.'}, status=400)

    task.status = status
    task.save(update_fields=['status', 'updated_at'])

    return JsonResponse({
        'success': True,
        'task_id': task.pk,
        'status': task.status,
    })