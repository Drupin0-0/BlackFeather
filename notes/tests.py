import json
from unittest.mock import patch
from uuid import uuid4

from asgiref.sync import async_to_sync, sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from Sincrow.asgi import application
from Tasks.models import Project, ProjectMember
from notes.models import Page, Section, Subsection
from notes.permissions import visible_sections
from notes.validators import MAX_CONTENT_BYTES


def make_stroke(points=None, color='auto', width=4, element_id=None, z=7):
    return {
        'id': element_id or str(uuid4()),
        'type': 'stroke',
        'points': [12.34, 80.04] if points is None else points,
        'color': color,
        'width': width,
        'z': z,
    }


class NotesPermissionTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(email='dono@example.com', password='Senha123!')
        self.leader = User.objects.create_user(email='lider@example.com', password='Senha123!')
        self.member = User.objects.create_user(email='integrante@example.com', password='Senha123!')
        self.other = User.objects.create_user(email='fora@example.com', password='Senha123!')

        self.project = Project.objects.create(
            title='Projeto de notas',
            description='Projeto de teste',
            owner=self.owner,
        )
        self.project.members.add(self.owner, self.leader, self.member)
        ProjectMember.objects.create(project=self.project, user=self.leader, role=ProjectMember.Role.LEADER)

        self.shared = Section.objects.create(
            project=self.project,
            title='Seção compartilhada',
            visibility='shared',
            created_by=self.owner,
        )
        self.private = Section.objects.create(
            project=self.project,
            title='Seção privada',
            visibility='private',
            created_by=self.owner,
        )
        self.private.allowed_users.add(self.member)

    def test_visible_sections_respects_project_visibility(self):
        self.assertIn(self.shared, visible_sections(self.project, self.member))
        self.assertIn(self.private, visible_sections(self.project, self.member))
        self.assertIn(self.private, visible_sections(self.project, self.leader))
        self.assertIn(self.private, visible_sections(self.project, self.owner))
        self.assertNotIn(self.private, visible_sections(self.project, self.other))

    def test_project_notes_tree_returns_only_visible_sections(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse('project_notes_tree', args=[self.project.pk]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        section_titles = {section['title'] for section in payload['sections']}
        self.assertIn('Seção compartilhada', section_titles)
        self.assertIn('Seção privada', section_titles)

    def test_project_notes_page_renders_for_member_with_correct_navigation_links(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse('project_notes', args=[self.project.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/html; charset=utf-8')
        self.assertContains(
            response,
            f'href="{reverse("project_notes", args=[self.project.pk])}"',
        )
        self.assertContains(
            response,
            f'href="{reverse("project_detail", args=[self.project.pk])}"',
        )
        self.assertContains(
            response,
            f'href="{reverse("project_summary", args=[self.project.pk])}"',
        )
        self.assertContains(response, 'id="notesDraftNotice"')
        self.assertContains(response, 'src="/static/js/notes/drafts.js"')
        html = response.content.decode()
        self.assertLess(
            html.index('src="/static/js/notes/drafts.js"'),
            html.index('src="/static/js/notes/editor.js"'),
        )

    def test_project_notes_page_is_not_available_to_non_member(self):
        self.client.force_login(self.other)
        response = self.client.get(reverse('project_notes', args=[self.project.pk]))

        self.assertEqual(response.status_code, 404)


class NotesRealtimeTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(email='tempo-dono@example.com', password='Senha123!')
        self.member = User.objects.create_user(email='tempo-membro@example.com', password='Senha123!')
        self.outsider = User.objects.create_user(email='tempo-fora@example.com', password='Senha123!')
        self.project = Project.objects.create(
            title='Projeto em tempo real',
            description='Projeto de teste',
            owner=self.owner,
        )
        self.project.members.add(self.owner, self.member)
        self.section = Section.objects.create(
            project=self.project,
            title='Compartilhada',
            visibility='shared',
        )
        self.subsection = Subsection.objects.create(section=self.section, title='Subseção')
        self.page = Page.objects.create(subsection=self.subsection, title='Página')
        self.private_section = Section.objects.create(
            project=self.project,
            title='Privada',
            visibility='private',
        )
        self.private_subsection = Subsection.objects.create(
            section=self.private_section,
            title='Privada',
        )
        self.private_page = Page.objects.create(
            subsection=self.private_subsection,
            title='Página privada',
        )

    def websocket(self, user=None, origin='http://localhost'):
        headers = [(b'origin', origin.encode('ascii'))]
        if user is not None:
            client = Client()
            client.force_login(user)
            session = client.cookies['sessionid'].value
            headers.append((b'cookie', f'sessionid={session}'.encode('ascii')))
        return WebsocketCommunicator(
            application,
            f'/ws/projetos/{self.project.pk}/notes/',
            headers=headers,
        )

    def test_anonymous_outsider_and_invalid_origin_are_rejected(self):
        anonymous = self.websocket()
        outsider = self.websocket(self.outsider)
        invalid_origin = self.websocket(self.member, origin='http://evil.example')

        async def exercise():
            connected, _ = await anonymous.connect()
            self.assertFalse(connected)

            connected, _ = await outsider.connect()
            self.assertFalse(connected)

            connected, _ = await invalid_origin.connect()
            self.assertFalse(connected)

        async_to_sync(exercise)()

    def test_project_member_can_connect_and_watch_visible_page(self):
        communicator = self.websocket(self.member)

        async def exercise():
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.send_json_to({'action': 'watch_page', 'page_id': self.page.pk})
            await communicator.send_json_to({'action': 'ping'})
            self.assertEqual(await communicator.receive_json_from(), {'type': 'pong'})
            await communicator.disconnect()

        async_to_sync(exercise)()

    def test_private_page_watch_is_denied_without_membership(self):
        communicator = self.websocket(self.member)

        async def exercise():
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.send_json_to({'action': 'watch_page', 'page_id': self.private_page.pk})
            self.assertEqual(await communicator.receive_json_from(), {'type': 'denied'})
            await communicator.disconnect()

        async_to_sync(exercise)()

    def test_page_update_is_sent_only_to_observers_without_content_or_names(self):
        client_id = 'tab-123'
        client = Client()
        client.force_login(self.member)
        observer = self.websocket(self.member)
        unobserved = self.websocket(self.member)

        async def exercise():
            self.assertTrue((await observer.connect())[0])
            self.assertTrue((await unobserved.connect())[0])
            await observer.send_json_to({'action': 'watch_page', 'page_id': self.page.pk})
            await observer.send_json_to({'action': 'ping'})
            self.assertEqual(await observer.receive_json_from(), {'type': 'pong'})
            response = await sync_to_async(client.put, thread_sensitive=True)(
                reverse('notes_page_content', args=[self.project.pk, self.page.pk]),
                data=json.dumps({'content': {'schema': 1, 'elements': []}, 'version': 1}),
                content_type='application/json',
                HTTP_X_NOTES_CLIENT=client_id,
            )
            self.assertEqual(response.status_code, 200)
            event = await observer.receive_json_from()
            self.assertEqual(event, {
                'type': 'page_updated',
                'page_id': self.page.pk,
                'version': 2,
                'origin': client_id,
            })
            self.assertFalse({'content', 'title', 'name', 'email'} & set(event))
            self.assertTrue(await unobserved.receive_nothing(timeout=0.05))
            await observer.disconnect()
            await unobserved.disconnect()

        async_to_sync(exercise)()

    def test_page_rename_broadcasts_tree_change_with_valid_origin(self):
        client_id = 'aba-42'
        client = Client()
        client.force_login(self.member)
        observer = self.websocket(self.member)

        async def exercise():
            self.assertTrue((await observer.connect())[0])
            await observer.send_json_to({'action': 'ping'})
            self.assertEqual(await observer.receive_json_from(), {'type': 'pong'})
            response = await sync_to_async(client.post, thread_sensitive=True)(
                reverse('notes_page_rename', args=[self.project.pk, self.page.pk]),
                {'title': 'Novo título'},
                HTTP_X_NOTES_CLIENT=client_id,
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(await observer.receive_json_from(), {
                'type': 'tree_changed',
                'origin': client_id,
            })
            await observer.disconnect()

        async_to_sync(exercise)()

    def test_invalid_client_id_is_not_forwarded(self):
        client = Client()
        client.force_login(self.member)
        observer = self.websocket(self.member)

        async def exercise():
            self.assertTrue((await observer.connect())[0])
            await observer.send_json_to({'action': 'watch_page', 'page_id': self.page.pk})
            await observer.send_json_to({'action': 'ping'})
            self.assertEqual(await observer.receive_json_from(), {'type': 'pong'})
            response = await sync_to_async(client.put, thread_sensitive=True)(
                reverse('notes_page_content', args=[self.project.pk, self.page.pk]),
                data=json.dumps({'content': {'schema': 1, 'elements': []}, 'version': 1}),
                content_type='application/json',
                HTTP_X_NOTES_CLIENT='tab identity!',
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(await observer.receive_json_from(), {
                'type': 'page_updated',
                'page_id': self.page.pk,
                'version': 2,
            })
            await observer.disconnect()

        async_to_sync(exercise)()

    def test_privacy_change_sends_access_lost(self):
        client = Client()
        client.force_login(self.owner)
        communicator = self.websocket(self.member)

        async def exercise():
            self.assertTrue((await communicator.connect())[0])
            await communicator.send_json_to({'action': 'watch_page', 'page_id': self.page.pk})
            await communicator.send_json_to({'action': 'ping'})
            self.assertEqual(await communicator.receive_json_from(), {'type': 'pong'})
            response = await sync_to_async(client.post, thread_sensitive=True)(
                reverse('notes_section_visibility', args=[self.project.pk, self.section.pk]),
                {'visibility': 'private'},
            )
            self.assertEqual(response.status_code, 200)
            event = await communicator.receive_json_from()
            self.assertEqual(event, {'type': 'access_lost', 'page_id': self.page.pk})
            await communicator.disconnect()

        async_to_sync(exercise)()

    def test_deleting_observed_page_sends_access_lost(self):
        client = Client()
        client.force_login(self.owner)
        communicator = self.websocket(self.member)

        async def exercise():
            self.assertTrue((await communicator.connect())[0])
            await communicator.send_json_to({'action': 'watch_page', 'page_id': self.page.pk})
            await communicator.send_json_to({'action': 'ping'})
            self.assertEqual(await communicator.receive_json_from(), {'type': 'pong'})
            response = await sync_to_async(client.post, thread_sensitive=True)(
                reverse('notes_page_delete', args=[self.project.pk, self.page.pk]),
            )
            self.assertEqual(response.status_code, 200)
            events = []
            for _ in range(3):
                try:
                    events.append(await communicator.receive_json_from(timeout=0.2))
                except TimeoutError:
                    break
                if events[-1].get('type') == 'access_lost':
                    break
            self.assertIn({'type': 'access_lost', 'page_id': self.page.pk}, events)
            await communicator.disconnect()

        async_to_sync(exercise)()

    def test_realtime_send_failure_does_not_fail_page_save(self):
        class FailingLayer:
            async def group_send(self, group, event):
                raise RuntimeError('canal indisponível')

        client = Client()
        client.force_login(self.member)
        with patch('notes.events.get_channel_layer', return_value=FailingLayer()):
            response = client.put(
                reverse('notes_page_content', args=[self.project.pk, self.page.pk]),
                data=json.dumps({'content': {'schema': 1, 'elements': []}, 'version': 1}),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 200)
        self.page.refresh_from_db()
        self.assertEqual(self.page.version, 2)

    def test_page_version_endpoint_obeys_visibility(self):
        client = Client()
        client.force_login(self.member)
        visible_response = client.get(reverse('notes_page_version', args=[self.project.pk, self.page.pk]))
        private_response = client.get(reverse('notes_page_version', args=[self.project.pk, self.private_page.pk]))
        self.assertEqual(visible_response.status_code, 200)
        self.assertEqual(visible_response.json(), {'version': 1})
        self.assertEqual(private_response.status_code, 404)

    def test_invalid_and_oversized_messages_do_not_close_connection(self):
        communicator = self.websocket(self.member)

        async def exercise():
            self.assertTrue((await communicator.connect())[0])
            await communicator.send_to(text_data='not-json')
            await communicator.send_to(text_data='x' * 1025)
            await communicator.send_json_to({'action': 'watch_page', 'page_id': 'invalid'})
            await communicator.send_json_to({'action': 'ping'})
            self.assertEqual(await communicator.receive_json_from(), {'type': 'pong'})
            await communicator.disconnect()

        async_to_sync(exercise)()


class NotesContentTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(email='dono@example.com', password='Senha123!')
        self.leader = User.objects.create_user(email='lider@example.com', password='Senha123!')
        self.member = User.objects.create_user(email='integrante@example.com', password='Senha123!')
        self.other = User.objects.create_user(email='fora@example.com', password='Senha123!')

        self.project = Project.objects.create(
            title='Projeto de notas',
            description='Projeto de teste',
            owner=self.owner,
        )
        self.project.members.add(self.owner, self.leader, self.member)
        ProjectMember.objects.create(project=self.project, user=self.leader, role=ProjectMember.Role.LEADER)
        self.shared = Section.objects.create(
            project=self.project,
            title='Seção compartilhada',
            visibility='shared',
            created_by=self.owner,
        )
        self.private = Section.objects.create(
            project=self.project,
            title='Seção privada',
            visibility='private',
            created_by=self.owner,
        )
        self.private.allowed_users.add(self.member)

    def test_notes_json_routes_are_nested_under_api(self):
        page_url = reverse('project_notes', args=[self.project.pk])
        tree_url = reverse('project_notes_tree', args=[self.project.pk])
        self.assertEqual(tree_url, page_url + 'api/tree/')

    def test_page_content_update_requires_matching_version(self):
        subsection = Subsection.objects.create(section=self.shared, title='Subseção')
        existing_content = {
            'schema': 1,
            'elements': [{
                'id': str(uuid4()),
                'type': 'text',
                'x': 0,
                'y': 0,
                'w': 320,
                'z': 1,
                'html': '<p>Antes</p>',
            }],
        }
        page = Page.objects.create(subsection=subsection, title='Página', content=existing_content, version=1)

        self.client.force_login(self.member)
        response = self.client.put(
            reverse('notes_page_content', args=[self.project.pk, page.pk]),
            data=json.dumps({'content': {'texto': 'depois'}, 'version': 99}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['current_version'], 1)
        page.refresh_from_db()
        self.assertEqual(page.version, 1)

    def test_empty_page_content_is_normalized_for_editor(self):
        subsection = Subsection.objects.create(section=self.shared, title='Subseção')
        page = Page.objects.create(subsection=subsection, title='Página')
        self.client.force_login(self.member)

        response = self.client.get(reverse('notes_page_content', args=[self.project.pk, page.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['content'], {'schema': 1, 'elements': []})

    def test_page_content_is_sanitized_before_saving_and_returned_to_client(self):
        subsection = Subsection.objects.create(section=self.shared, title='Subseção')
        page = Page.objects.create(subsection=subsection, title='Página')
        content = {
            'schema': 1,
            'elements': [{
                'id': str(uuid4()),
                'type': 'text',
                'x': 120,
                'y': 80,
                'w': 320,
                'z': 1,
                'html': (
                    '<p style="color:#ff6b6b;font-size:16px;text-align:center;'
                    'font-family:Arial;background-image:url(javascript:evil)" onclick="evil()">'
                    '<strong>Texto</strong><script>evil()</script></p>'
                ),
            }],
        }
        self.client.force_login(self.member)

        response = self.client.put(
            reverse('notes_page_content', args=[self.project.pk, page.pk]),
            data=json.dumps({'content': content, 'version': 1}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        sanitized = response.json()['content']
        self.assertEqual(sanitized['elements'][0]['html'], (
            '<p style="color:#ff6b6b;font-size:16px;text-align:center;font-family:Arial">'
            '<strong>Texto</strong></p>'
        ))
        page.refresh_from_db()
        self.assertEqual(page.content, sanitized)
        self.assertEqual(page.version, 2)
        self.assertEqual(page.updated_by, self.member)

    def test_unknown_block_type_is_rejected_without_saving(self):
        subsection = Subsection.objects.create(section=self.shared, title='Subseção')
        page = Page.objects.create(subsection=subsection, title='Página')
        content = {
            'schema': 1,
            'elements': [{
                'id': str(uuid4()),
                'type': 'shape',
                'x': 0,
                'y': 0,
                'w': 100,
                'z': 0,
                'html': '',
            }],
        }
        self.client.force_login(self.member)

        response = self.client.put(
            reverse('notes_page_content', args=[self.project.pk, page.pk]),
            data=json.dumps({'content': content, 'version': 1}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('Tipo de bloco desconhecido', response.json()['error'])
        page.refresh_from_db()
        self.assertEqual(page.content, {})
        self.assertEqual(page.version, 1)

    def test_page_content_rejects_out_of_range_coordinates(self):
        subsection = Subsection.objects.create(section=self.shared, title='Subseção')
        page = Page.objects.create(subsection=subsection, title='Página')
        content = {
            'schema': 1,
            'elements': [{
                'id': str(uuid4()),
                'type': 'text',
                'x': 20_001,
                'y': 0,
                'w': 320,
                'z': 1,
                'html': '<p>Texto</p>',
            }],
        }
        self.client.force_login(self.member)

        response = self.client.put(
            reverse('notes_page_content', args=[self.project.pk, page.pk]),
            data=json.dumps({'content': content, 'version': 1}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('campo x', response.json()['error'])
        page.refresh_from_db()
        self.assertEqual(page.version, 1)

    def test_page_content_rejects_duplicate_element_ids(self):
        subsection = Subsection.objects.create(section=self.shared, title='Subseção')
        page = Page.objects.create(subsection=subsection, title='Página')
        element_id = str(uuid4())
        element = {
            'id': element_id,
            'type': 'text',
            'x': 0,
            'y': 0,
            'w': 320,
            'z': 1,
            'html': '<p>Texto</p>',
        }
        content = {'schema': 1, 'elements': [element, dict(element)]}
        self.client.force_login(self.member)

        response = self.client.put(
            reverse('notes_page_content', args=[self.project.pk, page.pk]),
            data=json.dumps({'content': content, 'version': 1}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('não podem se repetir', response.json()['error'])
        page.refresh_from_db()
        self.assertEqual(page.version, 1)

    def test_stroke_content_is_saved_normalized_and_reloaded(self):
        subsection = Subsection.objects.create(section=self.shared, title='Subseção')
        page = Page.objects.create(subsection=subsection, title='Página')
        text = {
            'id': str(uuid4()),
            'type': 'text',
            'x': 120,
            'y': 80,
            'w': 320,
            'z': 1,
            'html': '<p>Texto</p>',
        }
        stroke = make_stroke(points=[12.34, 80.04, 100.06, 200.08], color='#AAbbCC')
        dot = make_stroke(points=[500.05, 600.05], width=1)
        content = {'schema': 1, 'elements': [text, stroke, dot]}
        self.client.force_login(self.member)

        response = self.client.put(
            reverse('notes_page_content', args=[self.project.pk, page.pk]),
            data=json.dumps({'content': content, 'version': 1}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        normalized = response.json()['content']
        self.assertEqual(normalized['elements'][1]['points'], [12.3, 80.0, 100.1, 200.1])
        self.assertEqual(normalized['elements'][1]['color'], '#AAbbCC')
        self.assertEqual(normalized['elements'][1]['width'], 4)
        self.assertEqual(normalized['elements'][2]['points'], [500.1, 600.1])
        self.assertEqual(normalized['elements'][2]['width'], 1)
        self.assertEqual(normalized['elements'][0]['html'], '<p>Texto</p>')
        page.refresh_from_db()
        self.assertEqual(page.content, normalized)

        reloaded = self.client.get(reverse('notes_page_content', args=[self.project.pk, page.pk]))
        self.assertEqual(reloaded.status_code, 200)
        self.assertEqual(reloaded.json()['content'], normalized)

    def test_invalid_stroke_fields_return_400(self):
        subsection = Subsection.objects.create(section=self.shared, title='Subseção')
        page = Page.objects.create(subsection=subsection, title='Página')
        self.client.force_login(self.member)
        invalid_strokes = [
            make_stroke(points=[]),
            make_stroke(points=[1, 2, 3]),
            make_stroke(points=[0, 0] * 5001),
            make_stroke(points=[float('nan'), 0]),
            make_stroke(points=[float('inf'), 0]),
            make_stroke(points=['1', 0]),
            make_stroke(points=[-0.1, 0]),
            make_stroke(points=[20_000.1, 0]),
            make_stroke(color='red'),
            make_stroke(color='#fff'),
            make_stroke(color='javascript:alert(1)'),
            make_stroke(width=0),
            make_stroke(width=41),
            make_stroke(z=-1),
            make_stroke(z=100_001),
            make_stroke(z=True),
        ]

        for stroke in invalid_strokes:
            with self.subTest(stroke=stroke):
                response = self.client.put(
                    reverse('notes_page_content', args=[self.project.pk, page.pk]),
                    data=json.dumps({
                        'content': {'schema': 1, 'elements': [stroke]},
                        'version': 1,
                    }),
                    content_type='application/json',
                )
                self.assertEqual(response.status_code, 400)

        page.refresh_from_db()
        self.assertEqual(page.version, 1)
        self.assertEqual(page.content, {})

    def test_stroke_ids_and_per_page_limits_return_400(self):
        subsection = Subsection.objects.create(section=self.shared, title='Subseção')
        page = Page.objects.create(subsection=subsection, title='Página')
        self.client.force_login(self.member)
        repeated_id = str(uuid4())
        duplicate_strokes = [
            make_stroke(element_id=repeated_id),
            make_stroke(element_id=repeated_id),
        ]
        too_many_strokes = [make_stroke() for _ in range(5001)]
        too_many_points = [
            make_stroke(points=[0, 0] * 5000)
            for _ in range(25)
        ]
        too_many_text = [{
            'id': str(uuid4()),
            'type': 'text',
            'x': 0,
            'y': 0,
            'w': 320,
            'z': 1,
            'html': '',
        } for _ in range(1001)]

        for elements in (duplicate_strokes, too_many_strokes, too_many_points, too_many_text):
            with self.subTest(element_count=len(elements)):
                response = self.client.put(
                    reverse('notes_page_content', args=[self.project.pk, page.pk]),
                    data=json.dumps({
                        'content': {'schema': 1, 'elements': elements},
                        'version': 1,
                    }),
                    content_type='application/json',
                )
                self.assertEqual(response.status_code, 400)

        oversized = json.dumps({
            'content': 'x' * (MAX_CONTENT_BYTES + 1),
            'version': 1,
        })
        response = self.client.put(
            reverse('notes_page_content', args=[self.project.pk, page.pk]),
            data=oversized,
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('2 MB', response.json()['error'])

        page.refresh_from_db()
        self.assertEqual(page.version, 1)

    def test_private_page_content_is_not_visible_to_outside_user(self):
        subsection = Subsection.objects.create(section=self.private, title='Subseção')
        page = Page.objects.create(subsection=subsection, title='Página')
        self.client.force_login(self.other)

        response = self.client.get(reverse('notes_page_content', args=[self.project.pk, page.pk]))

        self.assertEqual(response.status_code, 404)
