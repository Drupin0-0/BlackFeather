from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from accounts.models import User
import secrets
import string


def validate_future_date(value):
    """Garante que a data informada não seja anterior ao dia atual."""
    if value and value < timezone.localdate():
        raise ValidationError("A data limite não pode ser anterior à data atual.")


def code_generator():
    """Gera um código único de 6 caracteres alfanuméricos."""
    characters = string.ascii_uppercase + string.digits
    while True:
        code = ''.join(secrets.choice(characters) for _ in range(6))
        # Verifica se o código já existe no banco antes de retornar
        if not Project.objects.filter(code=code).exists():
            return code


class Project(models.Model):
    title = models.CharField(max_length=100)

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )

    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='projects'
    )

    description = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    code = models.CharField(
        max_length=6,
        unique=True,
        default=code_generator  # 
    )

    def __str__(self):
        return self.title

#a
class Task(models.Model):
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='tasks'
    )

    title = models.CharField(max_length=100)
    description = models.TextField(null=True, blank=True)

    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pendente'),
            ('in_progress', 'Em andamento'),
            ('completed', 'Concluída'),
        ],
        default='pending'
    )

    priority = models.CharField(
        max_length=10,
        choices=[
            ('low', 'Baixa'),
            ('medium', 'Média'),
            ('high', 'Alta'),
        ],
        default='medium'
    )

    deadline = models.DateField(
        null=True,
        blank=True,
        validators=[validate_future_date]
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    task_responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='responsible_tasks'
    )

    def __str__(self):
        return self.title
    
# Invite users to a project class
class ProjectInvitation(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    invited_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='project_invitations'
    )
    invited_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='project_invitations'
        )

    created_at =  models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pendente')
            ('accepted', 'Aceito')
            ('rejected', 'Recusado')
            ('expired', 'Expirado')
        ],
        default='pending',
    )