from django.shortcuts import render, redirect
from django.views import View
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.password_validation import validate_password
from django.contrib import messages
from django.urls import reverse_lazy
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone
from django.http import JsonResponse
import secrets

from .forms import CustomUserCreationForm
from .services import enviar_email_codigo
from .models import UserProfile, Technology, CategoryChoices, AvatarBirdChoices
from Tasks.models import Project, ProjectMember, Task

User = get_user_model()

def grouped_technologies():
    techs = list(Technology.objects.order_by("name"))
    groups = []
    for value, label in CategoryChoices.choices:
        items = [t for t in techs if t.category == value]
        if items:
            groups.append({"category": label, "skills": items})
    return groups

class RegisterView(View):
    def get(self, request):
        form = CustomUserCreationForm()
        return render(request, 'registration/register.html', {'form': form})

    def post(self, request):
        form = CustomUserCreationForm(request.POST)

        if form.is_valid():
            user = form.save()
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            return redirect('accounts:setup_profile')

        return render(request, 'registration/register.html', {'form': form})


class CustomLoginView(LoginView):
    template_name = 'registration/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse_lazy('accounts:dashboard')


@login_required
def dashboard_view(request):
    projects = list(Project.objects.filter(
        Q(owner=request.user) | Q(members=request.user)
    ).select_related('owner__profile').prefetch_related('members__profile').distinct().order_by('-created_at'))
    memberships_by_project = {
        membership.project_id: membership
        for membership in ProjectMember.objects.filter(
            project_id__in=[project.pk for project in projects],
            user=request.user,
        )
    }
    for project in projects:
        membership = memberships_by_project.get(project.pk)
        project.can_create_tasks = (
            project.owner_id == request.user.pk
            or (
                membership is not None
                and (
                    membership.role == ProjectMember.Role.LEADER
                    or membership.can_create_tasks
                )
            )
        )

    tasks = Task.objects.filter(
        Q(project__owner=request.user) | Q(project__members=request.user)
    ).select_related(
        'project',
        'task_responsible',
        'task_responsible__profile'
    ).distinct().order_by('-created_at')
    task_items = list(tasks)
    for task in task_items:
        membership = memberships_by_project.get(task.project_id)
        is_leader = (
            membership is not None
            and membership.role == ProjectMember.Role.LEADER
        )
        is_boss = task.project.owner_id == request.user.pk
        task.can_edit = is_boss or is_leader or (
            membership is not None and membership.can_edit_tasks
        )
        task.can_delete = is_boss or is_leader or (
            membership is not None and membership.can_delete_tasks
        )

    today = timezone.localdate()
    yesterday = today - timezone.timedelta(days=1)

    statuses = [
        {'key': 'pending', 'label': 'Pendente', 'tasks': [task for task in task_items if task.status == 'pending']},
        {'key': 'in_progress', 'label': 'Em andamento', 'tasks': [task for task in task_items if task.status == 'in_progress']},
        {'key': 'completed', 'label': 'Concluída', 'tasks': [task for task in task_items if task.status == 'completed']},
    ]

    context = {
        'projects': projects,
        'unread_count': request.user.notifications.filter(is_read=False).count(),
        'projects_count': len(projects),
        'tasks_count': tasks.count(),
        'tasks_pending': tasks.filter(status='pending').count(),
        'tasks_in_progress': tasks.filter(status='in_progress').count(),
        'tasks_completed': tasks.filter(status='completed').count(),
        'tasks_today': tasks.filter(created_at__date=today).count(),
        'tasks_yesterday': tasks.filter(created_at__date=yesterday).count(),
        'kanban_columns': statuses,
        'can_create_any_task': any(project.can_create_tasks for project in projects),
    }

    return render(request, 'dashboard.html', context)


def solicitar_codigo_view(request):
    if request.method == 'POST':
        email = (request.POST.get('email') or '').strip().lower()
        rate_key = f'reset_request_rate_{email}'
        solicitations = cache.get(rate_key, 0)

        if solicitations >= 5:
            messages.error(request, 'Muitas solicitações, tente novamente mais tarde.')
            return redirect('accounts:solicitar_codigo')

        cache.set(rate_key, solicitations + 1, timeout=600)

        user = User.objects.filter(email=email).first()
        if user:
            codigo = f"{secrets.randbelow(900000) + 100000}"
            cache.set(f'reset_code_{email}', codigo, timeout=600)
            enviar_email_codigo(email, codigo)

        request.session['email_recuperacao'] = email
        messages.success(
            request,
            'Se houver uma conta associada a esse e-mail, enviaremos um código de recuperação.'
        )
        return redirect('accounts:verificar_codigo')

    return render(request, 'registration/solicitar_codigo.html')


