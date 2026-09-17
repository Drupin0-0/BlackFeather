from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model

User = get_user_model()


class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ('email',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['email'].widget.attrs.update({
            'placeholder': 'Seu e-mail'
        })

        self.fields['password1'].widget.attrs.update({
            'placeholder': 'Crie uma senha forte'
        })

        self.fields['password2'].widget.attrs.update({
            'placeholder': 'Digite a senha novamente'
        })