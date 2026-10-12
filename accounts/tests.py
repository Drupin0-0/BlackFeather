from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Technology, UserProfile


class InitialProfileSetupTests(TestCase):
	def setUp(self):
		self.user = get_user_model().objects.create_user(
			email="novo-usuario@example.com",
			password="Senha123!",
		)
		self.python = Technology.objects.get(name="Python")
		self.react = Technology.objects.get(name="React")
		self.client.force_login(self.user)

	def test_setup_saves_skills_posted_as_names(self):
		response = self.client.post(reverse("accounts:setup_profile"), {
			"name": "Novo Usuário",
			"bio": "Perfil criado agora",
			"skills": ["Python", "React"],
		})

		self.assertRedirects(response, reverse("accounts:dashboard"))
		profile = UserProfile.objects.get(user=self.user)
		self.assertSetEqual(
			set(profile.skills.values_list("pk", flat=True)),
			{self.python.pk, self.react.pk},
		)

	def test_setup_still_accepts_skill_ids(self):
		response = self.client.post(reverse("accounts:setup_profile"), {
			"name": "Novo Usuário",
			"skills": [str(self.python.pk)],
		})

		self.assertRedirects(response, reverse("accounts:dashboard"))
		profile = UserProfile.objects.get(user=self.user)
		self.assertEqual(list(profile.skills.all()), [self.python])


class ProfileSecurityAndAvatarTests(TestCase):
	def setUp(self):
		self.user = get_user_model().objects.create_user(
			email="profile-owner@example.com",
			password="Senha123!",
		)
		self.client.force_login(self.user)

	def test_profile_has_back_button(self):
		response = self.client.get(reverse("accounts:view_profile"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Voltar ao painel")

	def test_profile_defaults_to_crow(self):
		self.client.get(reverse("accounts:view_profile"))
		profile = UserProfile.objects.get(user=self.user)

		self.assertEqual(profile.avatar_bird, "corvo")


	def test_profile_avatar_carousel_exposes_all_birds_and_navigation(self):
		response = self.client.get(reverse("accounts:view_profile"))

		self.assertContains(response, "Selecionar avatar anterior")
		self.assertContains(response, "Selecionar próximo avatar", html=False)
		self.assertContains(response, "avatarOptions")
		self.assertContains(response, "value: 'aguia'")
		self.assertContains(response, "value: 'corvo'")
		self.assertContains(response, "value: 'coruja'")
		self.assertContains(response, "value: 'papagaio'")
		self.assertContains(response, "img/avatars/Aguia.jpg")
		self.assertContains(response, "img/avatars/Corvo.jpg")
		self.assertContains(response, "img/avatars/Coruja.jpg")
		self.assertContains(response, "img/avatars/Papagaio.jpg")

	def test_profile_saves_selected_bird_with_profile_form(self):
		response = self.client.post(reverse("accounts:view_profile"), {
			"name": "Dono",
			"avatar_bird": "coruja",
		})

		self.assertRedirects(response, reverse("accounts:view_profile"))
		profile = self.user.profile
		profile.refresh_from_db()
		self.assertEqual(profile.avatar_bird, "coruja")

	def test_profile_ignores_invalid_bird_value(self):
		response = self.client.post(reverse("accounts:view_profile"), {
			"name": "Dono",
			"avatar_bird": "inexistente",
		})

		self.assertRedirects(response, reverse("accounts:view_profile"))
		profile = self.user.profile
		profile.refresh_from_db()
		self.assertEqual(profile.avatar_bird, "corvo")

	def test_profile_avatar_tag_uses_selected_bird(self):
		profile, _ = UserProfile.objects.get_or_create(user=self.user)
		profile.avatar_bird = "papagaio"
		profile.save()
		response = self.client.get(reverse("accounts:view_profile"))

		self.assertContains(response, "img/avatars/Papagaio.jpg")


class PublicInformationAndLogoutTests(TestCase):
	def setUp(self):
		self.user = get_user_model().objects.create_user(
			email="site-user@example.com",
			password="Senha123!",
		)

	def test_public_information_pages_are_reachable(self):
		for route_name, heading in (
			("legal_terms", "Termos de uso"),
			("legal_privacy", "Aviso de privacidade"),
			("legal_accessibility", "Acessibilidade"),
			("support", "Suporte"),
		):
			with self.subTest(route=route_name):
				response = self.client.get(reverse(route_name))
				self.assertEqual(response.status_code, 200)
				self.assertContains(response, heading)

	def test_logout_rejects_get_and_accepts_post(self):
		self.client.force_login(self.user)

		get_response = self.client.get(reverse("accounts:logout"))
		self.assertEqual(get_response.status_code, 405)
		self.assertTrue(self.client.session.get("_auth_user_id"))

		post_response = self.client.post(reverse("accounts:logout"))
		self.assertRedirects(post_response, reverse("accounts:login"))
		self.assertNotIn("_auth_user_id", self.client.session)
