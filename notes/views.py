import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from Tasks.models import Project
from .models import Page, Section, Subsection
from .events import publish_access_changed, publish_page_updated, publish_tree_changed, validated_client_id
from .permissions import can_manage_sections, project_contains_user, visible_sections
from .validators import MAX_CONTENT_BYTES, validate_page_content


def _client_origin(request):
    return validated_client_id(request.headers.get('X-Notes-Client'))


def _normalize_title(value):
    title = (value or '').strip()
    if len(title) > 100:
        return None, 'O título deve ter no máximo 100 caracteres.'
    if not title:
        return None, 'O título não pode ficar vazio.'
    return title, None


def _project_member_project(project_id, user):
    project = get_object_or_404(Project.objects.select_related('owner'), pk=project_id)
    if not project_contains_user(project, user):
        raise PermissionDenied
    return project


def _section_for_project(project, section_id, user):
    return get_object_or_404(visible_sections(project, user), pk=section_id)


def _subsection_for_project(project, subsection_id, user):
    return get_object_or_404(
        Subsection.objects.select_related('section__project').filter(
            section__in=visible_sections(project, user),
            section__project=project,
        ),
        pk=subsection_id,
    )


def _page_for_project(project, page_id, user, for_update=False):
    pages = Page.objects
    if for_update:
        pages = pages.select_for_update()
    else:
        pages = pages.select_related('subsection__section__project')
    return get_object_or_404(
        pages.filter(
            subsection__section__in=visible_sections(project, user),
            subsection__section__project=project,
        ),
        pk=page_id,
    )


def _serialize_section(section):
    return {
        'id': section.pk,
        'title': section.title,
        'order': section.order,
        'visibility': section.visibility,
        'subsections': [_serialize_subsection(sub) for sub in section.subsections.all()],
    }


def _serialize_subsection(subsection):
    return {
        'id': subsection.pk,
        'title': subsection.title,
        'order': subsection.order,
        'pages': [_serialize_page(page) for page in subsection.pages.all()],
    }


def _serialize_page(page):
    return {
        'id': page.pk,
        'title': page.title,
        'order': page.order,
    }


def _serialize_tree(project, user):
    sections = visible_sections(project, user).prefetch_related('subsections__pages')
    return {
        'sections': [_serialize_section(section) for section in sections],
    }


@login_required
def project_notes_view(request, project_id):
    project = get_object_or_404(Project.objects.select_related('owner', 'owner__profile'), pk=project_id)
    if request.user.pk != project.owner_id and not project.members.filter(pk=request.user.pk).exists():
        raise Http404

    members = []
    for member in project.members.select_related('profile').exclude(pk=project.owner_id).order_by('pk'):
        profile = getattr(member, 'profile', None)
        members.append({
            'id': member.pk,
            'name': (profile.name if profile else None) or member.email,
        })

    return render(
        request,
        'project_notes.html',
        {
            'project': project,
            'can_manage_settings': project.can_manage_settings(request.user),
            'can_manage_notes_sections': can_manage_sections(project, request.user),
            'notes_members': members,
            'notes_api_base': reverse('project_notes', args=[project.pk]) + 'api/',
            'active_tab': 'notes',
        },
    )


@login_required
def notes_tree_view(request, project_id):
    try:
        project = _project_member_project(project_id, request.user)
    except PermissionDenied:
        return JsonResponse({'error': 'Você não tem acesso a este projeto.'}, status=404)

    tree = _serialize_tree(project, request.user)
    return JsonResponse(tree)


