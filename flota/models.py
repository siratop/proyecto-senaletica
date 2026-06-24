from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from rutas.models import Ruta
import uuid
class Unidad(models.Model):
    ESTADOS = (
        ('operativa', 'Operativa (En Ruta)'),
        ('inactiva', 'Inactiva (Fuera de Servicio)'),
        ('averiada', 'Averiada / En Taller'),
    )
    
    numero_unidad = models.CharField(max_length=10, unique=True)
    conductor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='bus_asignado')
    ruta_asignada = models.ForeignKey('rutas.Ruta', on_delete=models.SET_NULL, null=True, blank=True, related_name='buses_en_ruta')
    propietario_flota = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='flota_propia')
    latitud_actual = models.FloatField(null=True, blank=True)
    longitud_actual = models.FloatField(null=True, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='inactiva')
    ultima_actualizacion = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Bus {self.numero_unidad}"
    
class MensajeFlota(models.Model):
    """Guarda los mensajes enviados desde el dueño de la flota al chofer"""
    unidad = models.ForeignKey(Unidad, on_delete=models.CASCADE, related_name='mensajes')
    mensaje = models.CharField(max_length=255)
    fecha_envio = models.DateTimeField(auto_now_add=True)
    leido = models.BooleanField(default=False)

    def __str__(self):
        return f"Mensaje a Unidad {self.unidad.numero_unidad} - {self.fecha_envio.strftime('%d/%m %H:%M')}"

class RegistroSesion(models.Model):
    """Calcula cuánto tiempo pasa un chofer transmitiendo su ruta"""
    unidad = models.ForeignKey(Unidad, on_delete=models.CASCADE, related_name='sesiones')
    hora_inicio = models.DateTimeField(default=timezone.now)
    hora_fin = models.DateTimeField(null=True, blank=True)
    
    @property
    def duracion_minutos(self):
        if self.hora_fin:
            delta = self.hora_fin - self.hora_inicio
        else:
            delta = timezone.now() - self.hora_inicio
        return int(delta.total_seconds() / 60)

    def __str__(self):
        return f"Sesión Unidad {self.unidad.numero_unidad} - {self.duracion_minutos} min"
    
class HistorialTurno(models.Model):
    # CORRECCIÓN: Ahora apunta a la clase 'Unidad' que está arriba
    bus = models.ForeignKey(Unidad, on_delete=models.CASCADE, related_name='historiales')
    conductor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    fecha = models.DateField(auto_now_add=True, verbose_name="Fecha del Turno")
    hora_inicio = models.DateTimeField(auto_now_add=True, verbose_name="Hora de Entrada")
    hora_fin = models.DateTimeField(null=True, blank=True, verbose_name="Hora de Salida")
    session_id = models.CharField(max_length=100, null=True, blank=True, unique=True)
    class Meta:
        verbose_name = "Historial de Turno"
        verbose_name_plural = "Historiales de Turnos"
        ordering = ['-fecha', '-hora_inicio']

    def __str__(self):
        return f"Turno: Unidad {self.bus.numero_unidad} - {self.fecha}"

    def duracion(self):
        """Calcula el tiempo exacto que el chofer estuvo transmitiendo en la vía"""
        if self.hora_fin:
            diferencia = self.hora_fin - self.hora_inicio
            # Extraemos horas y minutos matemáticamente
            segundos_totales = int(diferencia.total_seconds())
            horas = segundos_totales // 3600
            minutos = (segundos_totales % 3600) // 60
            return f"{horas}h {minutos}m"
        return "En curso..."
    
