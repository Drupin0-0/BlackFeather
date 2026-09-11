import os
import secrets
from django.core.mail import EmailMultiAlternatives
from django.conf import settings

def gerar_codigo_verificacao():
    return f"{secrets.randbelow(900000) + 100000}"

def enviar_email_codigo(destinatario_email, codigo):
    assunto = 'Seu código de recuperação - BlackFeather'
    corpo_texto = f'Seu código de recuperação é: {codigo}'
    corpo_html = f"""
    <h2>Recuperação de Senha</h2>
    <p>Você solicitou a alteração de senha. Use o código abaixo para continuar:</p>
    <h1 style="color: #4A90E2; letter-spacing: 5px;">{codigo}</h1>
    <p>Este código expira em 10 minutos.</p>
    <p>Se não foi você, ignore este e-mail.</p>
    """

    # Garante que o remetente seja lido das configurações do Django
    remetente = settings.EMAIL_HOST_USER

    try:
        email = EmailMultiAlternatives(
            subject=assunto,
            body=corpo_texto,
            from_email=remetente,  # IMPORTANTE: define explicitamente o remetente
            to=[destinatario_email]
        )
        email.attach_alternative(corpo_html, "text/html")
        email.send()
        print(f'E-mail com o código enviado para {destinatario_email}.')
        return True
    except Exception as e:
        print(f'Erro ao enviar o e-mail: {e}')
        return False