@login_required
@require_http_methods(['POST'])
def section_create(request, project_id):
    try:
        project = _project_member_project(project_id, request.user)
    except PermissionDenied:
        return JsonResponse({'error': 'Você não tem acesso a este projeto.'}, status=404)

    if not can_manage_sections(project, request.user):
        return JsonResponse({'error': 'Você não pode gerenciar seções deste projeto.'}, status=403)

    title, error = _normalize_title(request.POST.get('title'))
    if error:
        return JsonResponse({'error': error}, status=400)

    visibility = request.POST.get('visibility', 'shared')
    if visibility not in {'shared', 'private'}:
        return JsonResponse({'error': 'Visibilidade inválida.'}, status=400)
    allowed_ids = request.POST.getlist('allowed_users')
    valid_members = project.members.filter(pk__in=allowed_ids)
    if set(map(str, valid_members.values_list('pk', flat=True))) != set(allowed_ids):
        return JsonResponse({'error': 'Selecione apenas integrantes deste projeto.'}, status=400)

    section = Section.objects.create(
        project=project,
        title=title,
        order=project.note_sections.count(),
        visibility=visibility,
        created_by=request.user,
    )

    if visibility == 'private':
        section.allowed_users.set(valid_members.distinct())

    publish_tree_changed(project.pk, _client_origin(request))
    return JsonResponse({'success': True, 'section': _serialize_section(section)})


@login_required
@require_http_methods(['POST'])
def section_rename(request, project_id, section_id):
    try:
        project = _project_member_project(project_id, request.user)
    except PermissionDenied:
        return JsonResponse({'error': 'Você não tem acesso a este projeto.'}, status=404)

    section = _section_for_project(project, section_id, request.user)
    if not can_manage_sections(project, request.user):
        return JsonResponse({'error': 'Você não pode renomear seções deste projeto.'}, status=403)
    title, error = _normalize_title(request.POST.get('title'))
    if error:
        return JsonResponse({'error': error}, status=400)

    section.title = title
    section.save(update_fields=['title'])
    publish_tree_changed(project.pk, _client_origin(request))
    return JsonResponse({'success': True, 'section': _serialize_section(section)})


@login_required
@require_http_methods(['POST'])
def section_delete(request, project_id, section_id):
    try:
        project = _project_member_project(project_id, request.user)
    except PermissionDenied:
        return JsonResponse({'error': 'Você não tem acesso a este projeto.'}, status=404)

    section = _section_for_project(project, section_id, request.user)
    if not can_manage_sections(project, request.user):
        return JsonResponse({'error': 'Você não pode excluir seções deste projeto.'}, status=403)

    page_count = Page.objects.filter(subsection__section=section).count()
    subsection_count = section.subsections.count()
    section.delete()
    origin = _client_origin(request)
    publish_tree_changed(project.pk, origin)
    publish_access_changed(project.pk)
    return JsonResponse({
        'success': True,
        'deleted_section_id': section_id,
        'subsection_count': subsection_count,
        'page_count': page_count,
    })


@login_required
@require_http_methods(['POST'])
def section_reorder(request, project_id, section_id):
    try:
        project = _project_member_project(project_id, request.user)
    except PermissionDenied:
        return JsonResponse({'error': 'Você não tem acesso a este projeto.'}, status=404)

    section = _section_for_project(project, section_id, request.user)
    if not can_manage_sections(project, request.user):
        return JsonResponse({'error': 'Você não pode reorganizar seções deste projeto.'}, status=403)
    try:
        order = int(request.POST.get('order', section.order))
    except ValueError:
        return JsonResponse({'error': 'Ordem inválida.'}, status=400)

    section.order = order
    section.save(update_fields=['order'])
    publish_tree_changed(project.pk, _client_origin(request))
    return JsonResponse({'success': True, 'section': _serialize_section(section)})


@login_required
@require_http_methods(['GET', 'POST'])
def section_visibility_update(request, project_id, section_id):
    try:
        project = _project_member_project(project_id, request.user)
    except PermissionDenied:
        return JsonResponse({'error': 'Você não tem acesso a este projeto.'}, status=404)

    section = _section_for_project(project, section_id, request.user)
    if not can_manage_sections(project, request.user):
        return JsonResponse({'error': 'Você não pode alterar a privacidade desta seção.'}, status=403)

    if request.method == 'GET':
        return JsonResponse({
            'allowed_users': list(section.allowed_users.values_list('pk', flat=True)),
        })

    visibility = request.POST.get('visibility', section.visibility)
    if visibility not in {'shared', 'private'}:
        return JsonResponse({'error': 'Visibilidade inválida.'}, status=400)

    allowed_ids = request.POST.getlist('allowed_users')
    if visibility == 'private':
        valid_members = project.members.filter(pk__in=allowed_ids)
        if set(map(str, valid_members.values_list('pk', flat=True))) != set(allowed_ids):
            return JsonResponse({'error': 'Selecione apenas integrantes deste projeto.'}, status=400)
        section.allowed_users.set(valid_members.distinct())
    else:
        section.allowed_users.clear()

    section.visibility = visibility
    section.save(update_fields=['visibility'])
    origin = _client_origin(request)
    publish_access_changed(project.pk)
    publish_tree_changed(project.pk, origin)
    return JsonResponse({'success': True, 'section': _serialize_section(section)})


