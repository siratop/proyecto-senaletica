from django.contrib import admin
from .models import Parada, Patrocinador
from .models import Parada,  Patrocinador, AlertaOperativa
from .models import Sugerencia

admin.site.register(Parada)
admin.site.register(Patrocinador)
admin.site.register(AlertaOperativa)
admin.site.register(Sugerencia)