from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from Tasks.models import Project, ProjectMember, Task


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