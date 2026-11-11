from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from Tasks.models import Project


class NotesPageNormalizationMigrationTests(TransactionTestCase):
    reset_sequences = True
    migrate_from = [('notes', '0001_initial')]
    migrate_to = [('notes', '0003_page_one_per_subsection')]

    def test_splits_extra_pages_and_creates_missing_page_reversibly(self):
        owner = get_user_model().objects.create_user(
            email='notes-migration@example.test',
            password='Temporary-test-Password-847!',
        )
        project = Project.objects.create(
            title='Notes migration',
            description='Migration test project',
            owner=owner,
        )

        MigrationExecutor(connection).migrate(self.migrate_from)
        try:
            old_apps = MigrationExecutor(connection).loader.project_state(
                self.migrate_from,
            ).apps
            Section = old_apps.get_model('notes', 'Section')
            Subsection = old_apps.get_model('notes', 'Subsection')
            Page = old_apps.get_model('notes', 'Page')
            section = Section.objects.create(project_id=project.pk, title='Seção', order=4)
            original = Subsection.objects.create(
                section_id=section.pk,
                title='Subseção original',
                order=3,
                theme='light',
            )
            content_by_page = {}
            source_pages = []
            for title, order, version in (
                ('Primeira', 1, 5),
                ('Segunda', 1, 7),
                ('Terceira', 4, 9),
            ):
                content = {'schema': 1, 'elements': [{'text': title}]}
                page = Page.objects.create(
                    subsection_id=original.pk,
                    title=title,
                    order=order,
                    content=content,
                    version=version,
                )
                source_pages.append(page)
                content_by_page[page.pk] = (content, version, order)
            empty_subsection = Subsection.objects.create(
                section_id=section.pk,
                title='Sem documento',
                order=8,
                theme='dark',
            )
            expected_first = min(source_pages, key=lambda page: (page.order, page.pk))

            MigrationExecutor(connection).migrate(self.migrate_to)

            from notes.models import Page as CurrentPage
            from notes.models import Subsection as CurrentSubsection

            original_subsections = list(
                CurrentSubsection.objects.filter(section_id=section.pk)
            )
            self.assertEqual(len(original_subsections), 4)
            self.assertEqual(
                CurrentPage.objects.filter(subsection__section_id=section.pk).count(),
                4,
            )
            extra_subsections = []
            for source_page in source_pages:
                migrated_page = CurrentPage.objects.get(pk=source_page.pk)
                content, version, _ = content_by_page[source_page.pk]
                self.assertEqual(migrated_page.content, content)
                self.assertEqual(migrated_page.version, version)
                self.assertEqual(
                    migrated_page.subsection.pages.count(),
                    1,
                )
                if source_page.pk != expected_first.pk:
                    extra_subsection = migrated_page.subsection
                    extra_subsections.append(extra_subsection)
                    self.assertEqual(extra_subsection.title, source_page.title)
                    self.assertEqual(extra_subsection.section_id, section.pk)
                    self.assertEqual(extra_subsection.theme, original.theme)
            self.assertEqual(
                CurrentPage.objects.get(pk=expected_first.pk).subsection_id,
                original.pk,
            )
            extra_orders = sorted(subsection.order for subsection in extra_subsections)
            self.assertEqual(extra_orders, [9, 10])
            empty_page = CurrentPage.objects.get(subsection_id=empty_subsection.pk)
            self.assertEqual(empty_page.title, empty_subsection.title)
            self.assertEqual(empty_page.content, {})
            self.assertEqual(empty_page.version, 1)

            MigrationExecutor(connection).migrate(self.migrate_from)
            old_apps = MigrationExecutor(connection).loader.project_state(
                self.migrate_from,
            ).apps
            Page = old_apps.get_model('notes', 'Page')
            Subsection = old_apps.get_model('notes', 'Subsection')
            self.assertEqual(Page.objects.filter(subsection_id=original.pk).count(), 3)
            self.assertEqual(Page.objects.filter(subsection_id=empty_subsection.pk).count(), 0)
            for source_page in source_pages:
                restored = Page.objects.get(pk=source_page.pk)
                content, version, order = content_by_page[source_page.pk]
                self.assertEqual(restored.subsection_id, original.pk)
                self.assertEqual(restored.content, content)
                self.assertEqual(restored.version, version)
                self.assertEqual(restored.order, order)
            self.assertEqual(Subsection.objects.filter(section_id=section.pk).count(), 2)
        finally:
            MigrationExecutor(connection).migrate(self.migrate_to)
