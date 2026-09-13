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
            'placeholder': 'Seu melhor e-mail'
        })

        if 'password1' in self.fields:
            self.fields['password1'].widget.attrs.update({
                'placeholder': 'Crie uma senha forte'
            })

        if 'password2' in self.fields:
            self.fields['password2'].widget.attrs.update({
                'placeholder': 'Digite a senha novamente'
            })

    def save(self, commit=True):
        user = super().save(commit=False)

        # O e-mail será usado como username
        user.username = self.cleaned_data['email']

        if commit:
            user.save()

        return user