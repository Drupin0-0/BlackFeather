from django.conf import settings
from django.db import models

class Projeto(models.Model):
    title = models.CharField(max_length=20)
    team = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE
    )

    def __str__(self):
        return self.name
    
    