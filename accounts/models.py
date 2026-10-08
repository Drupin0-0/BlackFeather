from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.db import models
from PIL import Image

class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('O e-mail é obrigatório.')

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superusuário precisa ter is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superusuário precisa ter is_superuser=True.')

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    username = None
    email = models.EmailField(unique=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.email


class CategoryChoices(models.TextChoices):
    PROGRAMMING = 'programming', 'Linguagens de Programação'
    FRONTEND = 'frontend', 'Frontend'
    BACKEND = 'backend', 'Backend'
    DATABASE = 'database', 'Bancos de Dados'      
    DEVOPS = 'devops', 'DevOps & Cloud'           
    MOBILE = 'mobile', 'Mobile & Ferramentas'     

class Technology(models.Model):
    name = models.CharField(max_length=50, unique=True)
    category = models.CharField(max_length=20, choices=CategoryChoices.choices)
    icon_class = models.CharField(max_length=100, blank=True, help_text="Ex: devicon-python-plain colored")

    class Meta:
        verbose_name_plural = "Technologies"

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"


class AvatarSuitChoices(models.TextChoices):
    BLACK = 'black', 'Clássico'
    WINE = 'wine', 'Vinho'
    NAVY = 'navy', 'Azul-Marinho'


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    name = models.CharField(max_length=100)
    bio = models.TextField(blank=True)

    birth_date = models.DateField(null=True, blank=True)
    course_area = models.CharField(max_length=150, blank=True)
    website = models.URLField(blank=True)

    # Avatar: não é mais upload livre de foto — a pessoa escolhe um corvo
    # (cor do paletó) e, opcionalmente, um chapéu, combinados via CSS.
    # Novas cores de paletó = adicionar um choice aqui + um PNG em
    # static/img/avatars/suit-<valor>.png, nada mais muda.
    avatar_suit = models.CharField(
        max_length=20,
        choices=AvatarSuitChoices.choices,
        default=AvatarSuitChoices.BLACK,
    )
    avatar_hat = models.BooleanField(default=False)

    skills = models.ManyToManyField(Technology, blank=True, related_name="profiles")


from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

