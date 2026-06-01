from django import forms
from .models import Unidad
from django.contrib.auth.models import User

class UnidadForm(forms.ModelForm):
    class Meta:
        model = Unidad
        fields = ['numero_unidad', 'conductor', 'propietario_flota', 'ruta_asignada', 'estado']
        
        labels = {
            'numero_unidad': 'Número de Unidad / Código del Bus',
            'conductor': 'Conductor Asignado (Chofer)',
            'propietario_flota': 'Propietario de la Flota (Dueño)',
            'ruta_asignada': 'Ruta del Recorrido Asignada',
            'estado': 'Estado Operativo de la Unidad',
        }
        
        widgets = {
            'numero_unidad': forms.TextInput(attrs={'style': 'width: 100%; padding: 10px; border-radius: 6px; border: 1px solid #cbd5e1; outline: none;', 'placeholder': 'Ej: BUS-001 (O dejar vacío para auto-generar)'}),
            'conductor': forms.Select(attrs={'style': 'width: 100%; padding: 10px; border-radius: 6px; border: 1px solid #cbd5e1; background: #f8fafc; outline: none;'}),
            'propietario_flota': forms.Select(attrs={'style': 'width: 100%; padding: 10px; border-radius: 6px; border: 1px solid #cbd5e1; background: #f8fafc; outline: none;'}),
            'ruta_asignada': forms.Select(attrs={'style': 'width: 100%; padding: 10px; border-radius: 6px; border: 1px solid #cbd5e1; background: #f8fafc; outline: none;'}),
            'estado': forms.Select(attrs={'style': 'width: 100%; padding: 10px; border-radius: 6px; border: 1px solid #cbd5e1; background: #f8fafc; outline: none;'}),
        }

def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
       
        # Le decimos a Django que traiga a TODOS los usuarios (.all()) sin importar su rol
        self.fields['conductor'].queryset = User.objects.all()
        self.fields['propietario_flota'].queryset = User.objects.all()
        
        # Mantenemos los textos de ayuda para que el diseño siga viéndose profesional
        self.fields['conductor'].empty_label = "-- Seleccione un Chofer Disponible --"
        self.fields['propietario_flota'].empty_label = "-- Seleccione un Dueño de Flota --"
        self.fields['ruta_asignada'].empty_label = "-- Seleccione una Ruta Activa --" 

def clean_numero_unidad(self):
        numero = self.cleaned_data.get('numero_unidad')
        # Si el usuario no escribe un número, el sistema le genera uno secuencial automático
        if not numero or numero.strip() == "":
            ultimo_bus = Unidad.objects.all().order_by('id').last()
            if ultimo_bus and ultimo_bus.numero_unidad.startswith("BUS-"):
                try:
                    num_secuencial = int(ultimo_bus.numero_unidad.split("-")[1]) + 1
                    return f"BUS-{num_secuencial:03d}"
                except ValueError:
                    pass
            return f"BUS-001"
        return numero