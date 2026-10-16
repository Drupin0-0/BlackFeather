from django.db.models import Q

from Tasks.models import ProjectMember
from .models import Section


def project_contains_user(project, user):
    if user is None or not getattr(user, 'is_authenticated', False):
        return False
    if project.owner_id == getattr(user, 'pk', None):
        return True
    return project.members.filter(pk=getattr(user, 'pk', None)).exists()


def visible_sections(project, user):
    if not project_contains_user(project, user):
        return Section.objects.none()

    if project.owner_id == getattr(user, 'pk', None):
        return project.note_sections.all()

    membership = project.memberships.filter(user_id=getattr(user, 'pk', None)).first()
    if membership and membership.role == ProjectMember.Role.LEADER:
        return project.note_sections.all()

    return project.note_sections.filter(
        Q(visibility='shared') | Q(allowed_users=user)
    ).distinct()


def can_manage_sections(project, user):
    if not project_contains_user(project, user):
        return False
    if project.owner_id == getattr(user, 'pk', None):
        return True
    membership = project.memberships.filter(user_id=getattr(user, 'pk', None)).first()
    return bool(membership and membership.role == ProjectMember.Role.LEADER)
