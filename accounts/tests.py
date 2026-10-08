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

	def test_profile_defaults_to_classic_crow_without_hat(self):
		self.client.get(reverse("accounts:view_profile"))
		profile = UserProfile.objects.get(user=self.user)

		self.assertEqual(profile.avatar_suit, "black")
		self.assertFalse(profile.avatar_hat)

	def test_profile_avatar_carousel_exposes_all_suit_choices_and_navigation(self):
		response = self.client.get(reverse("accounts:view_profile"))

		self.assertContains(response, "Anterior")
		self.assertContains(response, "Próximo")
		self.assertContains(response, "avatarSuitOrder")
		self.assertContains(response, "value: 'black'")
		self.assertContains(response, "value: 'wine'")
		self.assertContains(response, "value: 'navy'")
		self.assertContains(response, "clip-path: circle(50% at 50% 50%)")
		self.assertContains(response, "background: transparent")
		self.assertContains(response, "border: 0")
		self.assertContains(response, "object-fit: cover")
		self.assertContains(response, "object-position: center 50%")
		self.assertContains(response, "transform: none")

	def test_profile_updates_avatar_suit_and_hat(self):
		response = self.client.post(reverse("accounts:customize_avatar"), {
			"avatar_suit": "wine",
			"avatar_hat": "1",
		})

		self.assertRedirects(response, reverse("accounts:view_profile"))
		profile = self.user.profile
		profile.refresh_from_db()
		self.assertEqual(profile.avatar_suit, "wine")
		self.assertTrue(profile.avatar_hat)

	def test_profile_ignores_invalid_suit_value(self):
		response = self.client.post(reverse("accounts:customize_avatar"), {
			"avatar_suit": "roxo-inexistente",
		})

		self.assertRedirects(response, reverse("accounts:view_profile"))
		profile = self.user.profile
		profile.refresh_from_db()
		self.assertEqual(profile.avatar_suit, "black")

	def test_saving_main_profile_form_does_not_reset_avatar(self):
		self.client.post(reverse("accounts:customize_avatar"), {
			"avatar_suit": "navy",
			"avatar_hat": "1",
		})

		self.client.post(reverse("accounts:view_profile"), {
			"name": "Dono",
			"skills": [],
		})

		profile = self.user.profile
		profile.refresh_from_db()
		self.assertEqual(profile.avatar_suit, "navy")
		self.assertTrue(profile.avatar_hat)
