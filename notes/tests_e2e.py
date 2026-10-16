import asyncio
import os
import sys
import uuid

from channels.testing import ChannelsLiveServerTestCase
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client
from playwright.sync_api import sync_playwright

from Tasks.models import Project, ProjectMember
from notes.models import Page, Section, Subsection


class NotesBrowserFlowTests(ChannelsLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.previous_async_unsafe = os.environ.get('DJANGO_ALLOW_ASYNC_UNSAFE')
        os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = 'true'
        event_loop_policy = asyncio.get_event_loop_policy()
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        try:
            cls.playwright = sync_playwright().start()
        finally:
            asyncio.set_event_loop_policy(event_loop_policy)
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.browser.close()
            cls.playwright.stop()
        finally:
            if cls.previous_async_unsafe is None:
                os.environ.pop('DJANGO_ALLOW_ASYNC_UNSAFE', None)
            else:
                os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = cls.previous_async_unsafe
        super().tearDownClass()

    def setUp(self):
        User = get_user_model()
        suffix = uuid.uuid4().hex[:12]
        self.owner = User.objects.create_user(
            email=f'notes-owner-{suffix}@example.test',
            password='Temporary-e2e-Password-847!',
        )
        self.member = User.objects.create_user(
            email=f'notes-member-{suffix}@example.test',
            password='Temporary-e2e-Password-847!',
        )
        self.outsider = User.objects.create_user(
            email=f'notes-outsider-{suffix}@example.test',
            password='Temporary-e2e-Password-847!',
        )
        self.project = Project.objects.create(
            title=f'Notes E2E {suffix}',
            description='Projeto temporário de teste de navegador.',
            owner=self.owner,
        )
        self.project.members.add(self.owner, self.member)
        ProjectMember.objects.create(
            project=self.project,
            user=self.member,
            role=ProjectMember.Role.MEMBER,
        )
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
        self.contexts = []

    def tearDown(self):
        for context in self.contexts:
            context.close()

    def _new_page(self, user, open_notes_from_project=False, viewport=None):
        client = Client()
        client.force_login(user)
        context_options = {'viewport': viewport} if viewport else {}
        context = self.browser.new_context(**context_options)
        context.add_cookies([{
            'name': settings.SESSION_COOKIE_NAME,
            'value': client.cookies[settings.SESSION_COOKIE_NAME].value,
            'url': self.live_server_url,
        }])
        self.contexts.append(context)
        page = context.new_page()
        signals = {'console': [], 'exceptions': [], 'responses': [], 'failed': []}
        page.on(
            'console',
            lambda message: signals['console'].append(message.text)
            if message.type == 'error' else None,
        )
        page.on('pageerror', lambda error: signals['exceptions'].append(str(error)))
        page.on(
            'response',
            lambda response: signals['responses'].append(
                (response.status, response.url)
            ) if response.status >= 400 else None,
        )
        page.on(
            'requestfailed',
            lambda request: signals['failed'].append(
                (request.method, request.url, request.failure)
            ),
        )
        project_url = f'{self.live_server_url}/projetos/{self.project.pk}/'
        if open_notes_from_project:
            page.goto(project_url)
            page.get_by_role('link', name='NOTES', exact=True).click()
        else:
            page.goto(project_url + 'notes/')
        return page, signals

    def _assert_browser_clean(self, signals, allowed_statuses=(), allowed_console=()):
        allowed = set(allowed_statuses)
        unexpected = [
            (status, url)
            for status, url in signals['responses']
            if status not in allowed
        ]
        unexpected_console = [
            message
            for message in signals['console']
            if not any(fragment in message for fragment in allowed_console)
        ]
        self.assertEqual(unexpected, [])
        self.assertEqual(unexpected_console, [])
        self.assertEqual(signals['exceptions'], [])
        self.assertEqual(signals['failed'], [])

    def _select_page(self, page, page_id):
        page.locator(f'[data-page-id="{page_id}"]').click()
        page.locator('#notesEditor').wait_for(state='visible')
        page.locator('#notesWorld').wait_for(state='attached')

    def _area_point(self, page, x, y):
        bounds = page.locator('#notesWorkArea').bounding_box()
        return {'x': bounds['x'] + x, 'y': bounds['y'] + y}

    def _drag_area(self, page, start, end, steps=12):
        first = self._area_point(page, *start)
        last = self._area_point(page, *end)
        page.mouse.move(first['x'], first['y'])
        page.mouse.down()
        page.mouse.move(last['x'], last['y'], steps=steps)
        page.mouse.up()

    def _wait_for_version_change(self, page, old_version):
        page.wait_for_function(
            'oldVersion => window.notesEditor.getVersion() > oldVersion',
            arg=old_version,
            timeout=10000,
        )

    def _create(self, page, button, placeholder, title):
        button.click()
        page.get_by_role('textbox', name=placeholder).fill(title)
        page.get_by_role('button', name='Salvar', exact=True).click()
        page.get_by_role('button', name=title, exact=True).wait_for()

    def _item(self, page, node_type, title):
        return page.locator(
            f'.notes-tree-entry[data-node-type="{node_type}"]'
        ).filter(has_text=title).first

    def _row(self, page, node_type, title):
        return self._item(page, node_type, title).locator(':scope > .notes-tree-row')

    def _rename(self, page, node_type, title, new_title):
        self._row(page, node_type, title).get_by_role(
            'button', name='Abrir ações'
        ).click()
        page.locator('.notes-popover').get_by_role(
            'button', name='Renomear', exact=True
        ).click()
        page.get_by_role('textbox', name='Nome').fill(new_title)
        page.get_by_role('button', name='Salvar', exact=True).click()
        page.get_by_role('button', name=new_title, exact=True).wait_for()

    def _move_down(self, page, node_type, title):
        selector = f'.notes-tree-entry[data-node-type="{node_type}"]'
        title_selector = ':scope > .notes-tree-row > .notes-node-title'
        order = page.locator(selector).evaluate_all(
            '(entries, selector) => entries.map(entry => '
            'entry.querySelector(selector).textContent)',
            title_selector,
        )
        index = order.index(title)
        self.assertLess(index, len(order) - 1)
        expected = list(order)
        expected[index], expected[index + 1] = expected[index + 1], expected[index]
        self._row(page, node_type, title).get_by_role(
            'button', name='Abrir ações'
        ).click()
        page.get_by_role('button', name='Mover para baixo').click()
        page.wait_for_function(
            '({selector, titleSelector, expected}) => JSON.stringify('
            'Array.from(document.querySelectorAll(selector)).map(entry => '
            'entry.querySelector(titleSelector).textContent)) === JSON.stringify(expected)',
            arg={
                'selector': selector,
                'titleSelector': title_selector,
                'expected': expected,
            },
        )

    def _delete(self, page, node_type, title):
        item = self._item(page, node_type, title)
        self._row(page, node_type, title).get_by_role(
            'button', name='Abrir ações'
        ).click()
        page.get_by_role('button', name='Excluir', exact=True).click()
        dialog = page.get_by_role('dialog', name='Confirmar exclusão')
        dialog.get_by_role('button', name='Excluir', exact=True).click()
        item.wait_for(state='detached')

    def _shared_page(self):
        subsection = Subsection.objects.create(
            section=self.shared,
            title='Subseção de teste',
        )
        return Page.objects.create(subsection=subsection, title='Página de teste')

    def test_owner_creates_renames_moves_and_deletes_all_tree_levels(self):
        self.shared.delete()
        self.private.delete()
        page, signals = self._new_page(self.owner, open_notes_from_project=True)
        page.get_by_text('Nenhuma seção ainda.').wait_for()
        self._create(
            page,
            page.locator('.notes-sidebar-heading [data-action="create-section"]'),
            'Nome da seção',
            'Seção A',
        )
        self._create(
            page,
            page.locator('.notes-sidebar-heading [data-action="create-section"]'),
            'Nome da seção',
            'Seção B',
        )
        self._rename(page, 'section', 'Seção A', 'Seção A renomeada')
        self._move_down(page, 'section', 'Seção A renomeada')

        section_a = self._item(page, 'section', 'Seção A renomeada')
        self._create(
            page,
            section_a.get_by_role('button', name='Criar subseção'),
            'Nome da subseção',
            'Subseção A1',
        )
        self._create(
            page,
            section_a.get_by_role('button', name='Criar subseção'),
            'Nome da subseção',
            'Subseção A2',
        )
        self._rename(page, 'subsection', 'Subseção A1', 'Subseção A1 renomeada')
        self._move_down(page, 'subsection', 'Subseção A1 renomeada')

        subsection = self._item(page, 'subsection', 'Subseção A1 renomeada')
        self._create(
            page,
            subsection.get_by_role('button', name='Criar página'),
            'Nome da página',
            'Página A1',
        )
        self._create(
            page,
            subsection.get_by_role('button', name='Criar página'),
            'Nome da página',
            'Página A2',
        )
        self._rename(page, 'page', 'Página A1', 'Página A1 renomeada')
        self._move_down(page, 'page', 'Página A1 renomeada')
        self._delete(page, 'page', 'Página A2')
        self._delete(page, 'subsection', 'Subseção A2')
        self._delete(page, 'section', 'Seção B')
        self._delete(page, 'section', 'Seção A renomeada')
        page.get_by_text('Nenhuma seção ainda.').wait_for()
        self._assert_browser_clean(signals)

    def test_text_block_autosaves_and_survives_reload(self):
        note_page = self._shared_page()
        page, signals = self._new_page(self.owner)
        self._select_page(page, note_page.pk)
        page.locator('[data-tool="text"]').click()
        page.locator('#notesWorkArea').click(position={'x': 250, 'y': 100})
        editor = page.locator('.notes-text-content')
        editor.fill('Texto salvo pelo navegador real')
        page.get_by_text('Salvo', exact=True).wait_for(timeout=10000)
        page.reload()
        page.locator(f'[data-page-id="{note_page.pk}"]').wait_for()
        page.get_by_text('Texto salvo pelo navegador real', exact=True).wait_for(
            timeout=10000
        )
        self._assert_browser_clean(signals)

    def test_member_can_create_in_shared_section_but_not_see_private_section(self):
        page, signals = self._new_page(self.member)
        self.assertEqual(
            page.locator('.notes-sidebar-heading [data-action="create-section"]').count(),
            0,
        )
        page.get_by_role('button', name='Seção compartilhada', exact=True).wait_for()
        self.assertEqual(page.get_by_role('button', name='Seção privada', exact=True).count(), 0)
        section = self._item(page, 'section', 'Seção compartilhada')
        self._create(
            page,
            section.get_by_role('button', name='Criar subseção'),
            'Nome da subseção',
            'Subseção do integrante',
        )
        subsection = self._item(page, 'subsection', 'Subseção do integrante')
        self._create(
            page,
            subsection.get_by_role('button', name='Criar página'),
            'Nome da página',
            'Página do integrante',
        )
        self._assert_browser_clean(signals)

    def test_outsider_gets_404_for_notes_page_and_read_endpoints(self):
        note_page = self._shared_page()
        page, signals = self._new_page(self.outsider)
        self.assertEqual(page.url, f'{self.live_server_url}/projetos/{self.project.pk}/notes/')
        tree_response = page.request.get(
            f'{self.live_server_url}/projetos/{self.project.pk}/notes/api/tree/'
        )
        content_response = page.request.get(
            f'{self.live_server_url}/projetos/{self.project.pk}/notes/api/pages/{note_page.pk}/'
        )
        self.assertEqual(tree_response.status, 404)
        self.assertEqual(content_response.status, 404)
        self.assertIn((404, page.url), signals['responses'])
        self._assert_browser_clean(
            signals,
            allowed_statuses=(404,),
            allowed_console=('status of 404 (Not Found)',),
        )

    def test_two_browser_sessions_receive_page_and_tree_updates(self):
        note_page = self._shared_page()
        first, first_signals = self._new_page(self.owner)
        second, second_signals = self._new_page(self.owner)
        self._select_page(first, note_page.pk)
        self._select_page(second, note_page.pk)
        first.locator('[data-tool="text"]').click()
        first.locator('#notesWorkArea').click(position={'x': 260, 'y': 100})
        first.locator('.notes-text-content').fill('Atualização recebida em tempo real')
        first.get_by_text('Salvo', exact=True).wait_for(timeout=10000)
        second.get_by_text('Atualização recebida em tempo real', exact=True).wait_for(
            timeout=10000
        )

        self._create(
            first,
            first.locator('.notes-sidebar-heading [data-action="create-section"]'),
            'Nome da seção',
            'Seção criada na primeira sessão',
        )
        created_section = self._item(first, 'section', 'Seção criada na primeira sessão')
        self._create(
            first,
            created_section.get_by_role('button', name='Criar subseção'),
            'Nome da subseção',
            'Subseção da primeira sessão',
        )
        created_subsection = self._item(
            first, 'subsection', 'Subseção da primeira sessão'
        )
        self._create(
            first,
            created_subsection.get_by_role('button', name='Criar página'),
            'Nome da página',
            'Página criada na primeira sessão',
        )
        second.get_by_role(
            'button', name='Página criada na primeira sessão', exact=True
        ).wait_for(timeout=10000)
        self._assert_browser_clean(first_signals)
        self._assert_browser_clean(second_signals)

    def test_offline_save_failure_retries_automatically_when_online(self):
        note_page = self._shared_page()
        page, signals = self._new_page(self.owner)
        self._select_page(page, note_page.pk)
        page.context.set_offline(True)
        page.locator('[data-tool="text"]').click()
        page.locator('#notesWorkArea').click(position={'x': 250, 'y': 100})
        page.locator('.notes-text-content').fill('Salvo após restaurar a rede')
        page.get_by_text('Falha ao salvar', exact=True).wait_for(timeout=10000)
        page.context.set_offline(False)
        page.get_by_text('Salvo', exact=True).wait_for(timeout=10000)
        note_page.refresh_from_db()
        self.assertIn(
            'Salvo após restaurar a rede',
            note_page.content['elements'][0]['html'],
        )
        self.assertEqual(signals['exceptions'], [])
        self.assertEqual(
            [(status, url) for status, url in signals['responses']],
            [],
        )

    def test_pencil_color_width_single_point_and_reload(self):
        note_page = self._shared_page()
        page, signals = self._new_page(self.owner)
        self._select_page(page, note_page.pk)
        page.locator('[data-ink-color="#f472b6"]').click()
        page.locator('[data-size-toggle]').click()
        page.locator('[data-ink-width="8"]').click()
        page.locator('[data-tool="pencil"]').click()
        old_version = page.evaluate('window.notesEditor.getVersion()')
        self._drag_area(page, (130, 50), (330, 50))
        point = self._area_point(page, 470, 110)
        page.mouse.click(point['x'], point['y'])
        paths = page.locator('.notes-ink path')
        page.wait_for_function(
            'document.querySelectorAll(".notes-ink path").length === 2'
        )
        self.assertEqual(paths.nth(0).get_attribute('stroke'), '#f472b6')
        self.assertEqual(paths.nth(0).get_attribute('stroke-width'), '8')
        self.assertTrue(paths.nth(1).get_attribute('d').startswith('M '))
        self._wait_for_version_change(page, old_version)
        page.reload()
        page.locator('#notesEditor').wait_for(state='visible')
        page.wait_for_function(
            'document.querySelectorAll(".notes-ink path").length === 2'
        )
        preferences = page.evaluate(
            'userId => JSON.parse(localStorage.getItem("sincrow:notes:ink:" + userId))',
            self.owner.pk,
        )
        self.assertEqual(preferences['color'], '#f472b6')
        self.assertEqual(preferences['width'], 8)
        note_page.refresh_from_db()
        strokes = [item for item in note_page.content['elements'] if item['type'] == 'stroke']
        self.assertEqual(len(strokes), 2)
        self.assertTrue(any(len(stroke['points']) == 2 for stroke in strokes))
        self._assert_browser_clean(signals)

    def test_partial_eraser_cancel_undo_and_redo(self):
        note_page = self._shared_page()
        page, signals = self._new_page(self.owner)
        self._select_page(page, note_page.pk)
        page.locator('[data-tool="pencil"]').click()
        self._drag_area(page, (150, 80), (450, 80))
        page.locator('.notes-ink path').wait_for(state='attached')
        original_id = page.locator('.notes-ink path').get_attribute('data-stroke-id')
        page.locator('[data-tool="eraser"]').click()
        self._drag_area(page, (300, 20), (300, 140))
        page.wait_for_function(
            'document.querySelectorAll(".notes-ink path").length === 2'
        )
        split_ids = page.locator('.notes-ink path').evaluate_all(
            'paths => paths.map(path => path.dataset.strokeId)'
        )
        self.assertNotIn(original_id, split_ids)
        page.locator('[data-history="undo"]').click()
        page.wait_for_function(
            'document.querySelectorAll(".notes-ink path").length === 1'
        )
        self.assertEqual(
            page.locator('.notes-ink path').get_attribute('data-stroke-id'),
            original_id,
        )
        page.locator('[data-history="redo"]').click()
        page.wait_for_function(
            'document.querySelectorAll(".notes-ink path").length === 2'
        )
        self.assertEqual(
            page.locator('.notes-ink path').evaluate_all(
                'paths => paths.map(path => path.dataset.strokeId)'
            ),
            split_ids,
        )

        page.keyboard.press('v')
        page.locator('[data-tool="eraser"]').click()
        first = self._area_point(page, 300, 60)
        last = self._area_point(page, 300, 100)
        page.mouse.move(first['x'], first['y'])
        page.mouse.down()
        page.mouse.move(last['x'], last['y'], steps=4)
        page.keyboard.press('Escape')
        page.mouse.up()
        page.wait_for_timeout(100)
        self.assertEqual(page.locator('.notes-ink path').count(), 2)
        self._assert_browser_clean(signals)

    def test_multiselect_move_copy_delete_and_history(self):
        note_page = self._shared_page()
        page, signals = self._new_page(self.owner)
        self._select_page(page, note_page.pk)
        page.locator('[data-tool="text"]').click()
        page.locator('#notesWorkArea').click(position={'x': 190, 'y': 30})
        page.locator('.notes-text-content').last.fill('Bloco um')
        page.locator('[data-tool="text"]').click()
        page.locator('#notesWorkArea').click(position={'x': 520, 'y': 80})
        page.locator('.notes-text-content').last.fill('Bloco dois')
        page.locator('button[data-tool="select"]').click()
        self._drag_area(page, (90, 5), (950, 150))
        page.wait_for_function('window.notesEditor.getSelection().length === 2')
        before = page.evaluate('window.notesEditor.getElements().map(item => [item.x, item.y])')
        bounds = page.evaluate('''() => {
            const rect = document.getElementById('notesWorld').getBoundingClientRect();
            const box = window.notesEditor.getSelectionBounds();
            return {
                x: rect.left + (box.minX + box.maxX) / 2,
                y: rect.top + (box.minY + box.maxY) / 2
            };
        }''')
        page.mouse.move(bounds['x'], bounds['y'])
        page.mouse.down()
        page.mouse.move(bounds['x'] + 40, bounds['y'] + 25, steps=5)
        page.mouse.up()
        moved = page.evaluate('window.notesEditor.getElements().map(item => [item.x, item.y])')
        self.assertNotEqual(moved, before)
        page.locator('[data-history="undo"]').click()
        page.wait_for_timeout(100)
        undone = page.evaluate('window.notesEditor.getElements().map(item => [item.x, item.y])')
        self.assertEqual(undone, before, {'moved': moved, 'selection': page.evaluate('window.notesEditor.getSelection()')})
        page.locator('[data-history="redo"]').click()
        page.wait_for_function(
            'expected => JSON.stringify(window.notesEditor.getElements().map(item => [item.x, item.y])) === '
            'JSON.stringify(expected)',
            arg=moved,
        )
        page.evaluate('document.activeElement.blur()')
        page.keyboard.press('Control+d')
        page.wait_for_function('window.notesEditor.getElements().length === 4')
        page.keyboard.press('Delete')
        page.wait_for_function('window.notesEditor.getElements().length === 2')
        page.keyboard.press('Control+z')
        page.wait_for_function('window.notesEditor.getElements().length === 4')
        self._assert_browser_clean(signals)

    def test_toolbar_size_preview_and_single_scroll_container(self):
        note_page = self._shared_page()
        page, signals = self._new_page(self.owner)
        self._select_page(page, note_page.pk)
        toolbar = page.locator('#notesToolbar')
        layout = toolbar.evaluate('''element => ({
            wrap: getComputedStyle(element).flexWrap,
            overflows: element.scrollWidth > element.clientWidth
        })''')
        self.assertEqual(layout['wrap'], 'nowrap')
        self.assertTrue(layout['overflows'])
        page.locator('[data-size-toggle]').click()
        preview_size = page.locator('#notesInkWidthPreview').evaluate(
            'element => [element.getBoundingClientRect().width, element.getBoundingClientRect().height]'
        )
        page.locator('[data-ink-width="12"]').click()
        self.assertEqual(
            page.locator('#notesInkWidthPreview').evaluate(
                'element => [element.getBoundingClientRect().width, element.getBoundingClientRect().height]'
            ),
            preview_size,
        )
        work_area = page.locator('#notesWorkArea')
        scroll_metrics = work_area.evaluate(
            'element => [element.scrollWidth, element.clientWidth, element.scrollHeight, element.clientHeight]'
        )
        self.assertGreater(scroll_metrics[0], scroll_metrics[1])
        self.assertGreater(scroll_metrics[2], scroll_metrics[3])
        work_area.evaluate('element => { element.scrollTop = 0; element.scrollLeft = 0; }')
        point = work_area.bounding_box()
        page.mouse.move(point['x'] + point['width'] / 2, point['y'] + point['height'] / 2)
        page.mouse.wheel(0, 350)
        self.assertGreater(work_area.evaluate('element => element.scrollTop'), 0)
        page.keyboard.down('Shift')
        page.mouse.wheel(0, 250)
        page.keyboard.up('Shift')
        self.assertGreater(work_area.evaluate('element => element.scrollLeft'), 0)
        before = work_area.evaluate('element => [element.scrollTop, element.scrollLeft]')
        prevented = work_area.evaluate('''element => {
            const event = new WheelEvent('wheel', {
                bubbles: true, cancelable: true, deltaY: 100, ctrlKey: true
            });
            element.dispatchEvent(event);
            return event.defaultPrevented;
        }''')
        self.assertFalse(prevented)
        self.assertEqual(
            work_area.evaluate('element => [element.scrollTop, element.scrollLeft]'),
            before,
        )
        self._assert_browser_clean(signals)

    def test_notes_navigation_toggle_persists_only_from_notes_script(self):
        page, signals = self._new_page(self.owner)
        toggle = page.locator('#projectMenuToggle')
        self.assertEqual(toggle.get_attribute('data-bound'), 'true')
        toggle.click()
        self.assertIn('collapsed', page.locator('#projectNavigation').get_attribute('class'))
        page.reload()
        self.assertIn('collapsed', page.locator('#projectNavigation').get_attribute('class'))
        page.locator('#projectMenuToggle').click()
        page.get_by_role('link', name='Resumo', exact=True).click()
        self.assertEqual(page.locator('script[src*="notes/navigation.js"]').count(), 0)
        self.assertIsNone(page.locator('#projectMenuToggle').get_attribute('data-bound'))
        self._assert_browser_clean(signals)

    def test_tool_shortcuts_text_color_and_disabled_formatting(self):
        note_page = self._shared_page()
        page, signals = self._new_page(self.owner)
        self._select_page(page, note_page.pk)
        page.locator('[data-tool="text"]').click()
        page.locator('#notesWorkArea').click(position={'x': 220, 'y': 30})
        content = page.locator('.notes-text-content').last
        content.fill('Texto colorido')
        content.press('Control+a')
        page.locator('button[data-color="#62d995"]').click()
        style_color = page.locator('.notes-text-content').last.locator('span').evaluate(
            'element => element.style.color'
        )
        self.assertEqual(style_color, 'rgb(98, 217, 149)')
        content.press('p')
        self.assertEqual(page.locator('button[data-tool="select"]').get_attribute('aria-pressed'), 'true')
        page.keyboard.press('Escape')
        page.keyboard.press('p')
        self.assertEqual(page.locator('button[data-tool="pencil"]').get_attribute('aria-pressed'), 'true')
        self.assertTrue(page.locator('#notesFontSize').is_disabled())
        page.keyboard.press('t')
        self.assertEqual(page.locator('button[data-tool="text"]').get_attribute('aria-pressed'), 'true')
        page.locator('#notesFontSize').focus()
        page.keyboard.press('p')
        self.assertEqual(page.locator('button[data-tool="text"]').get_attribute('aria-pressed'), 'true')
        page.locator('button[data-tool="select"]').click()
        self._assert_browser_clean(signals)

    def test_canvas_fills_remaining_height_at_all_requested_viewports(self):
        note_page = self._shared_page()
        page, signals = self._new_page(
            self.owner,
            viewport={'width': 1366, 'height': 768},
        )
        self._select_page(page, note_page.pk)
        self.assertFalse(page.locator('#notesTreeStatus').is_visible())
        page.set_viewport_size({'width': 1366, 'height': 768})

        for viewport in (
            {'width': 1366, 'height': 768},
            {'width': 1920, 'height': 1080},
            {'width': 1280, 'height': 600},
            {'width': 1024, 'height': 576},
        ):
            page.set_viewport_size(viewport)
            metrics = page.evaluate('''() => {
                const area = document.getElementById('notesWorkArea');
                const root = document.querySelector('.project-notes-page');
                const rect = area.getBoundingClientRect();
                return {
                    viewport: [innerWidth, innerHeight],
                    areaHeight: rect.height,
                    bottomGap: innerHeight - rect.bottom,
                    rootClientHeight: root.clientHeight,
                    rootScrollHeight: root.scrollHeight,
                    rootScrollTop: root.scrollTop,
                    chain: Array.from(document.querySelectorAll(
                        '.project-notes-page,.project-header,.project-navigation,.project-content,' +
                        '.notes-layout,.notes-sidebar,.notes-main,' +
                        '.notes-page-heading,.notes-editor,.notes-toolbar-shell,.notes-toolbar-topline,' +
                        '.notes-toolbar,.notes-toolbar-group,.notes-toolbar-controls,' +
                        '.notes-toolbar-group-label,.notes-work-area'
                    )).map(element => ({
                        selector: element.id || element.className,
                        rect: element.getBoundingClientRect().toJSON(),
                        flex: getComputedStyle(element).flex,
                        minHeight: getComputedStyle(element).minHeight,
                        overflow: getComputedStyle(element).overflow
                    }))
                };
            }''')
            self.assertGreaterEqual(metrics['areaHeight'], 520, (viewport, metrics))
            if viewport['height'] >= 768:
                self.assertGreaterEqual(metrics['bottomGap'], -1, (viewport, metrics))
                self.assertLessEqual(metrics['bottomGap'], 16, (viewport, metrics))
            else:
                self.assertGreater(
                    metrics['rootScrollHeight'],
                    metrics['rootClientHeight'],
                    (viewport, metrics),
                )

        page.set_viewport_size({'width': 1366, 'height': 768})
        area = page.locator('#notesWorkArea')
        initial_height = area.evaluate('element => element.getBoundingClientRect().height')
        toolbar = page.locator('#notesToolbar')
        toolbar_height = toolbar.evaluate('element => element.getBoundingClientRect().height')
        page.locator('#notesToolbarToggle').click()
        page.wait_for_function(
            'document.getElementById("notesToolbar").hidden === true'
        )
        after_toolbar_collapse = area.evaluate(
            'element => element.getBoundingClientRect().height'
        )
        self.assertGreaterEqual(
            after_toolbar_collapse - initial_height,
            toolbar_height - 2,
        )
        page.locator('#notesToolbarToggle').click()
        page.wait_for_function(
            'document.getElementById("notesToolbar").hidden === false'
        )
        self.assertAlmostEqual(
            area.evaluate('element => element.getBoundingClientRect().height'),
            initial_height,
            delta=1,
        )

        navigation = page.locator('#projectNavigation')
        navigation_height = navigation.evaluate('element => element.getBoundingClientRect().height')
        page.locator('#projectMenuToggle').click()
        page.wait_for_function(
            'document.getElementById("projectNavigation").classList.contains("collapsed")'
        )
        page.wait_for_function(
            'document.getElementById("projectNavigation").getBoundingClientRect().height < 1'
        )
        after_navigation_collapse = area.evaluate(
            'element => element.getBoundingClientRect().height'
        )
        self.assertGreaterEqual(
            after_navigation_collapse - initial_height,
            navigation_height - 2,
        )
        page.locator('#projectMenuToggle').click()
        page.wait_for_function(
            '!document.getElementById("projectNavigation").classList.contains("collapsed")'
        )
        page.wait_for_function(
            'document.getElementById("projectNavigation").getBoundingClientRect().height >= 32'
        )
        self.assertAlmostEqual(
            area.evaluate('element => element.getBoundingClientRect().height'),
            initial_height,
            delta=1,
        )

        page.locator('[data-tool="text"]').click()
        page.locator('#notesWorkArea').click(position={'x': 220, 'y': 60})
        page.locator('.notes-text-content').fill('Coordenadas preservadas ao rolar')
        page.wait_for_function(
            'document.getElementById("notesSaveLabel").textContent === "Salvo"'
        )
        original = page.evaluate(
            'window.notesEditor.getElements().map(item => ({x:item.x,y:item.y,w:item.w}))'
        )
        area.evaluate('element => { element.scrollTop = 0; element.scrollLeft = 0; }')
        bounds = area.bounding_box()
        page.mouse.move(bounds['x'] + bounds['width'] / 2, bounds['y'] + bounds['height'] / 2)
        page.mouse.wheel(0, 300)
        page.wait_for_function(
            'document.getElementById("notesWorkArea").scrollTop > 0'
        )
        self.assertGreater(area.evaluate('element => element.scrollTop'), 0)
        self.assertEqual(
            page.evaluate(
                'window.notesEditor.getElements().map(item => ({x:item.x,y:item.y,w:item.w}))'
            ),
            original,
        )
        area.evaluate('element => { element.scrollTop = element.scrollHeight; }')
        page.set_viewport_size({'width': 1024, 'height': 576})
        root = page.locator('.project-notes-page')
        root.evaluate('element => { element.scrollTop = 0; }')
        bounds = area.bounding_box()
        page.mouse.move(bounds['x'] + bounds['width'] / 2, bounds['y'] + bounds['height'] / 2)
        page.mouse.wheel(0, 400)
        page.wait_for_function(
            'document.querySelector(".project-notes-page").scrollTop > 0'
        )
        self.assertGreater(root.evaluate('element => element.scrollTop'), 0)
        self.assertEqual(
            page.evaluate(
                'window.notesEditor.getElements().map(item => ({x:item.x,y:item.y,w:item.w}))'
            ),
            original,
        )
        self._assert_browser_clean(signals)

    def test_tree_loading_indicator_is_hidden_after_load_and_retry_appears_on_error(self):
        page, signals = self._new_page(self.owner)
        status = page.locator('#notesTreeStatus')
        self.assertFalse(status.is_visible())
        self.assertFalse(status.get_by_text('Carregando notas…').is_visible())
        self.assertTrue(page.locator('#notesTree').is_visible())

        requests = {'count': 0}

        def fail_once(route):
            requests['count'] += 1
            if requests['count'] == 1:
                route.fulfill(
                    status=503,
                    content_type='application/json',
                    body='{"error":"Falha temporária de teste"}',
                )
            else:
                route.continue_()

        page.route('**/notes/api/tree/', fail_once)
        page.reload()
        page.get_by_text('Falha temporária de teste', exact=True).wait_for()
        page.get_by_role('button', name='Tentar de novo').wait_for()
        page.get_by_role('button', name='Tentar de novo').click()
        page.get_by_role('button', name='Seção compartilhada', exact=True).wait_for()
        self.assertFalse(status.is_visible())
        self.assertFalse(status.get_by_text('Carregando notas…').is_visible())
        self._assert_browser_clean(signals, allowed_statuses=(503,))

    def test_realtime_initialization_failure_does_not_block_tree(self):
        context = self.browser.new_context()
        context.add_init_script(
            "Object.defineProperty(Crypto.prototype, 'randomUUID', "
            "{ configurable: true, value: undefined });"
        )
        self.contexts.append(context)
        client = Client()
        client.force_login(self.owner)
        context.add_cookies([{
            'name': settings.SESSION_COOKIE_NAME,
            'value': client.cookies[settings.SESSION_COOKIE_NAME].value,
            'url': self.live_server_url,
        }])
        page = context.new_page()
        page_errors = []
        page.on('pageerror', lambda error: page_errors.append(str(error)))
        page.goto(f'{self.live_server_url}/projetos/{self.project.pk}/notes/')
        page.get_by_role('button', name='Seção compartilhada', exact=True).wait_for()
        self.assertEqual(page_errors, [])
