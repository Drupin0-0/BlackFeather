import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.db import models

from .models import Message


class ChatConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.project_id = self.scope["url_route"]["kwargs"]["project_id"]

        if not self.scope["user"].is_authenticated:
            await self.close()
            return

        if not await self.user_can_access_project():
            await self.close()
            return

        self.room_group_name = f"project_{self.project_id}"

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name,
        )

        await self.accept()

        # Carrega o histórico do projeto
        messages = await self.get_message_history()

        await self.send(
            text_data=json.dumps({
                "type": "history",
                "messages": messages,
            })
        )

    async def disconnect(self, close_code):
        if hasattr(self, "room_group_name"):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name,
            )

    async def receive(self, text_data):
        data = json.loads(text_data)

        content = data.get("message", "").strip()

        if not content:
            return

        message = await self.save_message(content)
        username = await self.get_user_name()

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "chat_message",
                "message": message.content,
                "username": username,
                "created_at": message.created_at.isoformat(),
            },
        )

    async def chat_message(self, event):
        await self.send(
            text_data=json.dumps({
                "type": "message",
                "message": event["message"],
                "username": event["username"],
                "created_at": event["created_at"],
            })
        )

    @database_sync_to_async
    def user_can_access_project(self):
        from Tasks.models import Project

        return Project.objects.filter(
            id=self.project_id
        ).filter(
            models.Q(owner=self.scope["user"]) |
            models.Q(members=self.scope["user"])
        ).exists()

    @database_sync_to_async
    def save_message(self, content):
        return Message.objects.create(
            project_id=self.project_id,
            user=self.scope["user"],
            content=content,
        )

    @database_sync_to_async
    def get_user_name(self):
        user = self.scope["user"]

        if hasattr(user, "profile"):
            return user.profile.name

        return user.email

    @database_sync_to_async
    def get_message_history(self):
        messages = Message.objects.filter(
            project_id=self.project_id
        ).select_related(
            "user",
            "user__profile",
        )

        history = []

        for message in messages:
            user = message.user

            if hasattr(user, "profile"):
                username = user.profile.name
            else:
                username = user.email

            history.append({
                "message": message.content,
                "username": username,
                "created_at": message.created_at.isoformat(),
            })

        return history