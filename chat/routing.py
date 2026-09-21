from django.urls import re_path

from .consumers import ChatConsumer


websocket_urlpatterns = [
    re_path(
        r"ws/projetos/(?P<project_id>\d+)/chat/$",
        ChatConsumer.as_asgi(),
    ),
]