def verificar_codigo_view(request):
    email = request.session.get('email_recuperacao')

    if not email:
        return redirect('accounts:solicitar_codigo')

        avatar_upload = request.FILES.get('avatar')
        if avatar_upload:
            if avatar_upload.size > 5 * 1024 * 1024:
                messages.error(request, 'A imagem do perfil deve ter no máximo 5 MB.')
                return redirect('accounts:view_profile')

            try:
                image_dimensions = get_image_dimensions(avatar_upload)
            except (OSError, ValueError):
                image_dimensions = None

            if not image_dimensions or avatar_upload.content_type not in {'image/jpeg', 'image/png', 'image/webp'}:
                messages.error(request, 'Envie uma imagem JPEG, PNG ou WebP válida.')
                return redirect('accounts:view_profile')

            extension = {
                'image/jpeg': '.jpg',
                'image/png': '.png',
                'image/webp': '.webp',
            }[avatar_upload.content_type]
            safe_avatar_path = f'avatars/profiles/{secrets.token_urlsafe(24)}{extension}'
            profile.avatar.save(safe_avatar_path, avatar_upload, save=False)
    if request.method == 'POST':
        codigo_digitado = request.POST.get('codigo')
        nova_senha = request.POST.get('nova_senha')
        confirmar_senha = request.POST.get('confirmar_senha')
        codigo_salvo = cache.get(f'reset_code_{email}')
        attempt_key = f'reset_attempts_{email}'
        attempts = cache.get(attempt_key, 0)

        if attempts >= 5:
            cache.delete(f'reset_code_{email}')
            messages.error(request, 'Muitas tentativas. Solicite um novo código de recuperação.')
            return redirect('accounts:solicitar_codigo')

        if not codigo_salvo or not codigo_digitado or not secrets.compare_digest(str(codigo_salvo), str(codigo_digitado)):
            cache.set(attempt_key, attempts + 1, timeout=600)
            messages.error(request, 'Código inválido ou expirado.')
        elif not nova_senha or nova_senha != confirmar_senha:
            messages.error(request, 'As senhas não coincidem.')
        else:
            user = User.objects.get(email=email)
            try:
                validate_password(nova_senha, user=user)
            except ValidationError as error:
                for message in error.messages:
                    messages.error(request, message)
            else:
                user.set_password(nova_senha)
                user.save()

                cache.delete(f'reset_code_{email}')
                cache.delete(attempt_key)
                del request.session['email_recuperacao']

                messages.success(request, 'Senha alterada com sucesso! Faça login.')
                return redirect('accounts:login')

    return render(request, 'registration/verificar_codigo.html')


@login_required
def delete_account_view(request):
    if request.method == "POST":
        user = request.user
        logout(request)
        user.delete()
        return redirect('accounts:login')

    return redirect('accounts:dashboard')


@login_required
def delete_account_page(request):
    return render(request, 'delete_account.html')


@login_required
def setup_profile_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()

        if not name:
            return render(request, 'profile/setup.html', {
                'profile': profile,
                'skill_catalog': grouped_technologies(),
                'error': 'O nome é obrigatório.',
            })

        profile.name = name
        profile.bio = (request.POST.get("bio") or "").strip()
        profile.birth_date = request.POST.get("birth_date") or None
        profile.save()

        selected_skills = [value.strip() for value in request.POST.getlist("skills") if value.strip()]
        skill_ids = [int(value) for value in selected_skills if value.isdigit()]
        skill_names = [value for value in selected_skills if not value.isdigit()]
        profile.skills.set(Technology.objects.filter(
            Q(pk__in=skill_ids) | Q(name__in=skill_names)
        ))

        return redirect('accounts:dashboard')

    return render(request, 'profile/setup.html', {
        'profile': profile,
        'skill_catalog': grouped_technologies(),
    })
@login_required
@require_POST
def bio_update(request):
    profile = request.user.profile
    bio = request.POST.get('bio', '').strip()
    
    if len(bio) > 500:
        return redirect('accounts:view_profile')
        
    profile.bio = bio
    profile.save(update_fields=['bio'])
    return redirect('accounts:view_profile')


@login_required
def search_users(request):
    query = (request.GET.get('q') or '').strip()

    users = User.objects.none()
    if '@' in query:
        users = User.objects.exclude(pk=request.user.pk).filter(
            email__iexact=query
        ).select_related('profile')[:1]

    results = []

    for user in users:
        profile = getattr(user, 'profile', None)
        skills = list(profile.skills.values_list('name', flat=True)) if profile else []

        results.append({
            'id': user.pk,
            'name': profile.name if profile else '',
            'email': user.email,
            'skills': skills,
            'bio': profile.bio if profile else '',
        })

    return JsonResponse({'results': results})


@login_required
def view_profile_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    def ctx(**extra):
        return {
            'profile': profile,
            'skills': profile.skills.all(),
            'skill_catalog': grouped_technologies(),
            **extra,
        }

    if request.method == 'POST':
        name = (request.POST.get('name') or '').strip()

        if not name:
            return render(request, 'profile/view_profile.html',
                          ctx(error='O nome é obrigatório.'))

        profile.name = name
        profile.bio = (request.POST.get('bio') or '').strip()
        profile.birth_date = request.POST.get('birth_date') or None
        profile.course_area = (request.POST.get('course_area') or '').strip()
        profile.website = (request.POST.get('website') or '').strip()
        avatar_bird = request.POST.get('avatar_bird')
        if avatar_bird in AvatarBirdChoices.values:
            profile.avatar_bird = avatar_bird

        profile.save()

        ids = [int(v) for v in request.POST.getlist('skills') if v.strip().isdigit()]
        profile.skills.set(Technology.objects.filter(pk__in=ids))

        return redirect('accounts:view_profile')

    return render(request, 'profile/view_profile.html', ctx())


@login_required
@require_POST
def logout_view(request):
    logout(request)
    return redirect("accounts:login")


@login_required
def settings_view(request):
    return render(request, 'settings.html')