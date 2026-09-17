from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    username = None
    email = models.EmailField(unique=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.email


class CategoryChoices(models.TextChoices):
    PROGRAMMING = 'programming', 'Programming Languages'
    FRONTEND = 'frontend', 'Frontend'
    BACKEND = 'backend', 'Backend'


class Technology(models.Model):
    name = models.CharField(max_length=50, unique=True)
    category = models.CharField(max_length=20, choices=CategoryChoices.choices)
    icon_class = models.CharField(max_length=100, blank=True, help_text="Ex: devicon-python-plain colored")

    class Meta:
        verbose_name_plural = "Technologies"

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    name = models.CharField(max_length=100)
    bio = models.TextField(blank=True)
    birth_date = models.DateField(null=True, blank=True)
    course_area = models.CharField(max_length=150, blank=True)
    website = models.URLField(blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    skills = models.ManyToManyField(Technology, blank=True, related_name="profiles")

    def __str__(self):
        return self.name or self.user.email