from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import Notification


def create_notification(
    user,
    title,
    description,
    join_request=None,
):
    notification = Notification.objects.create(
        user=user,
        title=title,
        description=description,
        join_request=join_request,
    )

    channel_layer = get_channel_layer()

    async_to_sync(channel_layer.group_send)(
        f"user_notifications_{user.pk}",
        {
            "type": "notification_message",
            "notification": {
                "id": notification.pk,
                "title": notification.title,
                "description": notification.description,
                "is_read": notification.is_read,
                "created_at": notification.created_at.isoformat(),
                "join_request_id": (
                    notification.join_request_id
                    if notification.join_request_id
                    else None
                ),
            },
        },
    )

    return notification