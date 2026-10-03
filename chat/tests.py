from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from Tasks.models import Project
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
