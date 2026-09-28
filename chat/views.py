
from django.shortcuts import get_object_or_404, render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render

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