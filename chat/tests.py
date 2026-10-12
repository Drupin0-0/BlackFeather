from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from Tasks.models import Project, ProjectMember
from accounts.models import UserProfile
from .models import JoinRequest, Notification


class NotificationFlowTests(TestCase):
	def setUp(self):
		User = get_user_model()
		self.sender = User.objects.create_user(
			email="sender@example.com",
			password="Senha123!",
		)
		self.recipient = User.objects.create_user(
			email="recipient@example.com",
			password="Senha123!",
		)
		self.project = Project.objects.create(
			title="Projeto de notificações",
			description="",
			owner=self.sender,
		)
		self.project.members.add(self.sender)

	def test_mailbox_renders_notification_description(self):
		self.client.force_login(self.recipient)
		Notification.objects.create(
			user=self.recipient,
			title="Aviso de teste",
			description="Descrição exibida na central",
		)

		response = self.client.get(reverse("mailbox"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Descrição exibida na central")

	def test_pending_join_request_displays_response_buttons_and_sort_control(self):
		join_request = JoinRequest.objects.create(
			sender=self.sender,
			recipient=self.recipient,
			project=self.project,
		)
		Notification.objects.create(
			user=self.recipient,
			title="Convite para projeto",
			description="Convite pendente",
			join_request=join_request,
		)
		self.client.force_login(self.recipient)

		response = self.client.get(reverse("mailbox"))

		self.assertContains(response, "Aceitar")
		self.assertContains(response, "Recusar")
		self.assertContains(response, 'id="sort-notifications"')

	def test_join_request_by_email_creates_notification(self):
		self.client.force_login(self.sender)

		response = self.client.post(
			reverse("send_join_request", args=[self.project.code]),
			{"username": self.recipient.email},
		)

		self.assertEqual(response.status_code, 200)
		notification = Notification.objects.get(user=self.recipient)
		self.assertIn(self.project.title, notification.description)
		self.assertTrue(notification.join_request_id)

	def test_project_invite_requires_recipient_acceptance(self):
		self.client.force_login(self.sender)

		response = self.client.post(
			reverse("send_join_request", args=[self.project.code]),
			{"username": self.recipient.email},
		)

		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.json()["success"])
		self.assertFalse(self.project.members.filter(pk=self.recipient.pk).exists())
		self.assertTrue(
			JoinRequest.objects.filter(
				project=self.project,
				recipient=self.recipient,
				request_type="invite",
				status="pending",
			).exists()
		)

	def test_member_without_invite_permission_cannot_invite(self):
		member = get_user_model().objects.create_user(
			email="member@example.com",
			password="Senha123!",
		)
		self.project.members.add(member)
		ProjectMember.objects.create(
			project=self.project,
			user=member,
			can_invite_members=False,
		)
		self.client.force_login(member)

		response = self.client.post(
			reverse("send_join_request", args=[self.project.code]),
			{"username": self.recipient.email},
		)

		self.assertEqual(response.status_code, 403)

	def test_request_to_join_by_code_notifies_project_owner(self):
		self.client.force_login(self.recipient)

		response = self.client.post(
			reverse("request_project_join"),
			{"project_code": self.project.code.lower()},
		)

		self.assertRedirects(response, reverse("project_list"))
		self.assertFalse(self.project.members.filter(pk=self.recipient.pk).exists())
		join_request = JoinRequest.objects.get(
			sender=self.recipient,
			recipient=self.sender,
			project=self.project,
			request_type="join",
			status="pending",
		)
		self.assertTrue(
			Notification.objects.filter(
				user=self.sender,
				join_request=join_request,
				title="Pedido para entrar no projeto",
			).exists()
		)

	def test_project_owner_acceptance_adds_user_who_requested_by_code(self):
		self.project.default_can_create_tasks = False
		self.project.default_can_delete_tasks = True
		self.project.save(update_fields=[
			"default_can_create_tasks",
			"default_can_delete_tasks",
		])
		join_request = JoinRequest.objects.create(
			sender=self.recipient,
			recipient=self.sender,
			project=self.project,
			request_type="join",
		)
		Notification.objects.create(
			user=self.sender,
			title="Pedido para entrar no projeto",
			description="Pedido de entrada",
			join_request=join_request,
		)
		self.client.force_login(self.sender)

		response = self.client.post(
			reverse("respond_join_request", args=[join_request.pk]),
			{"action": "accept"},
		)

		self.assertEqual(response.status_code, 200)
		self.assertTrue(self.project.members.filter(pk=self.recipient.pk).exists())
		self.assertTrue(
			ProjectMember.objects.filter(
				project=self.project,
				user=self.recipient,
				role=ProjectMember.Role.MEMBER,
			).exists()
		)
		membership = ProjectMember.objects.get(
			project=self.project,
			user=self.recipient,
		)
		self.assertFalse(membership.can_create_tasks)
		self.assertTrue(membership.can_delete_tasks)
		self.assertTrue(
			Notification.objects.filter(
				user=self.recipient,
				description__contains="foi aceito",
			).exists()
		)

	def test_recipient_can_accept_request_from_notification(self):
		join_request = JoinRequest.objects.create(
			sender=self.sender,
			recipient=self.recipient,
			project=self.project,
		)
		original_notification = Notification.objects.create(
			user=self.recipient,
			title="Nova solicitação",
			description="Solicitação de entrada",
			join_request=join_request,
		)
		self.client.force_login(self.recipient)

		response = self.client.post(
			reverse("respond_join_request", args=[join_request.pk]),
			{"action": "accept"},
		)

		self.assertEqual(response.status_code, 200)
		self.assertTrue(self.project.members.filter(pk=self.recipient.pk).exists())
		join_request.refresh_from_db()
		original_notification.refresh_from_db()
		self.assertEqual(join_request.status, "accepted")
		self.assertTrue(original_notification.is_read)
		self.assertTrue(Notification.objects.filter(user=self.sender).exists())

	def test_recipient_can_reject_invitation_without_joining_project(self):
		join_request = JoinRequest.objects.create(
			sender=self.sender,
			recipient=self.recipient,
			project=self.project,
		)
		self.client.force_login(self.recipient)

		response = self.client.post(
			reverse("respond_join_request", args=[join_request.pk]),
			{"action": "reject"},
		)

		self.assertEqual(response.status_code, 200)
		join_request.refresh_from_db()
		self.assertEqual(join_request.status, "rejected")
		self.assertFalse(self.project.members.filter(pk=self.recipient.pk).exists())
		self.assertTrue(
			Notification.objects.filter(
				user=self.sender,
				title="Resposta à solicitação",
				description__contains="recusou",
			).exists()
		)


class DirectConversationAvatarTests(TestCase):
	def setUp(self):
		User = get_user_model()
		self.me = User.objects.create_user(email="me@example.com", password="Senha123!")
		self.other = User.objects.create_user(email="other@example.com", password="Senha123!")
		UserProfile.objects.create(user=self.me, name="Eu", avatar_bird="corvo")
		UserProfile.objects.create(user=self.other, name="Outra pessoa", avatar_bird="aguia")
		self.project = Project.objects.create(title="Projeto compartilhado", owner=self.me)
		self.project.members.add(self.me, self.other)
		self.client.force_login(self.me)

	def test_direct_conversation_endpoints_include_selected_avatar(self):
		opened = self.client.post(reverse("direct_open", args=[self.other.pk]))
		self.assertEqual(opened.status_code, 200)
		self.assertEqual(opened.json()["avatar_bird"], "aguia")

		listed = self.client.get(reverse("direct_list"))
		self.assertEqual(listed.status_code, 200)
		self.assertEqual(listed.json()["conversations"][0]["avatar_bird"], "aguia")

	def test_project_chat_member_markup_includes_selected_avatar(self):
		response = self.client.get(reverse("chat_list"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'data-avatar-bird="aguia"')


class ProjectChatAccessTests(TestCase):
	def setUp(self):
		User = get_user_model()
		self.owner = User.objects.create_user(email="chat-owner@example.com", password="Senha123!")
		self.member = User.objects.create_user(email="chat-member@example.com", password="Senha123!")
		self.outsider = User.objects.create_user(email="chat-outsider@example.com", password="Senha123!")
		self.project = Project.objects.create(title="Chat privado", owner=self.owner)
		self.project.members.add(self.owner, self.member)

	def test_anonymous_user_is_redirected_to_login(self):
		response = self.client.get(reverse("project_chat", args=[self.project.code]))

		self.assertEqual(response.status_code, 302)
		self.assertIn(reverse("accounts:login"), response["Location"])

	def test_non_member_cannot_open_project_chat(self):
		self.client.force_login(self.outsider)

		response = self.client.get(reverse("project_chat", args=[self.project.code]))

		self.assertEqual(response.status_code, 403)

	def test_project_member_can_open_project_chat(self):
		self.client.force_login(self.member)

		response = self.client.get(reverse("project_chat", args=[self.project.code]))

		self.assertEqual(response.status_code, 200)
