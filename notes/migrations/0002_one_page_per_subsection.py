from django.db import migrations
from django.db.models import Max


MAPPING_TABLE = 'notes_subsection_page_migration'


def split_pages(apps, schema_editor):
    SectionSubsection = apps.get_model('notes', 'Subsection')
    Page = apps.get_model('notes', 'Page')
    connection = schema_editor.connection
    quote = connection.ops.quote_name

    next_order = {}
    subsections = SectionSubsection.objects.order_by('section_id', 'order', 'pk')
    for subsection in list(subsections):
        pages = list(
            Page.objects.filter(subsection_id=subsection.pk).order_by('order', 'pk')
        )
        if not pages:
            page = Page.objects.create(
                subsection_id=subsection.pk,
                title=subsection.title,
                content={},
                version=1,
            )
            with connection.cursor() as cursor:
                cursor.execute(
                    f'INSERT INTO {quote(MAPPING_TABLE)} '
                    '(page_id, source_subsection_id, target_subsection_id, created_page, original_order) '
                    'VALUES (%s, %s, %s, %s, %s)',
                    [page.pk, subsection.pk, subsection.pk, 1, page.order],
                )
            continue

        if subsection.section_id not in next_order:
            last_order = SectionSubsection.objects.filter(
                section_id=subsection.section_id,
            ).aggregate(last_order=Max('order'))['last_order']
            next_order[subsection.section_id] = (last_order or 0) + 1

        for page in pages[1:]:
            new_subsection = SectionSubsection.objects.create(
                section_id=subsection.section_id,
                title=page.title,
                order=next_order[subsection.section_id],
                theme=subsection.theme,
            )
            next_order[subsection.section_id] += 1
            with connection.cursor() as cursor:
                cursor.execute(
                    f'INSERT INTO {quote(MAPPING_TABLE)} '
                    '(page_id, source_subsection_id, target_subsection_id, created_page, original_order) '
                    'VALUES (%s, %s, %s, %s, %s)',
                    [page.pk, subsection.pk, new_subsection.pk, 0, page.order],
                )
            Page.objects.filter(pk=page.pk).update(subsection_id=new_subsection.pk)


def merge_pages(apps, schema_editor):
    Subsection = apps.get_model('notes', 'Subsection')
    Page = apps.get_model('notes', 'Page')
    connection = schema_editor.connection
    quote = connection.ops.quote_name

    with connection.cursor() as cursor:
        cursor.execute(
            f'SELECT page_id, source_subsection_id, target_subsection_id, created_page, original_order '
            f'FROM {quote(MAPPING_TABLE)}'
        )
        mappings = cursor.fetchall()

    for page_id, source_id, target_id, created_page, original_order in mappings:
        page = Page.objects.filter(pk=page_id).first()
        if page is None:
            continue
        if created_page:
            if page.content == {} and page.version == 1 and page.updated_by_id is None:
                page.delete()
            continue

        if not Subsection.objects.filter(pk=source_id).exists():
            continue
        Page.objects.filter(pk=page_id).update(
            subsection_id=source_id,
            order=original_order,
        )
        if target_id != source_id:
            Subsection.objects.filter(pk=target_id, pages__isnull=True).delete()


class Migration(migrations.Migration):

    atomic = True

    dependencies = [
        ('notes', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                f'CREATE TABLE {MAPPING_TABLE} ('
                'page_id BIGINT PRIMARY KEY, '
                'source_subsection_id BIGINT NOT NULL, '
                'target_subsection_id BIGINT NOT NULL, '
                'created_page SMALLINT NOT NULL, '
                'original_order INTEGER NOT NULL)'
            ),
            reverse_sql=f'DROP TABLE {MAPPING_TABLE}',
        ),
        migrations.RunPython(split_pages, merge_pages),
    ]
