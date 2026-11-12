from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from unittest.mock import patch

from Tasks.models import Project, ProjectColumn, ProjectMember, Task, TaskHistory, TechnicalBlocker
from Tasks.github_service import parse_github_repository_url
from accounts.models import UserProfile


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

    def test_github_repository_url_parser_accepts_only_repository_urls(self):
        self.assertEqual(
            parse_github_repository_url('https://github.com/acme/demo.git'),
            ('acme', 'demo'),
        )
        for invalid_url in (
            'http://github.com/acme/demo',
            'https://github.com.evil.example/acme/demo',
            'https://github.com/acme/demo/issues',
        ):
            with self.subTest(url=invalid_url):
                with self.assertRaises(ValueError):
                    parse_github_repository_url(invalid_url)

    @patch('Tasks.views.get_repository_activity')
    def test_boss_can_link_public_github_repository(self, get_activity):
        response = self.client.post(
            reverse('project_github_repository_update', args=[self.project.pk]),
            {'github_repo_url': 'https://github.com/acme/demo.git'},
        )

        self.assertRedirects(
            response,
            reverse('project_settings', args=[self.project.pk]),
        )
        self.project.refresh_from_db()
        self.assertEqual(self.project.github_repo_url, 'https://github.com/acme/demo')
        get_activity.assert_called_once_with('https://github.com/acme/demo')

    def test_project_member_cannot_change_github_repository(self):
        member = get_user_model().objects.create_user(
            email='integrante@example.com',
            password='Senha123!',
        )
        self.project.members.add(member)
        self.client.force_login(member)

        response = self.client.post(
            reverse('project_github_repository_update', args=[self.project.pk]),
            {'github_repo_url': 'https://github.com/acme/demo'},
        )

        self.assertEqual(response.status_code, 403)
        self.project.refresh_from_db()
        self.assertEqual(self.project.github_repo_url, '')

    @patch('Tasks.views.get_repository_activity')
    @patch('Tasks.views.get_open_pull_request_activity')
    def test_project_summary_returns_github_activity(self, get_pull_requests, get_activity):
        self.project.github_repo_url = 'https://github.com/acme/demo'
        self.project.save(update_fields=['github_repo_url'])
        get_activity.return_value = {
            'success': True,
            'repository': 'acme/demo',
            'commits': [],
            'contributors': [],
            'total_commits': 0,
            'contributors_count': 0,
            'sample_limit': 100,
        }
        get_pull_requests.return_value = {
            'pull_requests': [{
                'number': 42,
                'title': 'Corrigir falha no deploy',
                'requested_reviewers': ['dev-reviewer'],
                'stale': True,
            }],
            'open_count': 1,
            'review_requested_count': 1,
            'stale_count': 1,
            'sample_limit': 30,
        }

        response = self.client.get(
            reverse('project_summary_github', args=[self.project.pk]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['configured'])
        self.assertEqual(response.json()['repository'], 'acme/demo')
        self.assertEqual(response.json()['review_requested_count'], 1)
        self.assertTrue(response.json()['pull_requests'][0]['stale'])
        get_activity.assert_called_once_with(self.project.github_repo_url)
        get_pull_requests.assert_called_once_with(self.project.github_repo_url)

    def test_project_member_can_report_technical_blocker_with_task(self):
        task = Task.objects.create(project=self.project, title='Corrigir autenticação')

        response = self.client.post(
            reverse('project_blockers', args=[self.project.pk]),
            {
                'title': 'Token expira antes de concluir o fluxo',
                'category': TechnicalBlocker.Category.BUG,
                'severity': TechnicalBlocker.Severity.HIGH,
                'description': 'O token perde a validade no meio do teste de integração.',
                'unblock_action': 'Precisamos revisar a duração configurada.',
                'task_id': task.pk,
                'assigned_to': self.user.pk,
            },
        )

        self.assertRedirects(response, reverse('project_blockers', args=[self.project.pk]))
        blocker = TechnicalBlocker.objects.get(project=self.project)
        self.assertEqual(blocker.created_by, self.user)
        self.assertEqual(blocker.task, task)
        self.assertEqual(blocker.assigned_to, self.user)
        self.assertEqual(blocker.status, TechnicalBlocker.Status.OPEN)

    def test_blocker_cannot_be_linked_to_task_from_another_project(self):
        other_project = Project.objects.create(title='Outro projeto', owner=self.user)
        foreign_task = Task.objects.create(project=other_project, title='Tarefa privada')

        response = self.client.post(
            reverse('project_blockers', args=[self.project.pk]),
            {
                'title': 'Bloqueio inválido',
                'description': 'Tentativa de vincular uma tarefa externa.',
                'task_id': foreign_task.pk,
            },
        )

        self.assertRedirects(response, reverse('project_blockers', args=[self.project.pk]))
        self.assertFalse(TechnicalBlocker.objects.filter(project=self.project).exists())

    def test_blocker_must_have_resolution_before_being_resolved(self):
        blocker = TechnicalBlocker.objects.create(
            project=self.project,
            created_by=self.user,
            title='Problema de build',
            description='O build falha no pipeline.',
        )

        response = self.client.post(
            reverse('project_blocker_update', args=[self.project.pk, blocker.pk]),
            {'status': TechnicalBlocker.Status.RESOLVED, 'resolution': ''},
        )

        self.assertRedirects(response, reverse('project_blockers', args=[self.project.pk]))
        blocker.refresh_from_db()
        self.assertEqual(blocker.status, TechnicalBlocker.Status.OPEN)
        self.assertIsNone(blocker.resolved_at)

    def test_non_author_without_edit_permission_cannot_update_blocker(self):
        member = get_user_model().objects.create_user(
            email='integrante@example.com',
            password='Senha123!',
        )
        self.project.members.add(member)
        ProjectMember.objects.create(
            project=self.project,
            user=member,
            can_edit_tasks=False,
        )
        blocker = TechnicalBlocker.objects.create(
            project=self.project,
            created_by=self.user,
            title='Impedimento da equipe',
            description='Aguardando uma decisão técnica.',
        )
        self.client.force_login(member)

        response = self.client.post(
            reverse('project_blocker_update', args=[self.project.pk, blocker.pk]),
            {'status': TechnicalBlocker.Status.IN_PROGRESS, 'resolution': ''},
        )

        self.assertEqual(response.status_code, 403)
        blocker.refresh_from_db()
        self.assertEqual(blocker.status, TechnicalBlocker.Status.OPEN)

    def test_project_summary_payloads_include_the_selected_bird(self):
        UserProfile.objects.create(
            user=self.user,
            name='Teste',
            avatar_bird='coruja',
        )
        TaskHistory.objects.create(
            project=self.project,
            user=self.user,
            action='created',
            task_title='Tarefa de teste',
        )

        history = self.client.get(reverse('project_summary_history', args=[self.project.pk]))
        assignments = self.client.get(reverse('project_summary_assignment', args=[self.project.pk]))

        self.assertEqual(history.json()['items'][0]['user_avatar_bird'], 'coruja')
        owner_row = next(row for row in assignments.json()['rows'] if row['user_id'] == self.user.pk)
        self.assertEqual(owner_row['avatar_bird'], 'coruja')

    def test_project_role_and_permissions_helpers(self):
        member = get_user_model().objects.create_user(
            email='integrante@example.com',
            password='Senha123!'
        )
        self.project.members.add(member)
        membership = ProjectMember.objects.create(
            project=self.project,
            user=member,
        )

        self.assertTrue(self.project.is_boss(self.user))
        self.assertEqual(self.project.get_role(self.user), 'boss')
        self.assertTrue(self.project.user_can(self.user, 'can_delete_tasks'))
        self.assertFalse(self.project.can_manage_settings(member))
        self.assertEqual(self.project.get_role(member), 'member')
        self.assertTrue(self.project.user_can(member, 'can_create_tasks'))
        self.assertFalse(self.project.user_can(member, 'can_delete_tasks'))

        membership.role = ProjectMember.Role.LEADER
        membership.can_create_tasks = False
        membership.save()

        self.assertTrue(self.project.is_leader(member))
        self.assertTrue(self.project.can_manage_settings(member))
        self.assertEqual(self.project.get_role(member), 'leader')
        self.assertTrue(self.project.user_can(member, 'can_create_tasks'))

    def test_member_cannot_manage_project_settings(self):
        member = get_user_model().objects.create_user(
            email='integrante@example.com',
            password='Senha123!'
        )
        self.project.members.add(member)
        self.client.force_login(member)

        response = self.client.post(
            reverse('project_member_promote', args=[self.project.pk, member.pk])
        )

        self.assertEqual(response.status_code, 403)

    def test_boss_can_promote_and_demote_a_member(self):
        member = get_user_model().objects.create_user(
            email='integrante@example.com',
            password='Senha123!'
        )
        self.project.members.add(member)
        self.client.force_login(self.user)

        promote_response = self.client.post(
            reverse('project_member_promote', args=[self.project.pk, member.pk])
        )
        self.assertEqual(promote_response.status_code, 200)
        membership = ProjectMember.objects.get(project=self.project, user=member)
        self.assertEqual(membership.role, ProjectMember.Role.LEADER)

        demote_response = self.client.post(
            reverse('project_member_demote', args=[self.project.pk, member.pk])
        )
        self.assertEqual(demote_response.status_code, 200)
        membership.refresh_from_db()
        self.assertEqual(membership.role, ProjectMember.Role.MEMBER)

    def test_leader_can_edit_member_permissions_but_not_another_leader(self):
        leader = get_user_model().objects.create_user(
            email='lider@example.com',
            password='Senha123!'
        )
        member = get_user_model().objects.create_user(
            email='integrante@example.com',
            password='Senha123!'
        )
        other_leader = get_user_model().objects.create_user(
            email='outro-lider@example.com',
            password='Senha123!'
        )
        self.project.members.add(leader, member, other_leader)
        ProjectMember.objects.create(
            project=self.project,
            user=leader,
            role=ProjectMember.Role.LEADER,
        )
        ProjectMember.objects.create(
            project=self.project,
            user=other_leader,
            role=ProjectMember.Role.LEADER,
        )
        self.client.force_login(leader)
        permission_values = {
            'can_create_tasks': 'false',
            'can_delete_tasks': 'true',
            'can_edit_tasks': 'false',
            'can_create_boards': 'true',
            'can_invite_members': 'false',
        }

        allowed_response = self.client.post(
            reverse('project_member_permissions', args=[self.project.pk, member.pk]),
            permission_values,
        )
        denied_response = self.client.post(
            reverse('project_member_permissions', args=[self.project.pk, other_leader.pk]),
            permission_values,
        )

        self.assertEqual(allowed_response.status_code, 200)
        self.assertEqual(denied_response.status_code, 403)
        membership = ProjectMember.objects.get(project=self.project, user=member)
        self.assertFalse(membership.can_create_tasks)
        self.assertTrue(membership.can_delete_tasks)
        self.assertFalse(membership.can_edit_tasks)
        self.assertTrue(membership.can_create_boards)
        self.assertFalse(membership.can_invite_members)

    def test_boss_can_remove_member_and_unassign_their_tasks(self):
        member = get_user_model().objects.create_user(
            email='integrante@example.com',
            password='Senha123!'
        )
        self.project.members.add(member)
        ProjectMember.objects.create(project=self.project, user=member)
        task = Task.objects.create(
            project=self.project,
            title='Tarefa atribuída',
            task_responsible=member,
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('project_member_remove', args=[self.project.pk, member.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.project.members.filter(pk=member.pk).exists())
        self.assertFalse(
            ProjectMember.objects.filter(project=self.project, user=member).exists()
        )
        task.refresh_from_db()
        self.assertIsNone(task.task_responsible)

    def test_ownership_transfer_requires_confirmation(self):
        member = get_user_model().objects.create_user(
            email='integrante@example.com',
            password='Senha123!'
        )
        self.project.members.add(member)
        ProjectMember.objects.create(project=self.project, user=member)
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('project_transfer_ownership', args=[self.project.pk]),
            {'new_owner_id': member.pk},
        )

        self.assertEqual(response.status_code, 400)
        self.project.refresh_from_db()
        self.assertEqual(self.project.owner, self.user)

    def test_ownership_transfer_makes_previous_owner_a_member(self):
        member = get_user_model().objects.create_user(
            email='integrante@example.com',
            password='Senha123!'
        )
        self.project.members.add(member)
        ProjectMember.objects.create(project=self.project, user=member)
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('project_transfer_ownership', args=[self.project.pk]),
            {'new_owner_id': member.pk, 'confirmation': 'on'},
        )

        self.assertEqual(response.status_code, 200)
        self.project.refresh_from_db()
        self.assertEqual(self.project.owner, member)
        self.assertFalse(
            ProjectMember.objects.filter(project=self.project, user=member).exists()
        )
        previous_membership = ProjectMember.objects.get(
            project=self.project,
            user=self.user,
        )
        self.assertEqual(previous_membership.role, ProjectMember.Role.MEMBER)

    def test_project_deletion_requires_confirmation_without_title(self):
        self.client.force_login(self.user)

        invalid_response = self.client.post(
            reverse('project_delete', args=[self.project.pk]),
            {},
        )
        valid_response = self.client.post(
            reverse('project_delete', args=[self.project.pk]),
            {'confirmation': 'on'},
        )

        self.assertEqual(invalid_response.status_code, 400)
        self.assertRedirects(valid_response, reverse('project_list'))
        self.assertFalse(Project.objects.filter(pk=self.project.pk).exists())

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

    def test_project_can_add_custom_phase_and_move_task_into_it(self):
        self.client.get(reverse('project_detail', args=[self.project.pk]))
        response = self.client.post(
            reverse('project_column_create', args=[self.project.pk]),
            {'name': 'Em revisão'},
        )
        self.assertRedirects(response, reverse('project_detail', args=[self.project.pk]))

        custom_column = ProjectColumn.objects.get(project=self.project, name='Em revisão')
        task = Task.objects.create(project=self.project, title='Tarefa customizada')
        move_response = self.client.post(
            reverse('update_task_project_column', args=[task.pk]),
            {'project_column_id': custom_column.pk},
        )

        self.assertEqual(move_response.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.project_column, custom_column)

        board_response = self.client.get(reverse('project_detail', args=[self.project.pk]))
        self.assertEqual(len(board_response.context['kanban_columns']), 4)
        self.assertContains(board_response, 'Em revisão')

    def test_project_phase_cannot_receive_task_from_another_project(self):
        self.client.get(reverse('project_detail', args=[self.project.pk]))
        other_project = Project.objects.create(title='Outro projeto', owner=self.user)
        self.client.get(reverse('project_detail', args=[other_project.pk]))
        other_column = other_project.columns.get(default_status='pending')
        task = Task.objects.create(project=self.project, title='Tarefa protegida')

        response = self.client.post(
            reverse('update_task_project_column', args=[task.pk]),
            {'project_column_id': other_column.pk},
        )

        self.assertEqual(response.status_code, 404)
        task.refresh_from_db()
        self.assertIsNone(task.project_column_id)

    def test_dashboard_keeps_the_three_general_status_columns(self):
        ProjectColumn.objects.create(project=self.project, name='Fase extra')

        response = self.client.get(reverse('accounts:dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [column['key'] for column in response.context['kanban_columns']],
            ['pending', 'in_progress', 'completed'],
        )

    def test_member_without_task_permissions_is_denied_by_task_endpoints(self):
        member = get_user_model().objects.create_user(
            email='sem-permissao@example.com',
            password='Senha123!'
        )
        self.project.members.add(member)
        ProjectMember.objects.create(
            project=self.project,
            user=member,
            can_create_tasks=False,
            can_edit_tasks=False,
            can_delete_tasks=False,
        )
        task = Task.objects.create(
            project=self.project,
            title='Tarefa protegida',
        )
        self.client.force_login(member)

        create_response = self.client.post(
            reverse('task_create'),
            {'project': self.project.pk, 'title': 'Não deve ser criada'},
        )
        edit_response = self.client.post(
            reverse('task_update', args=[task.pk]),
            {'title': 'Edição não autorizada'},
        )
        status_response = self.client.post(
            reverse('update_task_status', args=[task.pk]),
            {'status': 'completed'},
        )
        delete_response = self.client.post(
            reverse('task_delete', args=[task.pk]),
        )

        self.assertEqual(create_response.status_code, 403)
        self.assertEqual(edit_response.status_code, 403)
        self.assertEqual(status_response.status_code, 403)
        self.assertEqual(delete_response.status_code, 403)
        self.assertTrue(Task.objects.filter(pk=task.pk).exists())

    def test_project_detail_context_reflects_member_task_permissions(self):
        member = get_user_model().objects.create_user(
            email='integrante@example.com',
            password='Senha123!'
        )
        self.project.members.add(member)
        ProjectMember.objects.create(
            project=self.project,
            user=member,
            can_create_tasks=False,
            can_edit_tasks=False,
            can_delete_tasks=False,
        )
        self.client.force_login(member)

        response = self.client.get(
            reverse('project_detail', args=[self.project.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['can_create'])
        self.assertFalse(response.context['can_edit'])
        self.assertFalse(response.context['can_delete'])
        self.assertFalse(response.context['can_manage_settings'])
        self.assertNotContains(response, 'id="projectAddTaskButton"')

    def test_project_settings_button_is_visible_only_to_boss_and_leaders(self):
        leader = get_user_model().objects.create_user(
            email='lider@example.com',
            password='Senha123!'
        )
        member = get_user_model().objects.create_user(
            email='integrante@example.com',
            password='Senha123!'
        )
        self.project.members.add(leader, member)
        ProjectMember.objects.create(
            project=self.project,
            user=leader,
            role=ProjectMember.Role.LEADER,
        )
        ProjectMember.objects.create(project=self.project, user=member)

        self.client.force_login(self.user)
        boss_response = self.client.get(
            reverse('project_detail', args=[self.project.pk])
        )
        self.assertContains(
            boss_response,
            reverse('project_settings', args=[self.project.pk]),
        )

        self.client.force_login(leader)
        leader_response = self.client.get(
            reverse('project_detail', args=[self.project.pk])
        )
        self.assertContains(
            leader_response,
            reverse('project_settings', args=[self.project.pk]),
        )

        self.client.force_login(member)
        member_response = self.client.get(
            reverse('project_detail', args=[self.project.pk])
        )
        self.assertNotContains(
            member_response,
            reverse('project_settings', args=[self.project.pk]),
        )

    def test_project_settings_page_renders_member_and_danger_sections_for_boss(self):
        member = get_user_model().objects.create_user(
            email='integrante@example.com',
            password='Senha123!'
        )
        self.project.members.add(member)
        ProjectMember.objects.create(project=self.project, user=member)
        self.client.force_login(self.user)

        response = self.client.get(
            reverse('project_settings', args=[self.project.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Integrantes')
        self.assertContains(response, 'Permissões dos integrantes')
        self.assertContains(response, 'ZONA DE PERIGO')
        self.assertContains(response, 'Promover a Líder')
        self.assertContains(response, 'name="new_owner_id"')
        self.assertContains(response, 'data-permission="can_create_tasks"')
        self.assertNotContains(response, 'ownerPassword')
        self.assertNotContains(response, 'deleteConfirmation')

    def test_project_settings_shows_default_permissions_without_other_members(self):
        response = self.client.get(
            reverse('project_settings', args=[self.project.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Nenhum outro integrante')
        self.assertContains(response, 'data-empty-permissions')
        self.assertContains(response, 'Permitir criação de tarefas')
        self.assertContains(response, 'Permitir exclusão de tarefas')
        self.assertContains(response, 'Permitir edição de tarefas')
        self.assertContains(response, 'Criação de novos quadros')
        self.assertContains(response, 'Convidar novos integrantes')
        self.assertContains(response, 'class="permission-toggle is-active"')
        self.assertContains(response, 'class="permission-toggle"')
        self.assertNotContains(response, 'permission-toggle" aria-label="Permitir exclusão de tarefas" aria-pressed="false" disabled')
        self.assertNotContains(response, 'dashboard-sidebar')
        self.assertContains(response, 'id="deleteProjectDialog"')

    def test_boss_can_update_default_permissions_for_future_members(self):
        payload = {
            'can_create_tasks': 'false',
            'can_delete_tasks': 'true',
            'can_edit_tasks': 'false',
            'can_create_boards': 'true',
            'can_invite_members': 'false',
        }

        response = self.client.post(
            reverse('project_default_member_permissions', args=[self.project.pk]),
            payload,
        )

        self.assertEqual(response.status_code, 200)
        self.project.refresh_from_db()
        self.assertFalse(self.project.default_can_create_tasks)
        self.assertTrue(self.project.default_can_delete_tasks)
        self.assertFalse(self.project.default_can_edit_tasks)
        self.assertTrue(self.project.default_can_create_boards)
        self.assertFalse(self.project.default_can_invite_members)

    def test_leader_cannot_update_default_permissions_without_a_common_member(self):
        leader = get_user_model().objects.create_user(
            email='lider@example.com',
            password='Senha123!'
        )
        self.project.members.add(leader)
        ProjectMember.objects.create(
            project=self.project,
            user=leader,
            role=ProjectMember.Role.LEADER,
        )
        self.client.force_login(leader)

        response = self.client.post(
            reverse('project_default_member_permissions', args=[self.project.pk]),
            {
                'can_create_tasks': 'false',
                'can_delete_tasks': 'true',
                'can_edit_tasks': 'false',
                'can_create_boards': 'true',
                'can_invite_members': 'false',
            },
        )

        self.assertEqual(response.status_code, 403)

    def test_project_settings_page_restricts_leader_and_member_controls(self):
        leader = get_user_model().objects.create_user(
            email='lider@example.com',
            password='Senha123!'
        )
        another_leader = get_user_model().objects.create_user(
            email='outro-lider@example.com',
            password='Senha123!'
        )
        member = get_user_model().objects.create_user(
            email='integrante@example.com',
            password='Senha123!'
        )
        self.project.members.add(leader, another_leader, member)
        ProjectMember.objects.create(
            project=self.project,
            user=leader,
            role=ProjectMember.Role.LEADER,
        )
        ProjectMember.objects.create(
            project=self.project,
            user=another_leader,
            role=ProjectMember.Role.LEADER,
        )
        ProjectMember.objects.create(project=self.project, user=member)
        self.client.force_login(leader)

        response = self.client.get(
            reverse('project_settings', args=[self.project.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Zona de perigo')
        for target in (leader, another_leader, member):
            self.assertNotContains(
                response,
                reverse('project_member_remove', args=[self.project.pk, target.pk]),
            )
            self.assertNotContains(
                response,
                reverse('project_member_promote', args=[self.project.pk, target.pk]),
            )
            self.assertNotContains(
                response,
                reverse('project_member_demote', args=[self.project.pk, target.pk]),
            )
        self.assertContains(response, 'data-editable="0"')
        self.assertContains(response, 'data-editable="1"')
        self.assertContains(response, 'data-permission="can_create_tasks"')
        self.assertContains(response, 'aria-pressed="true"')
        self.assertContains(response, 'class="permission-toggle is-active"')
        self.assertContains(response, ' disabled')
        self.assertContains(response, 'class="dashboard-main settings-page project-settings-page"')

    def test_project_member_cannot_open_project_settings(self):
        member = get_user_model().objects.create_user(
            email='integrante@example.com',
            password='Senha123!'
        )
        self.project.members.add(member)
        ProjectMember.objects.create(project=self.project, user=member)
        self.client.force_login(member)

        response = self.client.get(
            reverse('project_settings', args=[self.project.pk])
        )

        self.assertRedirects(
            response,
            reverse('project_detail', args=[self.project.pk]),
        )

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