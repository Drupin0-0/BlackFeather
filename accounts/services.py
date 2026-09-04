import os
import smtplib
import secrets
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()

def gerar_codigo_verificacao():
    # Gera um número aleatório de 6 dígitos (ex: 483921)
    return f"{secrets.randbelow(900000) + 100000}"

def enviar_email_codigo(destinatario_email, codigo):
    remetente = 'blackfeatherldta@gmail.com'
    senha = 'aksz voke ipny zclo'

    msg = EmailMessage()
    msg['Subject'] = 'Seu código de recuperação - BlackFeather'
    msg['From'] = remetente
    msg['To'] = destinatario_email
    
    # Corpo do e-mail destacando o código
    corpo_html = f"""
    <h2>Recuperação de Senha</h2>
    <p>Você solicitou a alteração de senha. Use o código abaixo para continuar:</p>
    <h1 style="color: #4A90E2; letter-spacing: 5px;">{codigo}</h1>
    <p>Este código expira em 10 minutos.</p>
    <p>Se não foi você, ignore este e-mail.</p>
    """
    
    msg.set_content(f'Seu código de recuperação é: {codigo}')
    msg.add_alternative(corpo_html, subtype='html')

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(remetente, senha)
            smtp.send_message(msg)
        print(f'E-mail com o código enviado para {destinatario_email}.')
        return True
    except Exception as e:
        print(f'Erro ao enviar o e-mail: {e}')
        return False
