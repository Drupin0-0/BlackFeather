from django.urls import re_path
from django.urls import path

from .consumers import NotificationConsumer
from .consumers import ChatConsumer


websocket_urlpatterns = [
    re_path(
        r"ws/projetos/(?P<project_code>[A-Z0-9]{6})/chat/$",
        ChatConsumer.as_asgi(),
    ),
    path(
        "ws/notifications/",
        NotificationConsumer.as_asgi(),
    ),
]