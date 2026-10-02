from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages as django_messages
from django.http import JsonResponse
from django.db.models import Q
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone
from django.shortcuts import get_object_or_404, render
from .models import Notification, JoinRequest
from .notification_service import create_notification
from django.views.decorators.http import require_POST
from accounts.models import User

from .models import Notification



from Tasks.models import Project


@login_required
def chat_list_view(request):
    projects = Project.objects.filter(
        Q(owner=request.user) | Q(members=request.user)
    ).select_related(
        'owner__profile'
    ).prefetch_related(
        'members__profile'
    ).distinct().order_by('title')

    return render(request, 'chats.html', {'projects': projects})


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
@require_POST
def mark_notification_read(request, notification_id):
    notification = get_object_or_404(
        Notification,
        pk=notification_id,
        user=request.user,
    )

    notification.is_read = True
    notification.save(update_fields=["is_read"])

    return JsonResponse({"success": True})


@login_required
@require_POST
def mark_all_notifications_read(request):
    request.user.notifications.filter(
        is_read=False
    ).update(is_read=True)

    return JsonResponse({"success": True})

@login_required
@require_POST
def send_join_request(request, project_code):
    email = request.POST.get("username", "").strip()

    if not email:
        return JsonResponse(
            {"success": False, "error": "Digite o e-mail do usuário."},
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

    recipient = User.objects.filter(email__iexact=email).first()

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
        request_type="invite",
    )

    sender_name = request.user.email
    try:
        sender_name = request.user.profile.name or sender_name
    except ObjectDoesNotExist:
        pass

    create_notification(
        user=recipient,
        title="Nova solicitação",
        description=(
            f"{sender_name} "
            f"enviou uma solicitação para entrar em "
            f"'{project.title}'."
        ),
        join_request=join_request,
    )

    return JsonResponse(
        {
            "success": True,
            "request_id": join_request.id,
        }
    )

@login_required
@require_POST
def request_project_join(request):
    project_code = (request.POST.get("project_code") or "").strip().upper()
    if not project_code:
        django_messages.error(request, "Digite o código do projeto.")
        return redirect("project_list")

    project = Project.objects.filter(code__iexact=project_code).select_related("owner").first()
    if project is None:
        django_messages.error(request, "Não encontramos um projeto com esse código.")
        return redirect("project_list")

    if project.owner_id == request.user.pk or project.members.filter(pk=request.user.pk).exists():
        django_messages.info(request, "Você já faz parte desse projeto.")
        return redirect("project_list")

    pending_request = JoinRequest.objects.filter(
        sender=request.user,
        recipient=project.owner,
        project=project,
        request_type="join",
        status="pending",
    ).exists()
    if pending_request:
        django_messages.info(request, "Seu pedido para esse projeto já está aguardando resposta.")
        return redirect("project_list")

    join_request = JoinRequest.objects.create(
        sender=request.user,
        recipient=project.owner,
        project=project,
        request_type="join",
    )
    requester_name = request.user.email
    try:
        requester_name = request.user.profile.name or requester_name
    except ObjectDoesNotExist:
        pass

    create_notification(
        user=project.owner,
        title="Pedido para entrar no projeto",
        description=f"{requester_name} quer participar do projeto '{project.title}'.",
        join_request=join_request,
    )
    django_messages.success(request, "Pedido enviado! O responsável pelo projeto foi notificado.")
    return redirect("project_list")


@login_required
@require_POST
def respond_join_request(request, request_id):
    action = request.POST.get("action")

    if action not in ("accept", "reject"):
        return JsonResponse(
            {
                "success": False,
                "error": "Ação inválida.",
            },
            status=400,
        )

    join_request = get_object_or_404(
        JoinRequest,
        pk=request_id,
        recipient=request.user,
        status="pending",
    )

    if action == "accept":
        project = join_request.project
        accepted_user = (
            join_request.sender
            if join_request.request_type == "join"
            else join_request.recipient
        )

        if not project.members.filter(id=accepted_user.id).exists():
            project.members.add(accepted_user)

        join_request.status = "accepted"

        message = "Solicitação aceita."

    else:
        join_request.status = "rejected"

        message = "Solicitação recusada."

    join_request.responded_at = timezone.now()
    join_request.save(update_fields=["status", "responded_at"])

    Notification.objects.filter(
        join_request=join_request,
        user=request.user,
    ).update(is_read=True)

    recipient_name = request.user.email
    try:
        recipient_name = request.user.profile.name or recipient_name
    except ObjectDoesNotExist:
        pass

    if join_request.request_type == "join":
        response_description = (
            f"Seu pedido para entrar no projeto '{join_request.project.title}' "
            f"foi {'aceito' if action == 'accept' else 'recusado'} por {recipient_name}."
        )
    else:
        response_description = (
            f"{recipient_name} {'aceitou' if action == 'accept' else 'recusou'} "
            f"seu convite para o projeto '{join_request.project.title}'."
        )

    create_notification(
        user=join_request.sender,
        title="Resposta à solicitação",
        description=response_description,
    )

    return JsonResponse(
        {
            "success": True,
            "status": join_request.status,
            "message": message,
        }
    )