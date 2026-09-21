from django.conf import settings
from django.db import models


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