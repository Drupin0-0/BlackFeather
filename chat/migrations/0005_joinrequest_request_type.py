from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("chat", "0004_directconversation_directmessage_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="joinrequest",
            name="request_type",
            field=models.CharField(
                choices=[
                    ("invite", "Convite para projeto"),
                    ("join", "Pedido para entrar no projeto"),
                ],
                default="invite",
                max_length=10,
            ),
        ),
    ]
