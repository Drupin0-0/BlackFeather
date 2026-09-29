
from django.shortcuts import get_object_or_404, render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from .models import Notification, JoinRequest
from .notification_service import create_notification
from django.views.decorators.http import require_POST
from accounts.models import User

from .models import Notification



from Tasks.models import Project


def test_chat(request, project_code):
    project = get_object_or_404(
        Project,
        code=project_code
    )

    return render(
        request,
        "test.html",
        {
            "project": project,
            "project_code": project.code,
        }
    )

@login_required
def mailbox(request):
    notifications = request.user.notifications.all()

    unread_count = notifications.filter(
        is_read=False
    ).count()

    return render(
        request,
        "mailbox/mailbox.html",
        {
            "notifications": notifications,
            "unread_count": unread_count,
        },
    )


@login_required
def mark_notification_read(request, notification_id):
    if request.method != "POST":
        return JsonResponse(
            {"error": "Método não permitido."},
            status=405,
        )

    notification = get_object_or_404(
        Notification,
        pk=notification_id,
        user=request.user,
    )

    notification.is_read = True
    notification.save(update_fields=["is_read"])

    return JsonResponse({"success": True})


@login_required
def mark_all_notifications_read(request):
    if request.method != "POST":
        return JsonResponse(
            {"error": "Método não permitido."},
            status=405,
        )

    request.user.notifications.filter(
        is_read=False
    ).update(is_read=True)

    return JsonResponse({"success": True})

@login_required
@require_POST
def send_join_request(request, project_code):
    username = request.POST.get("username", "").strip()

    if username.startswith("@"):
        username = username[1:].strip()

    if not username:
        return JsonResponse(
            {"success": False, "error": "Digite um username."},
            status=400,
        )

    project = get_object_or_404(
        Project,
        code=project_code,
    )

    if not project.members.filter(
        id=request.user.id
    ).exists() and project.owner_id != request.user.id:
        return JsonResponse(
            {
                "success": False,
                "error": "Você não pode enviar solicitações para este projeto.",
            },
            status=403,
        )

    recipient = User.objects.filter(
        username=username
    ).first()

    if recipient is None:
        return JsonResponse(
            {
                "success": False,
                "error": "Usuário não encontrado.",
            },
            status=404,
        )

    if recipient.id == request.user.id:
        return JsonResponse(
            {
                "success": False,
                "error": "Você não pode enviar uma solicitação para si mesmo.",
            },
            status=400,
        )

    if project.members.filter(
        id=recipient.id
    ).exists():
        return JsonResponse(
            {
                "success": False,
                "error": "Esse usuário já faz parte do projeto.",
            },
            status=409,
        )

    existing_request = JoinRequest.objects.filter(
        sender=request.user,
        recipient=recipient,
        project=project,
        status="pending",
    ).exists()

    if existing_request:
        return JsonResponse(
            {
                "success": False,
                "error": "Já existe uma solicitação pendente.",
            },
            status=409,
        )

    join_request = JoinRequest.objects.create(
        sender=request.user,
        recipient=recipient,
        project=project,
    )

    create_notification(
        user=recipient,
        title="Nova solicitação",
        description=(
            f"@{request.user.username} "
            f"enviou uma solicitação para entrar em "
            f"'{project.name}'."
        ),
        join_request=join_request,
    )

    return JsonResponse(
        {
            "success": True,
            "request_id": join_request.id,
        }
    )