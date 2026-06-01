from django import forms
from .models import Parada

class ParadaForm(forms.ModelForm):
    class Meta:
        model = Parada
     
        fields = ['codigo', 'nombre', 'latitud', 'longitud', 'tiempo_caminando']
        widgets = {
            'codigo': forms.TextInput(attrs={'class': 'input-estilo', 'placeholder': 'Ej: P-001'}),
            'nombre': forms.TextInput(attrs={'class': 'input-estilo', 'placeholder': 'Ej: Plaza del Hierro'}),
            'latitud': forms.NumberInput(attrs={'class': 'input-estilo', 'step': 'any'}),
            'longitud': forms.NumberInput(attrs={'class': 'input-estilo', 'step': 'any'}),
            'tiempo_caminando': forms.NumberInput(attrs={'class': 'input-estilo', 'placeholder': 'Minutos'}),
        }