from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_remove_userprofile_avatar_userprofile_avatar_hat_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='userprofile',
            name='avatar_hat',
        ),
        migrations.RemoveField(
            model_name='userprofile',
            name='avatar_suit',
        ),
        migrations.AddField(
            model_name='userprofile',
            name='avatar_bird',
            field=models.CharField(
                choices=[
                    ('aguia', 'Águia'),
                    ('corvo', 'Corvo'),
                    ('coruja', 'Coruja'),
                    ('papagaio', 'Papagaio'),
                ],
                default='corvo',
                max_length=20,
            ),
        ),
    ]