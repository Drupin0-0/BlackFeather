
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from Tasks.models import Project

from .models import DirectConversation, display_name

User = get_user_model()


def share_a_project(user, other):
    """True se os dois participam (dono ou membro) de ao menos um projeto em comum."""
    return (
        Project.objects
        .filter(Q(owner=user) | Q(members=user))
        .filter(Q(owner=other) | Q(members=other))
        .exists()
    )


def _serialize(conversation, me):
    other = conversation.other_user(me)
    last = conversation.messages.order_by("-created_at").first()

    return {
        "id": conversation.pk,
        "user_id": other.pk,
        "name": display_name(other),
        "last_message": last.content[:80] if last else "",
        "last_at": (last.created_at if last else conversation.created_at).isoformat(),
    }


@login_required
@require_GET
def direct_list(request):
    """Conversas privadas do usuário, da mais recente para a mais antiga."""
    conversations = (
        DirectConversation.for_user(request.user)
        .select_related("user_a", "user_b", "user_a__profile", "user_b__profile")
    )

    data = [_serialize(c, request.user) for c in conversations]
    data.sort(key=lambda item: item["last_at"], reverse=True)

    return JsonResponse({"conversations": data})


@login_required
@require_POST
def direct_open(request, user_id):
    """Abre (ou cria) a conversa privada com outro usuário."""
    if user_id == request.user.pk:
        return JsonResponse(
            {"error": "Você não pode iniciar uma conversa consigo mesmo."},
            status=400,
        )

    other = User.objects.filter(pk=user_id).first()

    if other is None:
        return JsonResponse({"error": "Usuário não encontrado."}, status=404)

    # Segurança: só dá para conversar com quem compartilha um projeto com você
    if not share_a_project(request.user, other):
        return JsonResponse(
            {"error": "Você só pode conversar com pessoas dos seus projetos."},
            status=403,
        )

    conversation = DirectConversation.between(request.user, other)

    return JsonResponse(_serialize(conversation, request.user))
