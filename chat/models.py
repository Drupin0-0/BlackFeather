from django.conf import settings
from django.db import models
from accounts.models import User

class Message(models.Model):
    project = models.ForeignKey(
        "Tasks.Project",
        on_delete=models.CASCADE,
        related_name="chat_messages",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )

    content = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.user.profile.name}: {self.content[:50]}"

class JoinRequest(models.Model):
    TYPE_CHOICES = [
        ("invite", "Convite para projeto"),
        ("join", "Pedido para entrar no projeto"),
    ]

    STATUS_CHOICES = [
        ("pending", "Pendente"),
        ("accepted", "Aceita"),
        ("rejected", "Recusada"),
    ]

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_join_requests",
    )

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_join_requests",
    )

    project = models.ForeignKey(
        "Tasks.Project",
        on_delete=models.CASCADE,
        related_name="join_requests",
    )

    request_type = models.CharField(
        max_length=10,
        choices=TYPE_CHOICES,
        default="invite",
    )

    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default="pending",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    responded_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-created_at"]

        constraints = [
            models.UniqueConstraint(
                fields=["sender", "recipient", "project"],
                condition=models.Q(status="pending"),
                name="unique_pending_join_request",
            )
        ]

    def __str__(self):
        return (
            f"{self.sender.username} -> "
            f"{self.recipient.username} | "
            f"{self.project} | "
            f"{self.status}"
        )


class Notification(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="notifications",
    )

    title = models.CharField(max_length=200)

    description = models.TextField()

    is_read = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    join_request = models.ForeignKey(
        "JoinRequest",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.email} - {self.title}"

# ======================================================================
# COLE ESTE BLOCO NO FIM DE  chat/models.py
# (os imports abaixo podem ser mesclados com os que já existem lá)
# ======================================================================

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.db.models import Q


def display_name(user):
    """Nome de exibição: nome do perfil, ou e-mail se não houver perfil.

    (O User deste projeto não tem `username` — o identificador é o e-mail.)
    """
    try:
        name = user.profile.name
    except (ObjectDoesNotExist, AttributeError):
        name = ""
    return name or user.email


class DirectConversation(models.Model):
    """Conversa privada entre dois usuários.

    Convenção: user_a.pk < user_b.pk, sempre. Assim existe no máximo UMA
    conversa por par de pessoas, não importa quem iniciou.
    """

    user_a = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="direct_conversations_as_a",
    )
    user_b = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="direct_conversations_as_b",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user_a", "user_b"],
                name="unique_direct_conversation",
            )
        ]

    def __str__(self):
        return f"DM {self.user_a_id} <-> {self.user_b_id}"

    @classmethod
    def between(cls, first, second):
        """Retorna (ou cria) a conversa entre dois usuários diferentes."""
        if first.pk == second.pk:
            raise ValueError("Não existe conversa privada de um usuário consigo mesmo.")

        user_a, user_b = sorted([first, second], key=lambda u: u.pk)
        conversation, _ = cls.objects.get_or_create(user_a=user_a, user_b=user_b)
        return conversation

    @classmethod
    def for_user(cls, user):
        """Todas as conversas em que o usuário participa."""
        return cls.objects.filter(Q(user_a=user) | Q(user_b=user))

    def includes(self, user):
        return user.pk in (self.user_a_id, self.user_b_id)

    def other_user(self, user):
        return self.user_b if user.pk == self.user_a_id else self.user_a


class DirectMessage(models.Model):
    conversation = models.ForeignKey(
        DirectConversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_direct_messages",
    )
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.sender_id}: {self.content[:30]}"