@login_required
@require_http_methods(['POST'])
def subsection_create(request, project_id, section_id):
    try:
        project = _project_member_project(project_id, request.user)
    except PermissionDenied:
        return JsonResponse({'error': 'Você não tem acesso a este projeto.'}, status=404)

    section = _section_for_project(project, section_id, request.user)

    title, error = _normalize_title(request.POST.get('title'))
    if error:
        return JsonResponse({'error': error}, status=400)

    subsection = Subsection.objects.create(
        section=section,
        title=title,
        order=section.subsections.count(),
        theme=request.POST.get('theme', 'dark'),
    )
    publish_tree_changed(project.pk, _client_origin(request))
    return JsonResponse({'success': True, 'subsection': _serialize_subsection(subsection)})


@login_required
@require_http_methods(['POST'])
def subsection_rename(request, project_id, subsection_id):
    try:
        project = _project_member_project(project_id, request.user)
    except PermissionDenied:
        return JsonResponse({'error': 'Você não tem acesso a este projeto.'}, status=404)

    subsection = _subsection_for_project(project, subsection_id, request.user)

    title, error = _normalize_title(request.POST.get('title'))
    if error:
        return JsonResponse({'error': error}, status=400)

    subsection.title = title
    subsection.save(update_fields=['title'])
    publish_tree_changed(project.pk, _client_origin(request))
    return JsonResponse({'success': True, 'subsection': _serialize_subsection(subsection)})


@login_required
@require_http_methods(['POST'])
def subsection_delete(request, project_id, subsection_id):
    try:
        project = _project_member_project(project_id, request.user)
    except PermissionDenied:
        return JsonResponse({'error': 'Você não tem acesso a este projeto.'}, status=404)

    subsection = _subsection_for_project(project, subsection_id, request.user)

    page_count = subsection.pages.count()
    subsection.delete()
    origin = _client_origin(request)
    publish_tree_changed(project.pk, origin)
    publish_access_changed(project.pk)
    return JsonResponse({'success': True, 'deleted_subsection_id': subsection_id, 'page_count': page_count})


@login_required
@require_http_methods(['POST'])
def subsection_reorder(request, project_id, subsection_id):
    try:
        project = _project_member_project(project_id, request.user)
    except PermissionDenied:
        return JsonResponse({'error': 'Você não tem acesso a este projeto.'}, status=404)

    subsection = _subsection_for_project(project, subsection_id, request.user)

    try:
        order = int(request.POST.get('order', subsection.order))
    except ValueError:
        return JsonResponse({'error': 'Ordem inválida.'}, status=400)

    subsection.order = order
    subsection.save(update_fields=['order'])
    publish_tree_changed(project.pk, _client_origin(request))
    return JsonResponse({'success': True, 'subsection': _serialize_subsection(subsection)})


@login_required
@require_http_methods(['POST'])
def page_create(request, project_id, subsection_id):
    try:
        project = _project_member_project(project_id, request.user)
    except PermissionDenied:
        return JsonResponse({'error': 'Você não tem acesso a este projeto.'}, status=404)

    subsection = _subsection_for_project(project, subsection_id, request.user)
    title, error = _normalize_title(request.POST.get('title'))
    if error:
        return JsonResponse({'error': error}, status=400)

    page = Page.objects.create(
        subsection=subsection,
        title=title,
        order=subsection.pages.count(),
    )
    publish_tree_changed(project.pk, _client_origin(request))
    return JsonResponse({'success': True, 'page': _serialize_page(page)})


