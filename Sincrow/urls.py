from django.contrib import admin
from django.urls import path, include
from chat import views
from chat.views import send_join_request


urlpatterns = [
    path('admin/', admin.site.urls),

    # URLs próprias
    path('accounts/', include('accounts.urls')),

    # Allauth
    path('accounts/', include('allauth.urls')),

    path('', include('Tasks.urls')),
    path('chat/', include('chat.urls')),
        path(
        "mailbox/",
        views.mailbox,
        name="mailbox",
    ),

    path(
        "mailbox/notification/<int:notification_id>/read/",
        views.mark_notification_read,
        name="mark_notification_read",
    ),

    path(
        "mailbox/mark-all-read/",
        views.mark_all_notifications_read,
        name="mark_all_notifications_read",
    ),
    path(
        "mailbox/join-request/<int:request_id>/respond/",
        views.respond_join_request,
        name="respond_join_request",
    ),
    path(
        "mailbox/project/<str:project_code>/join-request/",
        views.send_join_request,
        name="send_join_request",
    ),
]