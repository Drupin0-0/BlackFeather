import json
import time
from collections import deque
from urllib.parse import urlsplit

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings
from django.db.models import Q
from django.http.request import validate_host

from .events import validated_client_id


class NotesConsumer(AsyncWebsocketConsumer):
    async def send_json(self, payload):
        await self.send(text_data=json.dumps(payload))

    async def connect(self):
        self.project_id = self.scope['url_route']['kwargs']['project_id']
        self.user = self.scope['user']
        self.project_group = f'notes_project_{self.project_id}'
        self.watched_page_id = None
        self.message_times = deque()

        if not self.user.is_authenticated or not self._valid_origin():
            await self.close()
            return
        if not await self.user_can_access_project():
            await self.close()
            return

        await self.channel_layer.group_add(self.project_group, self.channel_name)
        await self.accept()

    def _valid_origin(self):
        headers = dict(self.scope.get('headers', []))
        raw_origin = headers.get(b'origin')
        if not raw_origin:
            return False
        try:
            origin = raw_origin.decode('ascii')
            parsed = urlsplit(origin)
            if parsed.scheme not in {'http', 'https'} or not parsed.hostname:
                return False
            if parsed.port is not None and not 1 <= parsed.port <= 65535:
                return False
            if parsed.username or parsed.password or parsed.path not in {'', '/'} or parsed.query or parsed.fragment:
                return False
            return validate_host(parsed.hostname, settings.ALLOWED_HOSTS)
        except (UnicodeDecodeError, ValueError):
            return False

    async def disconnect(self, close_code):
        if self.watched_page_id is not None:
            await self.channel_layer.group_discard(
                f'notes_page_{self.watched_page_id}',
                self.channel_name,
            )
        if hasattr(self, 'project_group'):
            await self.channel_layer.group_discard(self.project_group, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        if not isinstance(text_data, str):
            return
        try:
            if len(text_data.encode('utf-8')) > 1024:
                return
        except UnicodeEncodeError:
            return
        now = time.monotonic()
        while self.message_times and now - self.message_times[0] >= 1:
            self.message_times.popleft()
        if len(self.message_times) >= 20:
            return
        self.message_times.append(now)

        try:
            payload = json.loads(text_data)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return
        if not isinstance(payload, dict) or not isinstance(payload.get('action'), str):
            return

        action = payload['action']
        if action == 'ping' and set(payload) == {'action'}:
            await self.send_json({'type': 'pong'})
            return
        if action == 'unwatch_page' and set(payload) == {'action'}:
            await self._unwatch_page()
            return
        if action == 'watch_page' and set(payload) == {'action', 'page_id'}:
            page_id = payload['page_id']
            if not isinstance(page_id, int) or isinstance(page_id, bool) or page_id < 1:
                return
            await self._watch_page(page_id)
            return

    async def _watch_page(self, page_id):
        if not await self.user_can_view_page(page_id):
            await self.send_json({'type': 'denied'})
            return
        await self._unwatch_page()
        self.watched_page_id = page_id
        await self.channel_layer.group_add(f'notes_page_{page_id}', self.channel_name)

    async def _unwatch_page(self):
        if self.watched_page_id is None:
            return
        await self.channel_layer.group_discard(
            f'notes_page_{self.watched_page_id}',
            self.channel_name,
        )
        self.watched_page_id = None

    async def _still_project_member(self):
        return await self.user_can_access_project()

    async def _forward_event(self, payload):
        if not await self._still_project_member():
            await self._unwatch_page()
            await self.channel_layer.group_discard(self.project_group, self.channel_name)
            await self.close(code=4403)
            return False
        await self.send_json(payload)
        return True

    async def page_updated(self, event):
        page_id = event.get('page_id')
        version = event.get('version')
        if page_id != self.watched_page_id:
            return
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            return
        if not await self.user_can_view_page(page_id):
            await self._unwatch_page()
            await self.send_json({'type': 'access_lost', 'page_id': page_id})
            return
        payload = {
            'type': 'page_updated',
            'page_id': page_id,
            'version': version,
        }
        origin = validated_client_id(event.get('origin'))
        if origin:
            payload['origin'] = origin
        await self._forward_event(payload)

    async def tree_changed(self, event):
        payload = {'type': 'tree_changed'}
        origin = validated_client_id(event.get('origin'))
        if origin:
            payload['origin'] = origin
        await self._forward_event(payload)

    async def access_changed(self, event):
        if self.watched_page_id is not None and not await self.user_can_view_page(self.watched_page_id):
            page_id = self.watched_page_id
            await self._unwatch_page()
            await self.send_json({'type': 'access_lost', 'page_id': page_id})
        payload = {'type': 'access_changed'}
        await self._forward_event(payload)

    @database_sync_to_async
    def user_can_access_project(self):
        from Tasks.models import Project

        return Project.objects.filter(pk=self.project_id).filter(
            Q(owner_id=self.user.pk) | Q(members__pk=self.user.pk)
        ).exists()

    @database_sync_to_async
    def user_can_view_page(self, page_id):
        from Tasks.models import Project
        from .models import Page
        from .permissions import visible_sections

        project = Project.objects.filter(pk=self.project_id).first()
        if project is None:
            return False
        return Page.objects.filter(
            pk=page_id,
            subsection__section__in=visible_sections(project, self.user),
            subsection__section__project=project,
        ).exists()
