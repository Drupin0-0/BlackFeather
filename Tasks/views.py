import json
import os
import re
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied

from .models import Project, Task
from .serializers import ProjectSerializer, TaskSerializer
from accounts.models import UserProfile, Technology

User = get_user_model()


class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer

    def get_queryset(self):
        return Project.objects.filter(Q(owner=self.request.user) | Q(members=self.request.user))

    def perform_create(self, serializer):
        project = serializer.save(owner=self.request.user)
        project.members.add(self.request.user)


class TaskViewSet(viewsets.ModelViewSet):
    serializer_class = TaskSerializer

    def get_queryset(self):
        return Task.objects.filter(Q(project__owner=self.request.user) | Q(project__members=self.request.user))

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
            project = Project.objects.create(title=title, description=description, owner=request.user)
            project.members.add(request.user)

            selected_members = request.POST.getlist('members')
            if selected_members:
                selected_user_ids = [member_id for member_id in selected_members if member_id]
                members = User.objects.filter(pk__in=selected_user_ids).exclude(pk=request.user.pk)
                project.members.add(*members)

            return redirect('accounts:dashboard')

    return render(request, 'Project_add.html')


@login_required
def suggest_project_ai_view(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método inválido.'}, status=405)

    title = (request.POST.get('title') or '').strip()
    description = request.POST.get('description') or ''
    selected_members = request.POST.getlist('members')

    if not title:
        return JsonResponse({'error': 'O título do projeto é obrigatório.'}, status=400)

    users = User.objects.filter(pk__in=selected_members).select_related('profile').distinct() if selected_members else User.objects.none()
    owner_profile = getattr(request.user, 'profile', None)

    payload = {
        'project': {
            'title': title,
            'description': description,
            'owner': {
                'id': request.user.pk,
                'name': owner_profile.name if owner_profile else '',
                'email': request.user.email,
            }
        },
        'available_members': [
            {
                'id': user.pk,
                'name': user.profile.name if getattr(user, 'profile', None) else '',
                'email': user.email,
                'skills': list(user.profile.skills.values_list('name', flat=True)) if getattr(user, 'profile', None) else [],
            }
            for user in users
        ],
        'context': {
            'request_type': 'member_assignment',
            'project_stage': 'planning'
        }
    }

    n8n_url = os.getenv('N8N_WEBHOOK_URL')

    if n8n_url:
        try:
            req = Request(n8n_url, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json', 'Accept': 'application/json'}, method='POST')
            with urlopen(req, timeout=30) as response:
                n8n_response = json.loads(response.read().decode('utf-8'))
                if isinstance(n8n_response, dict):
                    return JsonResponse(n8n_response)
        except (URLError, HTTPError, ValueError, TimeoutError):
            pass

    project_text = f"{title} {description}".lower()
    search_terms = set(re.findall(r"[a-zA-ZÀ-ÖØ-öø-ÿ]+", project_text))

    suggestions = []

    for user in users:
        profile = getattr(user, 'profile', None)
        skill_names = list(profile.skills.values_list('name', flat=True)) if profile else []
        matched = []

        for skill in skill_names:
            skill_lower = skill.lower()
            if any(skill_lower in term.lower() or term.lower() in skill_lower for term in search_terms):
                matched.append(skill)

        score = len(matched) + (1 if profile and profile.bio else 0)

        suggestions.append({
            'user_id': user.pk,
            'name': profile.name if profile else '',
            'email': user.email,
            'score': score,
            'matched_skills': matched,
            'skills': skill_names,
        })

    suggestions = sorted(suggestions, key=lambda item: item['score'], reverse=True)

    return JsonResponse({
        'status': 'success',
        'suggestions': suggestions,
        'payload_ready_for_n8n': payload,
    })


@login_required
def create_task_view(request):
    user_projects = Project.objects.filter(Q(owner=request.user) | Q(members=request.user)).distinct().order_by('title')

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

        Task.objects.create(
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

    return JsonResponse({'success': True, 'task_id': task.pk, 'status': task.status})


@login_required
def setup_profile_view(request):
    profile, created = UserProfile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        name = (request.POST.get('name') or '').strip()

        if not name:
            return render(request, 'accounts/setup.html', {'profile': profile, 'error': 'O nome é obrigatório.'})

        profile.name = name
        profile.bio = (request.POST.get('bio') or '').strip()
        profile.birth_date = request.POST.get('birth_date') or None
        profile.save()

        skills_selected = request.POST.getlist('skills')
        skill_objects = []

        for tech_name in skills_selected:
            tech_name = tech_name.strip()
            if not tech_name:
                continue

            tech, _ = Technology.objects.get_or_create(name=tech_name)
            skill_objects.append(tech)

        profile.skills.set(skill_objects)

        return redirect('accounts:dashboard')

    return render(request, 'accounts/setup.html', {'profile': profile})