from io import BytesIO
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

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

	def make_png(self):
		content = BytesIO()
		Image.new("RGB", (3, 3), color="#336699").save(content, format="PNG")
		return SimpleUploadedFile("avatar.png", content.getvalue(), content_type="image/png")

	def test_profile_has_back_button(self):
		response = self.client.get(reverse("accounts:view_profile"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Voltar ao painel")

	def test_profile_avatar_upload_is_saved_to_media_storage(self):
		with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
			response = self.client.post(reverse("accounts:view_profile"), {
				"name": "Perfil com foto",
				"avatar": self.make_png(),
				"skills": [],
			})

			self.assertRedirects(response, reverse("accounts:view_profile"))
			profile = self.user.profile
			self.assertTrue(profile.avatar.name)
			self.assertTrue(profile.avatar.storage.exists(profile.avatar.name))

	def test_profile_rejects_non_image_upload(self):
		response = self.client.post(reverse("accounts:view_profile"), {
			"name": "Perfil com arquivo inválido",
			"avatar": SimpleUploadedFile(
				"not-image.png",
				b"isso nao e uma imagem",
				content_type="image/png",
			),
		})

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Envie uma imagem válida")
		self.assertFalse(self.user.profile.avatar)
