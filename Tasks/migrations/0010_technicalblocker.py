import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Tasks', '0009_project_github_repo_url'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='TechnicalBlocker',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=140)),
                ('category', models.CharField(choices=[('bug', 'Bug'), ('dependency', 'Dependência'), ('environment', 'Ambiente/infraestrutura'), ('specification', 'Requisito indefinido'), ('review', 'Aguardando revisão'), ('other', 'Outro')], default='other', max_length=20)),
                ('severity', models.CharField(choices=[('critical', 'Crítica'), ('high', 'Alta'), ('medium', 'Média'), ('low', 'Baixa')], default='medium', max_length=10)),
                ('description', models.TextField()),
                ('unblock_action', models.TextField(blank=True)),
                ('status', models.CharField(choices=[('open', 'Aberto'), ('in_progress', 'Em andamento'), ('resolved', 'Resolvido')], default='open', max_length=20)),
                ('resolution', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                ('assigned_to', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assigned_technical_blockers', to=settings.AUTH_USER_MODEL)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reported_technical_blockers', to=settings.AUTH_USER_MODEL)),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='technical_blockers', to='Tasks.project')),
                ('task', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='technical_blockers', to='Tasks.task')),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['project', 'status', '-created_at'], name='Tasks_techn_project_45d2b2_idx')],
            },
        ),
    ]
