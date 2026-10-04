import json
import os
import re
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q, Count
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from Tasks.ai_service import gerar_tarefas_para_projeto
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from .models import Project, ProjectMember, Task
from .serializers import ProjectSerializer, TaskSerializer
from accounts.models import UserProfile, Technology
from chat.models import JoinRequest
from chat.notification_service import create_notification

User = get_user_model()


def _n8n_headers():
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
    secret = os.getenv('N8N_WEBHOOK_SECRET')
    if secret:
        headers['X-Webhook-Secret'] = secret
    return headers


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
def my_tasks_view(request):
    today = timezone.localdate()
    tomorrow = today + timezone.timedelta(days=1)
    week_end = today + timezone.timedelta(days=7)

    base_qs = Task.objects.filter(
        task_responsible=request.user
    ).select_related('project').order_by('deadline', 'created_at')

    pending_qs = base_qs.exclude(status='completed')

    buckets = {
        'overdue': [],
        'today': [],
        'tomorrow': [],
        'week': [],
        'later': [],
        'no_deadline': [],
    }

    for task in pending_qs:
        if not task.deadline:
            buckets['no_deadline'].append(task)
        elif task.deadline < today:
            buckets['overdue'].append(task)
        elif task.deadline == today:
            buckets['today'].append(task)
        elif task.deadline == tomorrow:
            buckets['tomorrow'].append(task)
        elif task.deadline <= week_end:
            buckets['week'].append(task)
        else:
            buckets['later'].append(task)

    sections = [
        {'key': 'overdue', 'label': 'Atrasadas', 'tone': 'danger', 'tasks': buckets['overdue']},
        {'key': 'today', 'label': 'Hoje', 'tone': 'today', 'tasks': buckets['today']},
        {'key': 'tomorrow', 'label': 'Amanhã', 'tone': 'default', 'tasks': buckets['tomorrow']},
        {'key': 'week', 'label': 'Essa semana', 'tone': 'default', 'tasks': buckets['week']},
        {'key': 'later', 'label': 'Mais pra frente', 'tone': 'muted', 'tasks': buckets['later']},
        {'key': 'no_deadline', 'label': 'Sem prazo definido', 'tone': 'muted', 'tasks': buckets['no_deadline']},
    ]

    recently_completed = base_qs.filter(
        status='completed'
    ).order_by('-updated_at')[:8]

    context = {
        'sections': sections,
        'recently_completed': recently_completed,
        'pending_total': pending_qs.count(),
    }

    return render(request, 'minhas_tarefas.html', context)


@login_required
def project_list_view(request):
    projects = Project.objects.filter(
        Q(owner=request.user) | Q(members=request.user)
    ).select_related(
        'owner__profile'
    ).prefetch_related(
        'members__profile'
    ).annotate(
        members_count=Count('members', distinct=True)
    ).distinct().order_by('-created_at')

    return render(request, 'projetos.html', {'projects': projects})


