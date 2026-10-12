from django import template

register = template.Library()


@register.inclusion_tag('accounts/_crow_avatar.html')
def render_crow_avatar(profile, size=40, extra_class=''):
    bird = getattr(profile, 'avatar_bird', 'corvo') or 'corvo'
    image_by_bird = {
        'aguia': 'Aguia.jpg',
        'corvo': 'Corvo.jpg',
        'coruja': 'Coruja.jpg',
        'papagaio': 'Papagaio.jpg',
    }
    label_by_bird = {
        'aguia': 'Águia',
        'corvo': 'Corvo',
        'coruja': 'Coruja',
        'papagaio': 'Papagaio',
    }

    return {
        'bird_image': f"img/avatars/{image_by_bird.get(bird, 'Corvo.jpg')}",
        'bird_label': label_by_bird.get(bird, 'Corvo'),
        'size': size,
        'extra_class': extra_class,
    }
