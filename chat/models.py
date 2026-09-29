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