class ControlMecanico(models.Model):
    """Guarda el estatus de las piezas y el kilometraje de la unidad"""
    unidad = models.OneToOneField(Unidad, on_delete=models.CASCADE, related_name='mecanica')
    kilometraje = models.IntegerField(default=0)
    
    # Control de Aceite
    vida_aceite = models.IntegerField(default=100) # Porcentaje 0 a 100
    fecha_aceite = models.DateField(null=True, blank=True)
    
    # Control de Cauchos
    vida_cauchos = models.IntegerField(default=100) # Porcentaje 0 a 100
    fecha_cauchos = models.DateField(null=True, blank=True)
    
    # Estatus Físicos
    ESTADO_LIMPIEZA = (('Limpio', 'Limpio'), ('Sucio', 'Sucio'))
    estado_limpieza = models.CharField(max_length=20, choices=ESTADO_LIMPIEZA, default='Limpio')
    
    ESTADO_MECANICO = (
        ('Optimo', 'Óptimo'), 
        ('Pendiente', 'Pendiente para revisión'), 
        ('Danado', 'Dañado')
    )
    estado_mecanico = models.CharField(max_length=50, choices=ESTADO_MECANICO, default='Optimo')
    
    def __str__(self):
        return f"Mecánica - {self.unidad.numero_unidad}"

class ControlLegal(models.Model):
    """Guarda las fechas de vencimiento para el INTT y la Alcaldía de Caroní"""
    unidad = models.OneToOneField(Unidad, on_delete=models.CASCADE, related_name='legal')
    carnet_circulacion = models.BooleanField(default=False)
    vencimiento_rcv = models.DateField(null=True, blank=True)
    vencimiento_imttv = models.DateField(null=True, blank=True)
    pago_alcaldia = models.CharField(max_length=50, default='Sin registrar', choices=[
        ('Al día', 'Al día'),
        ('Pendiente T1', 'Pendiente T1'),
        ('Pendiente T2', 'Pendiente T2'),
        ('Pendiente T3', 'Pendiente T3'),
        ('En Mora', 'En Mora')
    ])
    
    def __str__(self):
        return f"Legal - {self.unidad.numero_unidad}"

class ControlLegal(models.Model):
    """Guarda las fechas de vencimiento para el INTT y la Alcaldía de Caroní"""
    unidad = models.OneToOneField(Unidad, on_delete=models.CASCADE, related_name='legal')
    carnet_circulacion = models.BooleanField(default=False)
    vencimiento_rcv = models.DateField(null=True, blank=True)
    vencimiento_imttv = models.DateField(null=True, blank=True)
    pago_alcaldia = models.CharField(max_length=50, default='Sin registrar', choices=[
        ('Al día', 'Al día'),
        ('Pendiente T1', 'Pendiente T1'),
        ('Pendiente T2', 'Pendiente T2'),
        ('Pendiente T3', 'Pendiente T3'),
        ('En Mora', 'En Mora')
    ])
    
    def __str__(self):
        return f"Legal - {self.unidad.numero_unidad}"   
    
# =========================================================
# MÓDULO DE ALERTAS TELEGRAM (Señal Ética +)
# =========================================================

class SuscripcionTelegram(models.Model):
    """Guarda el ID secreto de Telegram vinculado a la cuenta del usuario web"""
    usuario = models.OneToOneField(User, on_delete=models.CASCADE, related_name='telegram_data')
    chat_id = models.CharField(max_length=50, unique=True, help_text="ID interno del chat de Telegram")
    # Generamos un código único para que el usuario lo mande al bot y validemos su identidad
    codigo_vinculacion = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    activo = models.BooleanField(default=True)
    fecha_vinculacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Telegram de {self.usuario.username}"

class AlertaParada(models.Model):
    """Fila temporal: Un usuario esperando un bus en una parada específica"""
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='alertas_activas')
    parada = models.ForeignKey('rutas.Parada', on_delete=models.CASCADE)
    # Opcional: Por si solo quiere que le avise de una ruta en específico y no cualquier bus que pase
    ruta_esperada = models.ForeignKey('rutas.Ruta', on_delete=models.CASCADE, null=True, blank=True) 
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    activa = models.BooleanField(default=True)

    def __str__(self):
        return f"Alerta de {self.usuario.username} en {self.parada.nombre}"    