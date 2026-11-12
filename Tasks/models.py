from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
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
    CATEGORY_CHOICES = [
        ("general", "Geral"),
        ("sales", "Vendas"),
        ("personal", "Projeto pessoal"),
        ("mobile", "Mobile"),
        ("marketing", "Marketing"),
    ]

    title = models.CharField(max_length=100)

    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default="general",
    )

    accent_color = models.CharField(
        max_length=7,
        default="#a3c7ff",
    )

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )

    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='projects'
    )

    default_can_create_tasks = models.BooleanField(default=True)
    default_can_delete_tasks = models.BooleanField(default=False)
    default_can_edit_tasks = models.BooleanField(default=True)
    default_can_create_boards = models.BooleanField(default=False)
    default_can_invite_members = models.BooleanField(default=True)

    description = models.TextField(null=True, blank=True)

    github_repo_url = models.URLField(
        max_length=255,
        blank=True,
        help_text='URL de um repositório público do GitHub.',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    code = models.CharField(
        max_length=6,
        unique=True,
        default=code_generator  # 
    )

    def is_boss(self, user):
        return getattr(user, 'pk', None) == self.owner_id

    def is_leader(self, user):
        return self.memberships.filter(
            user_id=getattr(user, 'pk', None),
            role=ProjectMember.Role.LEADER,
        ).exists()

    def can_manage_settings(self, user):
        return self.is_boss(user) or self.is_leader(user)

    def get_role(self, user):
        if self.is_boss(user):
            return 'boss'

        membership = self.memberships.filter(
            user_id=getattr(user, 'pk', None),
        ).first()
        if membership:
            return membership.role
        if self.members.filter(pk=getattr(user, 'pk', None)).exists():
            return 'member'
        return None

    def user_can(self, user, permission):
        if self.is_boss(user):
            return True

        membership = self.memberships.filter(
            user_id=getattr(user, 'pk', None),
        ).first()
        if membership is None or permission not in ProjectMember.PERMISSION_FIELDS:
            return False

        if (
            membership.role == ProjectMember.Role.LEADER
            and permission in ProjectMember.TASK_PERMISSION_FIELDS
        ):
            return True

        return getattr(membership, permission)

    def __str__(self):
        return self.title


class ProjectMember(models.Model):
    class Role(models.TextChoices):
        LEADER = 'leader', 'Líder'
        MEMBER = 'member', 'Integrante'

    PERMISSION_FIELDS = {
        'can_create_tasks',
        'can_delete_tasks',
        'can_edit_tasks',
        'can_create_boards',
        'can_invite_members',
    }
    TASK_PERMISSION_FIELDS = {
        'can_create_tasks',
        'can_delete_tasks',
        'can_edit_tasks',
    }

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='memberships',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='project_memberships',
    )
    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.MEMBER,
    )
    can_create_tasks = models.BooleanField(default=True)
    can_delete_tasks = models.BooleanField(default=False)
    can_edit_tasks = models.BooleanField(default=True)
    can_create_boards = models.BooleanField(default=False)
    can_invite_members = models.BooleanField(default=True)

    class Meta:
        unique_together = ('project', 'user')


class ProjectColumn(models.Model):
    DEFAULT_STATUS_CHOICES = [
        ('pending', 'Pendente'),
        ('in_progress', 'Em andamento'),
        ('completed', 'Concluída'),
    ]

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='columns',
    )
    name = models.CharField(max_length=100)
    position = models.PositiveIntegerField(default=0)
    default_status = models.CharField(
        max_length=20,
        choices=DEFAULT_STATUS_CHOICES,
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ['position', 'pk']
        constraints = [
            models.UniqueConstraint(
                fields=['project', 'default_status'],
                condition=models.Q(default_status__isnull=False),
                name='unique_project_default_column_status',
            ),
        ]

    def __str__(self):
        return f'{self.project.title} - {self.name}'


class Task(models.Model):
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='tasks'
    )
    project_column = models.ForeignKey(
        ProjectColumn,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tasks',
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


class TaskHistory(models.Model):
    class Action(models.TextChoices):
        CREATED = 'created', 'Criada'
        UPDATED = 'updated', 'Atualizada'
        DELETED = 'deleted', 'Excluída'

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='history',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='task_history',
    )
    action = models.CharField(
        max_length=20,
        choices=Action.choices,
        default=Action.UPDATED,
    )
    task_title = models.CharField(max_length=100)
    task_id = models.IntegerField(null=True, blank=True)
    changes = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['project', '-created_at'])]
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.project.title} - {self.action}'


class TechnicalBlocker(models.Model):
    class Category(models.TextChoices):
        BUG = 'bug', 'Bug'
        DEPENDENCY = 'dependency', 'Dependência'
        ENVIRONMENT = 'environment', 'Ambiente/infraestrutura'
        SPECIFICATION = 'specification', 'Requisito indefinido'
        REVIEW = 'review', 'Aguardando revisão'
        OTHER = 'other', 'Outro'

    class Severity(models.TextChoices):
        CRITICAL = 'critical', 'Crítica'
        HIGH = 'high', 'Alta'
        MEDIUM = 'medium', 'Média'
        LOW = 'low', 'Baixa'

    class Status(models.TextChoices):
        OPEN = 'open', 'Aberto'
        IN_PROGRESS = 'in_progress', 'Em andamento'
        RESOLVED = 'resolved', 'Resolvido'

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='technical_blockers',
    )
    task = models.ForeignKey(
        Task,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='technical_blockers',
    )
    title = models.CharField(max_length=140)
    category = models.CharField(
        max_length=20,
        choices=Category.choices,
        default=Category.OTHER,
    )
    severity = models.CharField(
        max_length=10,
        choices=Severity.choices,
        default=Severity.MEDIUM,
    )
    description = models.TextField()
    unblock_action = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='reported_technical_blockers',
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_technical_blockers',
    )
    resolution = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['project', 'status', '-created_at'])]

    def __str__(self):
        return f'{self.project.title} - {self.title}'


def record_task_history(project, user=None, action='updated', task=None, task_title=None, changes=None, task_id=None):
    if not project:
        return None

    if task is not None:
        project = task.project
        task_id = task.pk if task_id is None else task_id
        task_title = task.title if task_title is None else task_title

    if not task_title:
        task_title = (task.title if task else '')[:100]

    if changes is None:
        changes = []
    if not isinstance(changes, list):
        changes = []
    if not changes:
        return None

    normalized = []
    for change in changes:
        if not isinstance(change, dict):
            continue
        normalized.append({
            'field': change.get('field') or 'field',
            'label': change.get('label') or change.get('field') or 'campo',
            'from': change.get('from'),
            'to': change.get('to'),
        })

    if not normalized:
        return None

    return TaskHistory.objects.create(
        project=project,
        user=user,
        action=action,
        task_title=task_title[:100],
        task_id=task_id,
        changes=normalized,
    )
