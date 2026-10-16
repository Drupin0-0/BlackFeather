from django.urls import path
from channels.security.websocket import AllowedHostsOriginValidator

from .consumers import NotesConsumer


websocket_urlpatterns = [
    path(
        'ws/projetos/<int:project_id>/notes/',
        AllowedHostsOriginValidator(NotesConsumer.as_asgi()),
        name='notes_websocket',
    ),
]
