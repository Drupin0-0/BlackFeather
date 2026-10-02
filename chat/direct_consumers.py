
import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.db.models import Q

from .models import DirectConversation, DirectMessage, display_name

MAX_LENGTH = 2000
HISTORY_LIMIT = 100


class DirectChatConsumer(AsyncWebsocketConsumer):
    """WebSocket de uma conversa privada: ws/privado/<conversation_id>/"""

    async def connect(self):
        self.user = self.scope["user"]
        self.conversation_id = int(self.scope["url_route"]["kwargs"]["conversation_id"])
        self.group_name = None

        # Só participantes autenticados da conversa podem conectar
        if not self.user.is_authenticated or not await self.is_participant():
            await self.close(code=4403)
            return

        self.group_name = f"dm_{self.conversation_id}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        await self.send(text_data=json.dumps({
            "type": "history",
            "messages": await self.get_history(),
        }))

    async def disconnect(self, code):
        if self.group_name:
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        try:
            data = json.loads(text_data or "")
        except ValueError:
            return

        content = str(data.get("message", "")).strip()

        if not content or len(content) > MAX_LENGTH:
            return

        payload = await self.save_message(content)

        await self.channel_layer.group_send(
            self.group_name,
            {"type": "direct_message", **payload},
        )

    # Handler do evento "direct_message" enviado ao grupo
    async def direct_message(self, event):
        await self.send(text_data=json.dumps({
            "type": "message",
            "sender_id": event["sender_id"],
            "username": event["username"],
            "message": event["message"],
            "created_at": event["created_at"],
        }))

    # ------------------------------------------------------------
    # Acesso ao banco (sync -> async)
    # ------------------------------------------------------------
    @database_sync_to_async
    def is_participant(self):
        return DirectConversation.objects.filter(
            Q(user_a=self.user) | Q(user_b=self.user),
            pk=self.conversation_id,
        ).exists()

    @database_sync_to_async
    def save_message(self, content):
        message = DirectMessage.objects.create(
            conversation_id=self.conversation_id,
            sender=self.user,
            content=content,
        )
        return self._serialize(message)

    @database_sync_to_async
    def get_history(self):
        queryset = (
            DirectMessage.objects
            .filter(conversation_id=self.conversation_id)
            .select_related("sender", "sender__profile")
            .order_by("-created_at")[:HISTORY_LIMIT]
        )
        return [self._serialize(m) for m in reversed(list(queryset))]

    @staticmethod
    def _serialize(message):
        return {
            "sender_id": message.sender_id,
            "username": display_name(message.sender),
            "message": message.content,
            "created_at": message.created_at.isoformat(),
        }
