from django import forms
from django.core.validators import validate_email

class ProjectInvitationForm(forms.Form):
    member = forms.CharField(
        max_length=250,
        strip=True
    )
    
    def clean_member(self):
        value = self.cleaned_data['member'].strip()
        if not value:
            raise forms.ValidationError(
                'Informe um email ou um nome de usuário'
            )
        if '@' in value:
            validate_email(value)
        return value