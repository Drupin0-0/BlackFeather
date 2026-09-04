from datetime import datetime, timedelta
import secrets
from django.shortcuts import render, redirect
from django.views import View
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model  # <-- Importação correta
from django.contrib import messages
from django.urls import reverse_lazy
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


@login_required
def dashboard_view(request):
    return render(request, 'dashboard.html')


# --- FLUXO DE RECUPERAÇÃO DE SENHA ---

# Dicionário temporário para guardar os códigos de recuperação
codigos_temporarios = {}

def solicitar_codigo_view(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        
        # Verifica se o usuário existe no banco de dados
        if User.objects.filter(email=email).exists():
            # Gera código aleatório de 6 dígitos
            codigo = f"{secrets.randbelow(900000) + 100000}"
            expiracao = datetime.now() + timedelta(minutes=10)
            
            codigos_temporarios[email] = {
                'codigo': codigo,
                'expiracao': expiracao
            }
            
            # Dispara o e-mail usando o services.py
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
        
        dados = codigos_temporarios.get(email)
        
        # Valida o código e o tempo de expiração
        if dados and dados['codigo'] == codigo_digitado and datetime.now() <= dados['expiracao']:
            user = User.objects.get(email=email)
            user.set_password(nova_senha)
            user.save()
            
            # Limpa os dados temporários e a sessão
            del codigos_temporarios[email]
            del request.session['email_recuperacao']
            
            messages.success(request, 'Senha alterada com sucesso! Faça login.')
            return redirect('accounts:login')
        else:
            messages.error(request, 'Código inválido ou expirado.')

    return render(request, 'registration/verificar_codigo.html')