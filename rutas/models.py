from django.db import models
import time
from django.conf import settings

class Patrocinador(models.Model):
    nombre = models.CharField(max_length=100)
    logo = models.ImageField(upload_to='logos_patrocinadores/', null=True, blank=True)

    def __str__(self):
        return self.nombre

class Parada(models.Model):
    TIPO_CHOICES = [
        ('OFICIAL', 'Oficial (Infraestructura Establecida)'),
        ('INFORMAL', 'Informal (Punto Frecuente por Costumbre)'),
    ]
    
    ESTADO_CHOICES = [
        ('ACTIVA', 'Operativa'),
        ('INACTIVA', 'Clausurada / En Reparación'),
    ]
    
    nombre = models.CharField(max_length=100)
    codigo = models.CharField(max_length=50, unique=True, blank=True)
    
    # Coordenadas
    latitud = models.FloatField()
    longitud = models.FloatField()
    
    # Campos adicionales
    referencia = models.CharField(max_length=200, help_text="Ej: Frente al C.C. Orinokia", blank=True, null=True)
    tipo = models.CharField(max_length=15, choices=TIPO_CHOICES, default='OFICIAL')
    estado = models.CharField(max_length=15, choices=ESTADO_CHOICES, default='ACTIVA')
    
    # Campo corregido y añadido
    tiempo_caminando = models.IntegerField(default=0, help_text="Minutos a pie hasta la parada")
    
    # Métricas ciudadanas
    reportes_limpieza = models.IntegerField(default=0)
    reportes_inseguridad = models.IntegerField(default=0)

    def save(self, *args, **kwargs):
        if not self.codigo:
            self.codigo = f"QR-PRD-{int(time.time())}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nombre} - {self.referencia}"

# rutas/models.py
class Ruta(models.Model):
    nombre = models.CharField(max_length=100)
    # Agregamos related_name='rutas'
    paradas = models.ManyToManyField(Parada, related_name='rutas') 
    activa = models.BooleanField(default=True)
    trazado = models.TextField(help_text="Puntos GPS del recorrido", null=True, blank=True)

    def __str__(self):
        return self.nombre
    
class AlertaOperativa(models.Model):
    TIPO_CHOICES = [
        ('general', '📢 Aviso General (Banner)'),
        ('trafico', '🚗 Congestión / Retraso (Mapa)'),
        ('incidente', '⚠️ Accidente / Vía Cerrada (Mapa)'),
    ]
    
    # NUEVO CAMPO: Relación con el usuario que creó la alerta
    usuario_creador = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        related_name='alertas_creadas'
    )
    
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default='general')
    mensaje = models.CharField(max_length=200, help_text="Ej: Paro de transporte, vía cerrada en Alta Vista...")
    activa = models.BooleanField(default=True, help_text="Desmarcar para quitar la alerta")
    latitud = models.CharField(max_length=50, null=True, blank=True)
    longitud = models.CharField(max_length=50, null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    dependiente = models.ForeignKey(
        'usuarios.Dependiente', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='alertas_operativas'
    )

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.mensaje[:30]}"
class Sugerencia(models.Model):
    TIPO_REPORTES = [
        ('ruta', 'Sugerencia de Ruta'),
        ('tranca', 'Reporte de Tranca/Congestión'),
        ('parada', 'Reporte de Parada/Tótem'),
    ]
    tipo = models.CharField(max_length=20, choices=TIPO_REPORTES)
    sector = models.CharField(max_length=100)
    referencia = models.CharField(max_length=200, blank=True)
    detalles = models.TextField()
    fecha = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.tipo} - {self.sector}"
    
class Campana(models.Model):
    nombre = models.CharField(max_length=100)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    patrocinador = models.ForeignKey(Patrocinador, on_delete=models.SET_NULL, null=True, blank=True)
    imagen_banner = models.ImageField(upload_to='campanas/')
    activa = models.BooleanField(default=True)

    def __str__(self):
        return self.nombre    
    

class ReporteRapido(models.Model):
    TIPO_REPORTES = [
        ('bus_lleno', '🚌 Bus Lleno / Sin Puestos'),
        ('trafico', '🚗 Retraso por Tráfico'),
        ('parada_sucia', '🚏 Parada en Mal Estado / Sucia'),
    ]

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    tipo = models.CharField(max_length=20, choices=TIPO_REPORTES)
    ruta = models.ForeignKey('Ruta', on_delete=models.CASCADE, null=True, blank=True)
    parada = models.ForeignKey('Parada', on_delete=models.CASCADE, null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.fecha_creacion.strftime('%H:%M')}"    