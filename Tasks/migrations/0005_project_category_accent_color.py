from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("Tasks", "0004_alter_task_deadline"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="category",
            field=models.CharField(
                choices=[
                    ("general", "Geral"),
                    ("sales", "Vendas"),
                    ("personal", "Projeto pessoal"),
                    ("mobile", "Mobile"),
                    ("marketing", "Marketing"),
                ],
                default="general",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="project",
            name="accent_color",
            field=models.CharField(default="#a3c7ff", max_length=7),
        ),
    ]
