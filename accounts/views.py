from django.shortcuts import render, redirect
from django.views import View
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.urls import reverse_lazy
from django.core.cache import cache
import secrets

from .forms import CustomUserCreationForm
from .services import enviar_email_codigo

User = get_user_model()


class RegisterView(View):
    def get(self, request):
        form = CustomUserCreationForm()
        return render(request, 'registration/register.html', {'form': form})

    def post(self, request):
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('accounts:login')
        return render(request, 'registration/register.html', {'form': form})


class CustomLoginView(LoginView):
    template_name = 'registration/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse_lazy('accounts:dashboard')



def logout_view(request):
    logout(request)
    return redirect("login")
@login_required
def dashboard_view(request):
    return render(request, 'dashboard.html')


# --- FLUXO DE RECUPERAÇÃO DE SENHA ---

def solicitar_codigo_view(request):
    if request.method == 'POST':
        email = request.POST.get('email')

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