from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import PerfilUsuario
from .models import TicketSoporte

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

@admin.register(TicketSoporte)
class TicketSoporteAdmin(admin.ModelAdmin):
    # Columnas que verá el equipo de soporte en la tabla
    list_display = ('id', 'asunto', 'usuario', 'estado', 'fecha_creacion')
    
    # Filtros laterales para buscar rápidamente
    list_filter = ('estado', 'fecha_creacion')
    search_fields = ('usuario__username', 'asunto')
    
    # Protegemos el mensaje original para que el operador no lo altere
    readonly_fields = ('usuario', 'asunto', 'mensaje', 'fecha_creacion')
    
    # Diseño de la pantalla de respuesta
    fieldsets = (
        ('Mensaje Original del Ciudadano', {
            'fields': ('usuario', 'asunto', 'mensaje', 'fecha_creacion')
        }),
        ('Área de Resolución (Soporte Técnico)', {
            'fields': ('respuesta_admin', 'estado')
        }),
    )