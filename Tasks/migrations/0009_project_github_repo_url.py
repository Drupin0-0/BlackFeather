from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Tasks', '0008_taskhistory'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='github_repo_url',
            field=models.URLField(blank=True, help_text='URL de um repositório público do GitHub.', max_length=255),
        ),
    ]
