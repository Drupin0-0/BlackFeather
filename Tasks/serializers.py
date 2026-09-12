from rest_framework import serializers
from .models import Project, Task

class ProjectSerializer(serializers.ModelSerializer):
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S" )
    updated_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")
    class Meta: 
        model = Project
        fields = ['title', 'description', 'owner', 'members', 'created_at', 'updated_at']   
        read_only_fields = ['owner', 'created_at', 'updated_at']
class TaskSerializer(serializers.ModelSerializer):
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S" )
    updated_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")
    class Meta:
        model = Task
        fields = ['project', 'title', 'description', 'status', 'priority', 'deadline', 'task_responsible', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']