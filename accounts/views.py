from django.shortcuts import render, redirect
from django.views import View
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.urls import reverse_lazy
from django.core.cache import cache
import secrets
from django.contrib.auth import logout
from .forms import CustomUserCreationForm
from .services import enviar_email_codigo
from .models import UserProfile
from django.contrib.auth import login
from django.db.models import Q
from django.utils import timezone
from django.http import JsonResponse
User = get_user_model()
from .models import UserProfile, Technology  
from Tasks.models import Project, Task
from django.core.cache import cache

class RegisterView(View):

    def get(self, request):
        form = CustomUserCreationForm()
        return render(request, 'registration/register.html', {'form': form})

    def post(self, request):
        form = CustomUserCreationForm(request.POST)

        if form.is_valid():
            user = form.save()

            login(
                request,
                user,
                backend='django.contrib.auth.backends.ModelBackend'
            )

            return redirect('accounts:setup_profile')

        return render(request, 'registration/register.html', {'form': form})

class CustomLoginView(LoginView):
    template_name = 'registration/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse_lazy('accounts:dashboard')

@login_required
def dashboard_view(request):
    # Busca os projetos onde o usuário é dono ou membro
    projects = Project.objects.filter(
        Q(owner=request.user) | Q(members=request.user)
    ).distinct().order_by('-created_at')

    tasks = Task.objects.filter(
        Q(project__owner=request.user) | Q(project__members=request.user)
    ).distinct().order_by('-created_at')

    today = timezone.localdate()
    yesterday = today - timezone.timedelta(days=1)

    statuses = [
        {'key': 'pending', 'label': 'Pendente', 'tasks': tasks.filter(status='pending').select_related('project', 'task_responsible').order_by('-created_at')},
        {'key': 'in_progress', 'label': 'Em andamento', 'tasks': tasks.filter(status='in_progress').select_related('project', 'task_responsible').order_by('-created_at')},
        {'key': 'completed', 'label': 'Concluída', 'tasks': tasks.filter(status='completed').select_related('project', 'task_responsible').order_by('-created_at')},
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

# --- FLUXO DE RECUPERAÇÃO DE SENHA ---

def solicitar_codigo_view(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        # rate limit
        rate_key = f'reset_request_rate_{email}'
        solicitations = cache.get(rate_key, 0)

        if solicitations >= 5:
            messages.error(
                request,
                'Muitas solicitações, tente novamente mais tarde'
            )
            return redirect('accounts:solicitar_codigo')
        cache.set(
            rate_key,
            solicitations + 1,
            timeout=600
        )

        if User.objects.filter(email=email).exists():
            codigo = f"{secrets.randbelow(900000) + 100000}"

            # Salva o código no cache por 10 minutos
            cache.set(f'reset_code_{email}', codigo, timeout=600)

            enviar_email_codigo(email, codigo)

            request.session['email_recuperacao'] = email
            messages.success(request, 'Código enviado para o seu e-mail!')
            return redirect('accounts:verificar_codigo')
        else:
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

            # Limpa código do cache e a sessão
            cache.delete(f'reset_code_{email}')
            del request.session['email_recuperacao']

            messages.success(request, 'Senha alterada com sucesso! Faça login.')
            return redirect('accounts:login')

    return render(request, 'registration/verificar_codigo.html')

@login_required
def delete_account_view(request):
    if request.method == "POST":
        user = request.user

        print("EXCLUINDO:", user.id, user.email)

        logout(request)
        user.delete()

        print("USUÁRIO EXCLUÍDO")

        return redirect('accounts:login')

    return redirect('accounts:dashboard')

@login_required
def delete_account_page(request):
    return render(request, 'delete_account.html')

@login_required
def setup_profile_view(request):
    profile, created = UserProfile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        profile.bio = request.POST.get("bio", "")
        profile.birth_date = request.POST.get("birth_date") or None
        profile.save()

        # Recebe a lista de nomes enviados pelo HTML (ex: ['TypeScript', 'Python'])
        skills_selected = request.POST.getlist("skills")

        # Busca ou cria cada tecnologia pelo nome e associa ao perfil
        skill_objects = []
        for tech_name in skills_selected:
            tech, _ = Technology.objects.get_or_create(name=tech_name)
            skill_objects.append(tech)

        profile.skills.set(skill_objects)

        return redirect('accounts:dashboard') # Altere para sua rota final

    return render(request, 'profile/setup.html', {
        'profile': profile,
    })

@login_required
def search_users(request):
    query = (request.GET.get('q') or '').strip()

    users = User.objects.exclude(pk=request.user.pk)

    if query:
        users = users.filter(
            Q(username__icontains=query) |
            Q(email__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query)
        ).distinct()[:10]
    else:
        users = users[:10]

    results = []
    for user in users:
        profile = getattr(user, 'profile', None)
        skills = list(profile.skills.values_list('name', flat=True)) if profile else []
        results.append({
            'id': user.pk,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'full_name': user.get_full_name() or user.username,
            'skills': skills,
            'location': profile.location if profile else '',
            'bio': profile.bio if profile else '',
        })

    return JsonResponse({'results': results})


@login_required
def view_profile_view(request):
    return render(request, 'profile/view_profile.html')