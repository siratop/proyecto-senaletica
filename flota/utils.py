from django.utils import timezone
from .models import HistorialTurno

def registrar_inicio_turno(bus_objeto, conductor_objeto):
    """
    Verifica si el chofer ya tiene un turno abierto para este bus.
    Si no existe ninguno activo, crea un registro nuevo en el historial.
    """
    # Buscamos si ya hay un turno activo (donde hora_fin sea null)
    turno_activo = HistorialTurno.objects.filter(
        bus=bus_objeto, 
        conductor=conductor_objeto, 
        hora_fin__isnull=True
    ).exists()
    
    if not turno_activo:
        # No hay turno activo, abrimos uno nuevo en la bitácora
        HistorialTurno.objects.create(
            bus=bus_objeto,
            conductor=conductor_objeto
        )
        print(f"[HISTORIAL] Turno ABIERTO para Unidad {bus_objeto.numero_unidad}")

def registrar_fin_turno(bus_objeto, conductor_objeto):
    """
    Busca el turno activo actual de este bus y chofer, 
    y estampa la hora exacta de salida.
    """
    # Buscamos el turno abierto
    turno_abierto = HistorialTurno.objects.filter(
        bus=bus_objeto, 
        conductor=conductor_objeto, 
        hora_fin__isnull=True
    ).first()
    
    if turno_abierto:
        # Cerramos el turno con la hora y fecha de este instante
        turno_abierto.hora_fin = timezone.now()
        turno_abierto.save()
        print(f"[HISTORIAL] Turno CERRADO para Unidad {bus_objeto.numero_unidad}")