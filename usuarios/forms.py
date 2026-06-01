from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django import forms

class RegistroInclusivoForm(UserCreationForm):
   
    email = forms.EmailField(required=True, help_text='Requerido para recuperación de cuenta.')
    first_name = forms.CharField(max_length=30, required=False, label='Nombre')
    last_name = forms.CharField(max_length=30, required=False, label='Apellido')

    class Meta(UserCreationForm.Meta):
        model = User
        fields = UserCreationForm.Meta.fields + ('email', 'first_name', 'last_name')