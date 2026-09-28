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