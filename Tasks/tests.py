from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from Tasks.models import Project, Task


class CreateTaskViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username='testeuser',
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
            reverse('task_update_status', args=[task.pk]),
            {'status': 'in_progress'}
        )

        self.assertEqual(response.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.status, 'in_progress')

    def test_create_project_accepts_selected_members(self):
        User = get_user_model()
        member = User.objects.create_user(
            username='membro1',
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
        self.assertIn(member, project.members.all())

    def test_search_users_by_name_or_email(self):
        User = get_user_model()
        User.objects.create_user(
            username='joao.silva',
            email='joao.silva@empresa.com',
            first_name='João',
            last_name='Silva',
            password='Senha123!'
        )

        response = self.client.get(reverse('accounts:search_users'), {'q': 'joao'})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['results'])
        self.assertEqual(response.json()['results'][0]['email'], 'joao.silva@empresa.com')

    def test_create_project_accepts_selected_members(self):
        User = get_user_model()
        member = User.objects.create_user(
            username='membro1',
            email='membro1@empresa.com',
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
        self.assertIn(member, project.members.all())

    def test_search_users_by_name_or_email(self):
        User = get_user_model()
        User.objects.create_user(
            username='joao.silva',
            email='joao.silva@empresa.com',
            first_name='João',
            last_name='Silva',
            password='Senha123!'
        )

        response = self.client.get(reverse('search_users'), {'q': 'joao'})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['results'])
        self.assertEqual(response.json()['results'][0]['email'], 'joao.silva@empresa.com')
