from django.contrib import admin
from .models import HistorialTurno, MensajeFlota, RegistroSesion, Ruta, Unidad
from rutas.models import Ruta

admin.site.register(Ruta)
admin.site.register(Unidad)
admin.site.register(Unidad)
admin.site.register(MensajeFlota)
admin.site.register(RegistroSesion)
admin.site.register(HistorialTurno)