from django.shortcuts import render, redirect
from django.views import View
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model, login, logout
from django.contrib import messages
from django.urls import reverse_lazy
from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone
from django.http import JsonResponse
import secrets

from .forms import CustomUserCreationForm
from .services import enviar_email_codigo
from .models import UserProfile, Technology
from Tasks.models import Project, Task

User = get_user_model()


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
    projects = Project.objects.filter(
        Q(owner=request.user) | Q(members=request.user)
    ).select_related('owner__profile').prefetch_related('members__profile').distinct().order_by('-created_at')

    tasks = Task.objects.filter(
        Q(project__owner=request.user) | Q(project__members=request.user)
    ).select_related(
        'project',
        'task_responsible',
        'task_responsible__profile'
    ).distinct().order_by('-created_at')

    today = timezone.localdate()
    yesterday = today - timezone.timedelta(days=1)

    statuses = [
        {'key': 'pending', 'label': 'Pendente', 'tasks': tasks.filter(status='pending').order_by('-created_at')},
        {'key': 'in_progress', 'label': 'Em andamento', 'tasks': tasks.filter(status='in_progress').order_by('-created_at')},
        {'key': 'completed', 'label': 'Concluída', 'tasks': tasks.filter(status='completed').order_by('-created_at')},
    ]

    context = {
        'projects': projects,
        'projects_count': projects.count(),
        'tasks_count': tasks.count(),
        'tasks_pending': tasks.filter(status='pending').count(),
        'tasks_in_progress': tasks.filter(status='in_progress').count(),
        'tasks_completed': tasks.filter(status='completed').count(),
        'tasks_today': tasks.filter(created_at__date=today).count(),
        'tasks_yesterday': tasks.filter(created_at__date=yesterday).count(),
        'kanban_columns': statuses,
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

        if User.objects.filter(email=email).exists():
            codigo = f"{secrets.randbelow(900000) + 100000}"
            cache.set(f'reset_code_{email}', codigo, timeout=600)
            enviar_email_codigo(email, codigo)

            request.session['email_recuperacao'] = email
            messages.success(request, 'Código enviado para o seu e-mail!')
            return redirect('accounts:verificar_codigo')

        messages.error(request, 'E-mail não encontrado no sistema.')

    return render(request, 'registration/solicitar_codigo.html')


def verificar_codigo_view(request):
    email = request.session.get('email_recuperacao')

    if not email:
        return redirect('accounts:solicitar_codigo')

    if request.method == 'POST':
        codigo_digitado = request.POST.get('codigo')
        nova_senha = request.POST.get('nova_senha')
        confirmar_senha = request.POST.get('confirmar_senha')
        codigo_salvo = cache.get(f'reset_code_{email}')

        if not codigo_salvo or codigo_salvo != codigo_digitado:
            messages.error(request, 'Código inválido ou expirado.')
        elif nova_senha != confirmar_senha:
            messages.error(request, 'As senhas não coincidem.')
        elif len(nova_senha) < 8:
            messages.error(request, 'A senha deve ter pelo menos 8 caracteres.')
        else:
            user = User.objects.get(email=email)
            user.set_password(nova_senha)
            user.save()

            cache.delete(f'reset_code_{email}')
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
    profile, created = UserProfile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()

        if not name:
            return render(request, 'profile/setup.html', {
                'profile': profile,
                'error': 'O nome é obrigatório.'
            })

        profile.name = name
        profile.bio = (request.POST.get("bio") or "").strip()
        profile.birth_date = request.POST.get("birth_date") or None
        profile.save()

        skills_selected = request.POST.getlist("skills")
        skill_objects = []

        for tech_name in skills_selected:
            tech_name = tech_name.strip()

            if not tech_name:
                continue

            tech, _ = Technology.objects.get_or_create(name=tech_name)
            skill_objects.append(tech)

        profile.skills.set(skill_objects)

        return redirect('accounts:dashboard')

    return render(request, 'profile/setup.html', {'profile': profile})


@login_required
def search_users(request):
    query = (request.GET.get('q') or '').strip()

    users = User.objects.exclude(pk=request.user.pk).select_related('profile')

    if query:
        users = users.filter(
            Q(profile__name__icontains=query) |
            Q(email__icontains=query)
        ).distinct()[:10]
    else:
        users = users[:10]

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
    profile, created = UserProfile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        name = (request.POST.get('name') or '').strip()

        if not name:
            return render(request, 'profile/view_profile.html', {
                'profile': profile,
                'error': 'O nome é obrigatório.'
            })

        profile.name = name
        profile.bio = (request.POST.get('bio') or '').strip()
        profile.birth_date = request.POST.get('birth_date') or None
        profile.course_area = (request.POST.get('course_area') or '').strip()
        profile.website = (request.POST.get('website') or '').strip()

        if request.POST.get('remove_avatar') == '1':
            if profile.avatar:
                profile.avatar.delete(save=False)
            profile.avatar = None
        elif request.FILES.get('avatar'):
            if profile.avatar:
                profile.avatar.delete(save=False)
            profile.avatar = request.FILES['avatar']

        profile.save()

        return redirect('accounts:view_profile')

    return render(request, 'profile/view_profile.html', {'profile': profile})