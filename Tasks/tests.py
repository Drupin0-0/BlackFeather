from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from Tasks.models import Project, Task


class CreateTaskViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            email='teste@example.com',
            password='Senha123!'
        )
        self.client.force_login(self.user)

        self.project = Project.objects.create(
            title='Projeto de Teste',
            description='Projeto para validar tarefa',
            owner=self.user,
        )
        self.project.members.add(self.user)

    def test_create_task_view_creates_task(self):
        response = self.client.post(reverse('task_create'), {
            'project': self.project.pk,
            'title': 'Tarefa de teste',
            'description': 'Descrição da tarefa',
            'status': 'pending',
            'priority': 'high',
            'deadline': '2035-12-31',
            'task_responsible': self.user.pk,
        })

        self.assertEqual(response.status_code, 302)
        task = Task.objects.get(title='Tarefa de teste', project=self.project)
        self.assertEqual(task.task_responsible, self.user)

    def test_update_task_status_moves_task_between_columns(self):
        task = Task.objects.create(
            project=self.project,
            title='Tarefa para mover',
            description='Descrição',
            status='pending',
            priority='medium',
            task_responsible=self.user,
        )

        response = self.client.post(
            reverse('update_task_status', args=[task.pk]),
            {'status': 'in_progress'}
        )

        self.assertEqual(response.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.status, 'in_progress')

    def test_create_project_sends_invite_and_waits_for_acceptance(self):
        User = get_user_model()
        member = User.objects.create_user(
            email='membro1@empresa.com',
            first_name='Maria',
            last_name='Silva',
            password='Senha123!'
        )

        response = self.client.post(reverse('project_create'), {
            'title': 'Projeto com membros',
            'description': 'Projeto para validar adição de membros',
            'members': [str(member.pk)],
        })

        self.assertEqual(response.status_code, 302)
        project = Project.objects.get(title='Projeto com membros')
        self.assertIn(self.user, project.members.all())
        self.assertNotIn(member, project.members.all())
        from chat.models import JoinRequest, Notification
        invitation = JoinRequest.objects.get(
            sender=self.user,
            recipient=member,
            project=project,
            status='pending',
        )
        notification = Notification.objects.get(user=member, join_request=invitation)
        self.assertEqual(notification.title, 'Convite para projeto')

    def test_create_project_saves_category_and_custom_accent_color(self):
        response = self.client.post(reverse('project_create'), {
            'title': 'App de vendas',
            'category': 'mobile',
            'accent_color': '#22aa77',
        })

        self.assertEqual(response.status_code, 302)
        project = Project.objects.get(title='App de vendas')
        self.assertEqual(project.category, 'mobile')
        self.assertEqual(project.accent_color, '#22aa77')

    def test_create_project_can_keep_default_accent_color(self):
        self.client.post(reverse('project_create'), {
            'title': 'Projeto padrão',
            'category': 'personal',
            'accent_color': '#ff0000',
            'use_default_color': 'on',
        })

        project = Project.objects.get(title='Projeto padrão')
        self.assertEqual(project.category, 'personal')
        self.assertEqual(project.accent_color, '#a3c7ff')

    def test_project_form_uses_email_invite_without_autocomplete_list(self):
        response = self.client.get(reverse('project_create'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Convidar por e-mail')
        self.assertContains(response, 'Digite o e-mail completo')
        self.assertNotContains(response, 'Buscar por nome ou e-mail')
        self.assertContains(response, 'name="category"')
        self.assertContains(response, 'value="sales"')
        self.assertContains(response, 'name="accent_color"')
        self.assertContains(response, 'Usar cor padrão')
        self.assertContains(response, 'name="generate_tasks_ai"')
        self.assertNotContains(response, 'Sugerir membros com IA')

    def test_project_list_displays_join_by_code_form(self):
        response = self.client.get(reverse('project_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Entrar em um projeto')
        self.assertContains(response, 'name="project_code"')

    def test_search_users_by_name_or_email(self):
        User = get_user_model()
        User.objects.create_user(
            email='joao.silva@empresa.com',
            first_name='João',
            last_name='Silva',
            password='Senha123!'
        )
        response = self.client.get(
            reverse('accounts:search_users'),
            {'q': 'joao.silva@empresa.com'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['results'])
        self.assertEqual(response.json()['results'][0]['email'], 'joao.silva@empresa.com')

    def test_search_users_does_not_return_partial_suggestions(self):
        User = get_user_model()
        User.objects.create_user(
            email='joao.silva@empresa.com',
            password='Senha123!'
        )

        response = self.client.get(reverse('accounts:search_users'), {'q': 'joao'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['results'], [])

    def test_suggest_distribution_denies_non_member(self):
        outro_usuario = get_user_model().objects.create_user(
            email='fora@teste.com',
            password='Senha123!'
        )
        self.client.force_login(outro_usuario)

        response = self.client.post(
            reverse('task_suggest_distribution', args=[self.project.pk]),
            {'task_description': ['Tarefa teste']}
        )

        self.assertEqual(response.status_code, 403)