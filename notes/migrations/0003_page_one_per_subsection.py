from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notes', '0002_one_page_per_subsection'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='page',
            constraint=models.UniqueConstraint(
                fields=('subsection',),
                name='notes_page_one_per_subsection',
            ),
        ),
    ]
