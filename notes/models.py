from django.conf import settings
from django.db import models

from Tasks.models import Project


class Section(models.Model):
    VISIBILITY_CHOICES = [
        ('shared', 'Compartilhada'),
        ('private', 'Privada'),
    ]

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='note_sections',
    )
    title = models.CharField(max_length=100)
    order = models.PositiveIntegerField(default=0)
    visibility = models.CharField(
        max_length=15,
        choices=VISIBILITY_CHOICES,
        default='shared',
    )
    allowed_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='allowed_note_sections',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_note_sections',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'id']
        indexes = [models.Index(fields=['project', 'order'])]

    def __str__(self):
        return self.title


class Subsection(models.Model):
    section = models.ForeignKey(
        Section,
        on_delete=models.CASCADE,
        related_name='subsections',
    )
    title = models.CharField(max_length=100)
    order = models.PositiveIntegerField(default=0)
    theme = models.CharField(max_length=20, default='dark')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'id']
        indexes = [models.Index(fields=['section', 'order'])]

    def __str__(self):
        return self.title


class Page(models.Model):
    subsection = models.ForeignKey(
        Subsection,
        on_delete=models.CASCADE,
        related_name='pages',
    )
    title = models.CharField(max_length=100)
    order = models.PositiveIntegerField(default=0)
    content = models.JSONField(default=dict, blank=True)
    version = models.PositiveIntegerField(default=1)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='updated_note_pages',
    )
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'id']
        indexes = [models.Index(fields=['subsection', 'order'])]

    def __str__(self):
        return self.title
