from django.db.models import Q
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from .models import Project, Task
from .serializers import ProjectSerializer, TaskSerializer


class ProjectViewSet(viewsets.ModelViewSet):

    serializer_class = ProjectSerializer

    def get_queryset(self):
        return Project.objects.filter(
            Q(owner=self.request.user) | Q(members=self.request.user)
        )

    def perform_create(self, serializer):
        project = serializer.save(owner=self.request.user)
        project.members.add(self.request.user)
class TaskViewSet(viewsets.ModelViewSet):
    serializer_class = TaskSerializer
    def get_queryset(self):
        return Task.objects.filter(
            Q(project__owner=self.request.user) | Q(project__members=self.request.user)
        )   
    def perform_create(self, serializer):
        project = serializer.validated_data['project']
        if not (project.owner == self.request.user or self.request.user in project.members.all()):
            raise PermissionDenied("Você não tem acesso a esse projeto.")
        serializer.save()