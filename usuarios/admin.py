from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import PerfilUsuario

# 1. Creamos la vista "en línea" para el Perfil
class PerfilUsuarioInline(admin.StackedInline):
    model = PerfilUsuario
    can_delete = False
    verbose_name_plural = 'Información de Agencia (Rol y Contacto)'
    fk_name = 'usuario'

# 2. Personalizamos el panel de Usuarios original de Django
class UserAdmin(BaseUserAdmin):
    inlines = (PerfilUsuarioInline,)
    
    
    list_display = ('username', 'email', 'first_name', 'last_name', 'get_rol')
    
    def get_rol(self, instance):
        
        if hasattr(instance, 'perfil'):
            return instance.perfil.get_rol_display()
        return "Sin Perfil"
    get_rol.short_description = 'Rol en la Agencia'


admin.site.unregister(User)
admin.site.register(User, UserAdmin)