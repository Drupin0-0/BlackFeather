import logging
import re

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction


logger = logging.getLogger(__name__)
CLIENT_ID_PATTERN = re.compile(r'^[A-Za-z0-9-]{1,64}$')


def validated_client_id(value):
    if isinstance(value, str) and CLIENT_ID_PATTERN.fullmatch(value):
        return value
    return None


def _send_group_event(group_name, event):
    try:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            raise RuntimeError('A camada de canais não está configurada.')
        async_to_sync(channel_layer.group_send)(group_name, event)
    except Exception:
        logger.exception('Falha ao publicar evento de notas no grupo %s.', group_name)


def publish_project_event(project_id, event_type, origin=None):
    event = {'type': event_type}
    valid_origin = validated_client_id(origin)
    if valid_origin:
        event['origin'] = valid_origin
    transaction.on_commit(
        lambda: _send_group_event(f'notes_project_{project_id}', event)
    )


def publish_page_updated(page_id, version, origin=None):
    event = {
        'type': 'page_updated',
        'page_id': page_id,
        'version': version,
    }
    valid_origin = validated_client_id(origin)
    if valid_origin:
        event['origin'] = valid_origin
    transaction.on_commit(
        lambda: _send_group_event(f'notes_page_{page_id}', event)
    )


def publish_tree_changed(project_id, origin=None):
    publish_project_event(project_id, 'tree_changed', origin)


def publish_access_changed(project_id):
    publish_project_event(project_id, 'access_changed')
