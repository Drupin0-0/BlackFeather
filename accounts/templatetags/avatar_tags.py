from django import template

register = template.Library()


@register.inclusion_tag('accounts/_crow_avatar.html')
def render_crow_avatar(profile, size=40, extra_class=''):
    """
    Renderiza o avatar-corvo de um UserProfile: a camada do paletó
    (static/img/avatars/suit-<cor>.png) e, se avatar_hat estiver marcado,
    o chapéu por cima (static/img/avatars/hat.png), posicionado via CSS.

    Uso: {% render_crow_avatar profile size=40 %}
    Ou com classe extra: {% render_crow_avatar profile size=110 extra_class="crow-avatar-preview" %}
    Se `profile` for None (ex: usuário sem perfil criado ainda), cai no
    corvo clássico sem chapéu.
    """
    suit = getattr(profile, 'avatar_suit', 'black') or 'black'
    hat = bool(getattr(profile, 'avatar_hat', False))

    return {
        'suit_image': f'img/avatars/suit-{suit}.png',
        'hat': hat,
        'size': size,
        'extra_class': extra_class,
    }
