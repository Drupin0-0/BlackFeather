from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),

    # URLs próprias
    path('accounts/', include('accounts.urls')),

    # Allauth
    path('accounts/', include('allauth.urls')),

    path('', include('Tasks.urls')),
    path('chat/', include('chat.urls')),
]