@login_required
def create_project_view(request):
    if request.method == 'POST':
        title = (request.POST.get('title') or '').strip()
        description = (request.POST.get('description') or '').strip()
        category = request.POST.get('category', 'general')
        allowed_categories = {value for value, _label in Project.CATEGORY_CHOICES}
        if category not in allowed_categories:
            category = 'general'

        accent_color = (request.POST.get('accent_color') or '#a3c7ff').strip()
        if request.POST.get('use_default_color') == 'on' or not re.fullmatch(r'#[0-9a-fA-F]{6}', accent_color):
            accent_color = '#a3c7ff'

        if title:
            project = Project.objects.create(
                title=title,
                description=description,
                category=category,
                accent_color=accent_color.lower(),
                owner=request.user,
            )
            project.members.add(request.user)

            selected_members = request.POST.getlist('members')
            if selected_members:
                selected_user_ids = [member_id for member_id in selected_members if member_id]
                members = User.objects.filter(pk__in=selected_user_ids).exclude(pk=request.user.pk)
                for member in members:
                    join_request, created = JoinRequest.objects.get_or_create(
                        sender=request.user,
                        recipient=member,
                        project=project,
                        status='pending',
                    )
                    if created:
                        create_notification(
                            user=member,
                            title="Convite para projeto",
                            description=(
                                f"{request.user.email} convidou você para "
                                f"participar do projeto '{project.title}'."
                            ),
                            join_request=join_request,
                        )

            if request.POST.get('generate_tasks_ai') == 'on':
                criadas = gerar_tarefas_para_projeto(project)
                if criadas:
                    messages.success(request, f'{criadas} tarefas geradas pela IA.')
                else:
                    messages.warning(request, 'Projeto criado, mas a IA não conseguiu gerar tarefas.')

            return redirect('accounts:dashboard')

    return render(request, 'Project_add.html', {
        'category_choices': Project.CATEGORY_CHOICES,
    })


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
            req = Request(n8n_url, data=json.dumps(payload).encode('utf-8'), headers=_n8n_headers(), method='POST')
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
def suggest_task_distribution_view(request, project_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método inválido.'}, status=405)

    project = get_object_or_404(Project, pk=project_id)

    if project.owner != request.user and request.user not in project.members.all():
        return JsonResponse({'error': 'Você não tem acesso a este projeto.'}, status=403)

    descricoes = request.POST.getlist('task_description')
    tasks_payload = [
        {'temp_id': i, 'description': desc.strip()}
        for i, desc in enumerate(descricoes) if desc.strip()
    ]

    if not tasks_payload:
        return JsonResponse({'error': 'Informe ao menos uma tarefa.'}, status=400)

    membros = project.members.all().select_related('profile')
    membros_validos_ids = set(membros.values_list('pk', flat=True))

    payload = {
        'project': {
            'id': project.pk,
            'title': project.title,
            'description': project.description or '',
        },
        'tasks': tasks_payload,
        'context': {'request_type': 'task_distribution'},
        'available_members': [
            {
                'id': user.pk,
                'name': user.profile.name if getattr(user, 'profile', None) else '',
                'skills': list(user.profile.skills.values_list('name', flat=True)) if getattr(user, 'profile', None) else [],
            }
            for user in membros
        ],
    }

    n8n_url = os.getenv('N8N_WEBHOOK_URL')
    n8n_secret = os.getenv('N8N_WEBHOOK_SECRET')
    assignments = None

    if n8n_url:
        try:
            req = Request(
                n8n_url,
                data=json.dumps(payload).encode('utf-8'),
                headers=_n8n_headers(),
                method='POST'
            )
            with urlopen(req, timeout=45) as response:
                n8n_response = json.loads(response.read().decode('utf-8'))
                assignments = _validar_resposta_ia(n8n_response, tasks_payload, membros_validos_ids)
        except (URLError, HTTPError, ValueError, TimeoutError):
            assignments = None

    # Fallback local: matching simples por palavra-chave nas skills
    if assignments is None:
        assignments = []
        membros_lista = list(membros)

        for task in tasks_payload:
            desc_lower = task['description'].lower()
            melhor_membro = None
            melhor_score = -1

            for user in membros_lista:
                profile = getattr(user, 'profile', None)
                skills = list(profile.skills.values_list('name', flat=True)) if profile else []
                score = sum(1 for skill in skills if skill.lower() in desc_lower)

                if score > melhor_score:
                    melhor_score = score
                    melhor_membro = user

            if melhor_membro:
                assignments.append({
                    'temp_id': task['temp_id'],
                    'assigned_user_id': melhor_membro.pk,
                    'priority': 'medium',
                })

    request.session[f'ai_task_suggestion_{project.pk}'] = {
        'tasks': tasks_payload,
        'assignments': assignments,
    }

    return JsonResponse({
        'status': 'success',
        'tasks': tasks_payload,
        'assignments': assignments,
    })


@login_required
def confirm_task_distribution_view(request, project_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método inválido.'}, status=405)

    project = get_object_or_404(Project, pk=project_id)

    if project.owner != request.user and request.user not in project.members.all():
        return JsonResponse({'error': 'Você não tem acesso a este projeto.'}, status=403)

    session_key = f'ai_task_suggestion_{project.pk}'
    dados = request.session.get(session_key)

    if not dados:
        return JsonResponse({'error': 'Sugestão expirada ou não encontrada. Gere novamente.'}, status=400)

    tasks_por_id = {t['temp_id']: t for t in dados['tasks']}
    membros_validos_ids = set(project.members.values_list('pk', flat=True))
    criadas = []

    for item in dados['assignments']:
        task_info = tasks_por_id.get(item['temp_id'])
        if not task_info:
            continue

        responsavel_id = item.get('assigned_user_id')
        if responsavel_id not in membros_validos_ids:
            responsavel_id = None

        task = Task.objects.create(
            project=project,
            title=task_info['description'][:100],
            description=task_info['description'],
            priority=item.get('priority', 'medium'),
            task_responsible_id=responsavel_id,
        )
        criadas.append(task.pk)

    del request.session[session_key]
    

    return JsonResponse({'status': 'success', 'created_task_ids': criadas})

def _validar_resposta_ia(data, tasks_enviadas, membros_validos_ids):
    """Valida a resposta da IA (N8N) antes de confiar nela."""
    if not isinstance(data, dict) or 'assignments' not in data:
        return None

    temp_ids_enviados = {t['temp_id'] for t in tasks_enviadas}
    resultado = []

    for item in data.get('assignments', []):
        if not isinstance(item, dict):
            continue
        if item.get('temp_id') not in temp_ids_enviados:
            continue
        if item.get('assigned_user_id') not in membros_validos_ids:
            continue

        resultado.append({
            'temp_id': item['temp_id'],
            'assigned_user_id': item['assigned_user_id'],
            'priority': item.get('priority') if item.get('priority') in ('low', 'medium', 'high') else 'medium',
        })

    return resultado if resultado else None

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
        if not project.user_can(request.user, 'can_create_tasks'):
            return JsonResponse(
                {'error': 'Você não tem permissão para criar tarefas neste projeto.'},
                status=403,
            )

        Task.objects.create(
            project=project,
            title=title,
            description=description or '',
            status=status,
            priority=priority,
            deadline=deadline or None,
            task_responsible=project.members.filter(pk=responsible_id).first() if responsible_id else None,
        )
        if request.POST.get('from_project') == '1':
                return redirect('project_detail', project_id=project.pk)

        return redirect('accounts:dashboard')

    return render(request, 'task_create.html', {'projects': user_projects})


@login_required
def update_task_status_view(request, task_id):
    task = get_object_or_404(Task, pk=task_id)

    if task.project.owner != request.user and request.user not in task.project.members.all():
        return JsonResponse({'error': 'Você não tem acesso a esta tarefa.'}, status=403)

    if not task.project.user_can(request.user, 'can_edit_tasks'):
        return JsonResponse(
            {'error': 'Você não tem permissão para editar tarefas neste projeto.'},
            status=403,
        )

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

@login_required
def project_detail(request, project_id):
    project = get_object_or_404(
        Project.objects.select_related('owner'),
        pk=project_id
    )

    if (
        request.user != project.owner
        and not project.members.filter(pk=request.user.pk).exists()
    ):
        return redirect('project_list')

    tasks = (
        Task.objects
        .filter(project=project)
        .select_related(
            'task_responsible',
            'task_responsible__profile'
        )
        .order_by('created_at')
    )

    kanban_columns = [
        {
            'key': 'pending',
            'label': 'A fazer',
            'tasks': tasks.filter(status='pending'),
        },
        {
            'key': 'in_progress',
            'label': 'Em andamento',
            'tasks': tasks.filter(status='in_progress'),
        },
        {
            'key': 'completed',
            'label': 'Concluído',
            'tasks': tasks.filter(status='completed'),
        },
    ]

    return render(
        request,
        'project_detail.html',
        {
            'project': project,
            'kanban_columns': kanban_columns,
            'can_create': project.user_can(request.user, 'can_create_tasks'),
            'can_edit': project.user_can(request.user, 'can_edit_tasks'),
            'can_delete': project.user_can(request.user, 'can_delete_tasks'),
            'can_manage_settings': project.can_manage_settings(request.user),
        }
    )


def _get_user_project(request, project_id):
    return get_object_or_404(
        Project.objects.filter(
            Q(owner=request.user) | Q(members=request.user)
        ).distinct(),
        pk=project_id,
    )


def _get_project_member(project, user_id):
    return get_object_or_404(
        project.members.exclude(pk=project.owner_id),
        pk=user_id,
    )


@login_required
def project_settings_view(request, project_id):
    project = _get_user_project(request, project_id)
    if not project.can_manage_settings(request.user):
        return redirect('project_detail', project_id=project.pk)

    memberships = list(
        project.memberships
        .exclude(user_id=project.owner_id)
        .select_related('user__profile')
        .order_by('role', 'user__email')
    )
    permission_labels = (
        ('can_create_tasks', 'Permitir criação de tarefas'),
        ('can_delete_tasks', 'Permitir exclusão de tarefas'),
        ('can_edit_tasks', 'Permitir edição de tarefas'),
        ('can_create_boards', 'Criação de novos quadros (em breve, sem efeito por enquanto)'),
        ('can_invite_members', 'Convidar novos integrantes'),
    )
    for membership in memberships:
        membership.permission_rows = [
            (permission, label, getattr(membership, permission))
            for permission, label in permission_labels
        ]
    project.default_permission_rows = [
        (permission, label, getattr(project, f'default_{permission}'))
        for permission, label in permission_labels
    ]
    return render(
        request,
        'project_settings.html',
        {
            'project': project,
            'memberships': memberships,
            'is_boss': project.is_boss(request.user),
            'role_labels': {
                'boss': 'Chefe',
                ProjectMember.Role.LEADER: 'Líder',
                ProjectMember.Role.MEMBER: 'Integrante',
            },
        },
    )


@login_required
@require_POST
def update_default_member_permissions_view(request, project_id):
    project = _get_user_project(request, project_id)
    if not project.is_boss(request.user):
        return JsonResponse(
            {'error': 'Apenas o Chefe pode alterar as permissões padrão deste projeto.'},
            status=403,
        )

    permission_values = {}
    for permission in ProjectMember.PERMISSION_FIELDS:
        raw_value = request.POST.get(permission)
        if raw_value not in {'true', 'false', '1', '0', 'on', 'off'}:
            return JsonResponse(
                {'error': f'Valor inválido para a permissão {permission}.'},
                status=400,
            )
        permission_values[f'default_{permission}'] = raw_value in {'true', '1', 'on'}

    for permission, value in permission_values.items():
        setattr(project, permission, value)
    project.save(update_fields=list(permission_values))
    return JsonResponse({'success': True})


@login_required
@require_POST
def remove_member_view(request, project_id, user_id):
    project = _get_user_project(request, project_id)
    if not project.is_boss(request.user):
        return JsonResponse(
            {'error': 'Apenas o Chefe pode remover integrantes.'},
            status=403,
        )
    if user_id == request.user.pk:
        return JsonResponse(
            {'error': 'O Chefe não pode remover a si mesmo.'},
            status=400,
        )

    member = _get_project_member(project, user_id)
    Task.objects.filter(
        project=project,
        task_responsible=member,
    ).update(task_responsible=None)
    project.members.remove(member)
    ProjectMember.objects.filter(project=project, user=member).delete()
    return JsonResponse({'success': True})


@login_required
@require_POST
def promote_member_view(request, project_id, user_id):
    project = _get_user_project(request, project_id)
    if not project.is_boss(request.user):
        return JsonResponse(
            {'error': 'Apenas o Chefe pode promover integrantes.'},
            status=403,
        )

    member = _get_project_member(project, user_id)
    membership, _ = ProjectMember.objects.get_or_create(
        project=project,
        user=member,
    )
    if membership.role == ProjectMember.Role.LEADER:
        return JsonResponse(
            {'error': 'Este integrante já é Líder.'},
            status=400,
        )

    membership.role = ProjectMember.Role.LEADER
    membership.save(update_fields=['role'])
    return JsonResponse({'success': True})


@login_required
@require_POST
def demote_member_view(request, project_id, user_id):
    project = _get_user_project(request, project_id)
    if not project.is_boss(request.user):
        return JsonResponse(
            {'error': 'Apenas o Chefe pode rebaixar Líderes.'},
            status=403,
        )

    member = _get_project_member(project, user_id)
    membership = get_object_or_404(
        ProjectMember,
        project=project,
        user=member,
    )
    if membership.role != ProjectMember.Role.LEADER:
        return JsonResponse(
            {'error': 'Este integrante não é Líder.'},
            status=400,
        )

    membership.role = ProjectMember.Role.MEMBER
    membership.save(update_fields=['role'])
    return JsonResponse({'success': True})


@login_required
@require_POST
def update_member_permissions_view(request, project_id, user_id):
    project = _get_user_project(request, project_id)
    is_boss = project.is_boss(request.user)
    if not is_boss and not project.is_leader(request.user):
        return JsonResponse(
            {'error': 'Você não pode alterar permissões deste projeto.'},
            status=403,
        )

    if user_id == project.owner_id:
        return JsonResponse(
            {'error': 'As permissões do Chefe não podem ser alteradas.'},
            status=403,
        )

    member = _get_project_member(project, user_id)
    membership, _ = ProjectMember.objects.get_or_create(
        project=project,
        user=member,
    )
    if not is_boss and membership.role != ProjectMember.Role.MEMBER:
        return JsonResponse(
            {'error': 'Líderes só podem alterar permissões de Integrantes.'},
            status=403,
        )

    permission_values = {}
    for permission in ProjectMember.PERMISSION_FIELDS:
        raw_value = request.POST.get(permission)
        if raw_value not in {'true', 'false', '1', '0', 'on', 'off'}:
            return JsonResponse(
                {'error': f'Valor inválido para a permissão {permission}.'},
                status=400,
            )
        permission_values[permission] = raw_value in {'true', '1', 'on'}

    for permission, value in permission_values.items():
        setattr(membership, permission, value)
    membership.save(update_fields=list(permission_values))
    return JsonResponse({'success': True})


@login_required
@require_POST
def transfer_ownership_view(request, project_id):
    project = _get_user_project(request, project_id)
    if not project.is_boss(request.user):
        return JsonResponse(
            {'error': 'Apenas o Chefe pode transferir a posse do projeto.'},
            status=403,
        )

    new_owner_id = request.POST.get('new_owner_id')
    new_owner = get_object_or_404(
        project.members.exclude(pk=project.owner_id),
        pk=new_owner_id,
    )
    if request.POST.get('confirmation') != 'on':
        return JsonResponse(
            {'error': 'Confirme a transferência de posse.'},
            status=400,
        )

    previous_owner = request.user
    with transaction.atomic():
        ProjectMember.objects.filter(
            project=project,
            user=new_owner,
        ).delete()
        project.owner = new_owner
        project.save(update_fields=['owner'])
        project.members.add(previous_owner)
        ProjectMember.objects.update_or_create(
            project=project,
            user=previous_owner,
            defaults={'role': ProjectMember.Role.MEMBER},
        )
    return JsonResponse({'success': True})


@login_required
@require_POST
def delete_project_view(request, project_id):
    project = _get_user_project(request, project_id)
    if not project.is_boss(request.user):
        return JsonResponse(
            {'error': 'Apenas o Chefe pode excluir o projeto.'},
            status=403,
        )
    if request.POST.get('confirmation') != 'on':
        return JsonResponse(
            {'error': 'Confirme a exclusão do projeto.'},
            status=400,
        )

    project.delete()
    return redirect('project_list')


def _get_user_task(request, task_id):
    """Só devolve a tarefa se o usuário for dono ou membro do projeto."""
    queryset = Task.objects.filter(
        Q(project__owner=request.user) | Q(project__members=request.user)
    ).distinct()
    return get_object_or_404(queryset, pk=task_id)


@login_required
@require_POST
def delete_task_view(request, task_id):
    task = _get_user_task(request, task_id)
    if not task.project.user_can(request.user, 'can_delete_tasks'):
        return JsonResponse(
            {'error': 'Você não tem permissão para excluir tarefas neste projeto.'},
            status=403,
        )
    task.delete()
    return JsonResponse({'success': True, 'task_id': task_id})


@login_required
@require_POST
def update_task_view(request, task_id):
    task = _get_user_task(request, task_id)
    if not task.project.user_can(request.user, 'can_edit_tasks'):
        return JsonResponse(
            {'error': 'Você não tem permissão para editar tarefas neste projeto.'},
            status=403,
        )

    title = request.POST.get('title', '').strip()[:100]
    if title:
        task.title = title

    task.description = request.POST.get('description', '').strip() or None

    valid_statuses = {c[0] for c in Task._meta.get_field('status').choices}
    status = request.POST.get('status')
    if status in valid_statuses:
        task.status = status

    valid_priorities = {c[0] for c in Task._meta.get_field('priority').choices}
    priority = request.POST.get('priority')
    if priority in valid_priorities:
        task.priority = priority

    raw_deadline = request.POST.get('deadline', '').strip()
    if raw_deadline:
        try:
            parsed = parse_date(raw_deadline)
        except ValueError:
            parsed = None
        if parsed:
            task.deadline = parsed
    else:
        task.deadline = None

    responsible_id = request.POST.get('task_responsible')
    task.task_responsible = (
        task.project.members.filter(pk=responsible_id).first()
        if responsible_id else None
    )

    task.save()
    if request.POST.get('from_dashboard') == '1':
        return redirect('accounts:dashboard')
    return redirect('project_detail', project_id=task.project_id)