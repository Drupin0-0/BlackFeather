from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from django.conf import settings
from django.conf.urls.static import static
from chat import views
from chat.views import send_join_request


urlpatterns = [
    path('admin/', admin.site.urls),

    # Página pública inicial
    path('', TemplateView.as_view(template_name='index.html'), name='home'),
    path(
        'privacidade/',
        TemplateView.as_view(
            template_name='legal/privacy.html',
            extra_context={
                'controller_name': settings.DATA_CONTROLLER_NAME,
                'controller_contact': settings.DATA_CONTROLLER_CONTACT,
                'ai_external_processor_enabled': settings.AI_EXTERNAL_PROCESSOR_ENABLED,
            },
        ),
        name='legal_privacy',
    ),
    path('termos/', TemplateView.as_view(template_name='legal/terms.html'), name='legal_terms'),
    path('acessibilidade/', TemplateView.as_view(template_name='legal/accessibility.html'), name='legal_accessibility'),
    path(
        'suporte/',
        TemplateView.as_view(
            template_name='legal/support.html',
            extra_context={'support_email': settings.SUPPORT_EMAIL},
        ),
        name='support',
    ),

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

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)