@login_required
@require_http_methods(['GET', 'PUT'])
def page_content_view(request, project_id, page_id):
    try:
        project = _project_member_project(project_id, request.user)
    except PermissionDenied:
        return JsonResponse({'error': 'Você não tem acesso a este projeto.'}, status=404)

    page = _page_for_project(project, page_id, request.user)

    if request.method == 'GET':
        try:
            content = validate_page_content(page.content)
        except ValueError as error:
            return JsonResponse({'error': str(error)}, status=400)
        return JsonResponse({
            'id': page.pk,
            'title': page.title,
            'content': content,
            'version': page.version,
            'updated_at': page.updated_at.isoformat() if page.updated_at else None,
        })

    if len(request.body) > MAX_CONTENT_BYTES:
        return JsonResponse({'error': 'O conteúdo excede o limite de 2 MB.'}, status=400)

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({'error': 'JSON inválido.'}, status=400)

    if not isinstance(payload, dict):
        return JsonResponse({'error': 'O payload deve ser um objeto JSON.'}, status=400)

    if 'content' not in payload:
        return JsonResponse({'error': 'O campo content é obrigatório.'}, status=400)

    sent_version = payload.get('version')
    if not isinstance(sent_version, int) or isinstance(sent_version, bool):
        return JsonResponse({'error': 'A versão atual da página é obrigatória.'}, status=400)
    with transaction.atomic():
        page = _page_for_project(project, page_id, request.user, for_update=True)
        if sent_version != page.version:
            return JsonResponse({
                'error': 'A página foi alterada por outra pessoa. Suas alterações locais serão mantidas.',
                'current_version': page.version,
            }, status=409)

        try:
            content = validate_page_content(payload['content'])
        except ValueError as error:
            return JsonResponse({'error': str(error)}, status=400)

        page.content = content
        page.version += 1
        page.updated_by = request.user
        page.save(update_fields=['content', 'version', 'updated_by', 'updated_at'])
    publish_page_updated(
        page.pk,
        page.version,
        _client_origin(request),
    )
    return JsonResponse({
        'success': True,
        'page': _serialize_page(page),
        'content': content,
        'version': page.version,
    })


@login_required
@require_http_methods(['GET'])
def page_version_view(request, project_id, page_id):
    try:
        project = _project_member_project(project_id, request.user)
    except PermissionDenied:
        return JsonResponse({'error': 'Você não tem acesso a este projeto.'}, status=404)

    page = _page_for_project(project, page_id, request.user)
    return JsonResponse({'version': page.version})


@login_required
@require_http_methods(['POST'])
def page_rename(request, project_id, page_id):
    try:
        project = _project_member_project(project_id, request.user)
    except PermissionDenied:
        return JsonResponse({'error': 'Você não tem acesso a este projeto.'}, status=404)

    page = _page_for_project(project, page_id, request.user)

    title, error = _normalize_title(request.POST.get('title'))
    if error:
        return JsonResponse({'error': error}, status=400)

    page.title = title
    page.save(update_fields=['title'])
    publish_tree_changed(project.pk, _client_origin(request))
    return JsonResponse({'success': True, 'page': _serialize_page(page)})


@login_required
@require_http_methods(['POST'])
def page_delete(request, project_id, page_id):
    try:
        project = _project_member_project(project_id, request.user)
    except PermissionDenied:
        return JsonResponse({'error': 'Você não tem acesso a este projeto.'}, status=404)

    page = _page_for_project(project, page_id, request.user)

    page.delete()
    origin = _client_origin(request)
    publish_tree_changed(project.pk, origin)
    publish_access_changed(project.pk)
    return JsonResponse({'success': True, 'deleted_page_id': page_id})


@login_required
@require_http_methods(['POST'])
def page_reorder(request, project_id, page_id):
    try:
        project = _project_member_project(project_id, request.user)
    except PermissionDenied:
        return JsonResponse({'error': 'Você não tem acesso a este projeto.'}, status=404)

    page = _page_for_project(project, page_id, request.user)

    try:
        order = int(request.POST.get('order', page.order))
    except ValueError:
        return JsonResponse({'error': 'Ordem inválida.'}, status=400)

    page.order = order
    page.save(update_fields=['order'])
    publish_tree_changed(project.pk, _client_origin(request))
    return JsonResponse({'success': True, 'page': _serialize_page(page)})
