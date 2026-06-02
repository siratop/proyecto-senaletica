import uuid
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class Dependiente(models.Model):
    """Clase Hija: Representa a un niño o adulto mayor bajo el cuidado de un ciudadano"""
    
    RELACION_CHOICES = [
        ('HIJO', 'Hijo/a'),
        ('PADRE', 'Padre/Madre (Adulto Mayor)'),
        ('OTRO', 'Familiar / Otro'),
    ]
    
    # Llave foránea que conecta con la "Clase Padre" (El usuario registrado)
    tutor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='dependientes')
    
    nombre_completo = models.CharField(max_length=100)
    relacion = models.CharField(max_length=20, choices=RELACION_CHOICES)
    condicion_medica = models.TextField(blank=True, null=True, help_text="Alergias, tipo de sangre, medicamentos...")
    telefono_emergencia = models.CharField(max_length=20, help_text="A dónde llamar si escanean el NFC")
    
    # EL CORAZÓN DEL NFC: Un código único e irrepetible generado automáticamente
    token_nfc = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    
    fecha_registro = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.nombre_completo} - Dependiente de {self.tutor.username}"
    
class RegistroActividad(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    fecha = models.DateTimeField(auto_now_add=True)
    accion = models.CharField(max_length=200)    

class TarjetaNFC(models.Model):
    usuario = models.OneToOneField(User, on_delete=models.CASCADE)
    codigo_uid = models.CharField(max_length=50, unique=True)
    activa = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.usuario.username} - {self.codigo_uid}"    
    
# 1. EL PERFIL EXPANDIDO DEL USUARIO
class PerfilUsuario(models.Model):
    ROLES = (
        ('ciudadano', 'Ciudadano Normal'),
        ('conductor', 'Dueño de Unidad / Conductor'),
        ('flota', 'Dueño de Flota'),
    )
    usuario = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')
    telefono = models.CharField(max_length=20, blank=True, null=True)
    # El correo ya viene por defecto en el User de Django (usuario.email)
    rol = models.CharField(max_length=20, choices=ROLES, default='ciudadano')
    ultima_modificacion = models.DateTimeField(null=True, blank=True)
    correo_emergencia = models.EmailField(
        max_length=255, 
        blank=True, 
        null=True, 
        help_text="Correo del familiar que recibirá la alerta SOS"
    )
  
    nombre_flota = models.CharField(max_length=100, blank=True, null=True, help_text="Nombre público de la empresa/flota")
    fecha_cambio_nombre = models.DateTimeField(blank=True, null=True, help_text="Fecha del último cambio de nombre")

    def __str__(self):
        return f"{self.usuario.username} - {self.get_rol_display()}"
        
    def puede_cambiar_nombre(self):
        """Verifica si han pasado 30 días desde el último cambio"""
        if not self.fecha_cambio_nombre:
            return True 
        diferencia = timezone.now() - self.fecha_cambio_nombre
        return diferencia.days >= 30

class SolicitudOperador(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    telefono_contacto = models.CharField(max_length=20)
    experiencia_anios = models.IntegerField(help_text="Años de experiencia manejando unidades pesadas")
    tipo_licencia = models.CharField(max_length=50, help_text="Ej: Título de 5ta")
    mensaje = models.TextField(blank=True, help_text="¿Por qué desea unirse a nuestra red?")
    fecha_solicitud = models.DateTimeField(auto_now_add=True)
    estado = models.CharField(max_length=20, default='pendiente', choices=[('pendiente', 'Pendiente'), ('aprobada', 'Aprobada'), ('rechazada', 'Rechazada')])

    def __str__(self):
        return f"Solicitud de {self.usuario.username}"
  