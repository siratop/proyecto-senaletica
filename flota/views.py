import math
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import CreateView, ListView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.models import User
from .models import Unidad, Ruta
from .forms import UnidadForm
from usuarios.models import PerfilUsuario
from django.contrib import messages
from django.db import IntegrityError
from django.utils import timezone
from datetime import timedelta
from rutas.models import Ruta, Parada
from .models import MensajeFlota, RegistroSesion
from .models import HistorialTurno
from django.db.models import Q
from .models import  ControlMecanico, ControlLegal
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from datetime import datetime
from django.db import transaction

# =========================================================
# MOTOR MATEMÁTICO (Geocerca para el mapa ciudadano)
# =========================================================

def calcular_distancia_metros(lat1, lon1, lat2, lon2):
    """Calcula la distancia exacta en metros entre dos coordenadas GPS usando la fórmula de Haversine"""
    R = 6371000  # Radio de la Tierra en metros
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + \
        math.cos(phi1) * math.cos(phi2) * \
        math.sin(delta_lambda / 2.0) ** 2
    
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def calcular_distancia_segmento(lat_bus, lon_bus, lat1, lon1, lat2, lon2):
    """Calcula la distancia mínima entre un bus y la LÍNEA de la calle, no solo los clics"""
    pasos = 10  # Divide la calle trazada en 10 puntos virtuales
    min_dist = float('inf')
    for i in range(pasos + 1):
        frac = i / pasos
        lat_inter = lat1 + (lat2 - lat1) * frac
        lon_inter = lon1 + (lon2 - lon1) * frac
        dist = calcular_distancia_metros(lat_bus, lon_bus, lat_inter, lon_inter)
        if dist < min_dist:
            min_dist = dist
    return min_dist

# =========================================================
# GESTIÓN DE OPERADORES Y ROLES (Nivel de Usuario)
# =========================================================

@staff_member_required
def gestionar_usuarios(request):
    """Muestra el listado global de cuentas en el sistema"""
    return render(request, 'rutas/gestionar_usuarios.html', {
        'usuarios': User.objects.all()
    })

@staff_member_required
def editar_usuario(request, usuario_id):
    usuario_edit = get_object_or_404(User, id=usuario_id)
    perfil_edit, created = PerfilUsuario.objects.get_or_create(usuario=usuario_edit)

    if request.method == 'POST':
        usuario_edit.username = request.POST.get('username')
        usuario_edit.email = request.POST.get('email')
        usuario_edit.first_name = request.POST.get('first_name')
        usuario_edit.last_name = request.POST.get('last_name')
        usuario_edit.is_staff = request.POST.get('is_staff') == 'on'
        usuario_edit.save()

        nuevo_rol = request.POST.get('rol')
        if nuevo_rol:
            perfil_edit.rol = nuevo_rol
            perfil_edit.save()

        return redirect('gestionar_usuarios')

    return render(request, 'rutas/editar_usuario.html', {
        'usuario_edit': usuario_edit,
        'perfil_edit': perfil_edit
    })

# =========================================================
# CONSOLAS DE CONTROL Y RUTEO (Dashboards)
# =========================================================

@login_required
def dashboard_router(request):
    perfil, created = PerfilUsuario.objects.get_or_create(usuario=request.user)
    
    if perfil.rol == 'conductor':
        unidad = Unidad.objects.filter(conductor=request.user).first()
        return render(request, 'flota/dashboard_chofer.html',{'unidad': unidad})
    
    elif perfil.rol == 'flota':
        flota = Unidad.objects.filter(propietario_flota=request.user)
        rutas_activas = Ruta.objects.filter(activa=True)
        paradas_activas = Parada.objects.filter(estado='ACTIVA')
        
        rutas_json = []
        for r in rutas_activas:
            if r.trazado:
                try:
                    trazado_limpio = r.trazado.strip().replace("'", '"')
                    coords = json.loads(trazado_limpio)
                    rutas_json.append({
                        'id': r.id,
                        'nombre': r.nombre,
                        'color': getattr(r, 'color_hex', '#3b82f6'),
                        'coordenadas': coords
                    })
                except Exception as e:
                    print(f"❌ Error JSON ruta '{r.nombre}': {e}")

        paradas_json = []
        for p in paradas_activas:
            try:
                paradas_json.append({
                    'id': p.id,
                    'nombre': p.nombre,
                    'referencia': p.referencia or "Sin referencia",
                    'lat': float(str(p.latitud).replace(',', '.')),
                    'lon': float(str(p.longitud).replace(',', '.'))
                })
            except Exception as e:
                pass

        return render(request, 'flota/panel_flota.html', {
            'flota': flota,
            'rutas': rutas_activas,
            'rutas_json': rutas_json,
            'paradas_json': paradas_json
        })
    
    return redirect('inicio_general')

@login_required
def panel_chofer(request):
    unidad = Unidad.objects.filter(conductor=request.user).first()
    if not unidad:
        return render(request, 'mensaje_aviso.html', {
            'titulo': '⚠️ Acceso Restringido',
            'mensaje': 'Su usuario no tiene unidad asignada.'
        })
    return render(request, 'flota/dashboard_chofer.html', {'unidad': unidad})

# =========================================================
# TELEMETRÍA Y SERVICIOS API (Recepción desde la App)
# =========================================================

@csrf_exempt
def actualizar_gps(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            if data.get('token') != "SENALETICA_SECRETO_2026":
                return JsonResponse({'error': 'No autorizado'}, status=403)
                
            unidad_id = data.get('unidad_id')
            
            # BLOQUEO ATÓMICO: Congela la base de datos para esta unidad impidiendo duplicados
            with transaction.atomic():
                unidad = Unidad.objects.select_for_update().filter(numero_unidad=unidad_id).first()
                if not unidad:
                    return JsonResponse({'error': 'Unidad no encontrada'}, status=404)

                hoy = timezone.now().date()
                ahora = timezone.now().time()
                turnos_abiertos = HistorialTurno.objects.filter(bus=unidad, fecha=hoy, hora_fin__isnull=True)

                estado_texto = str(data.get('estado', '')).lower()
                en_servicio_flag = str(data.get('en_servicio', '')).lower()
                se_esta_apagando = (estado_texto == 'inactivo') or (en_servicio_flag in ['false', '0', 'no'])

                # --- LÓGICA DE APAGADO ---
                if se_esta_apagando:
                    unidad.estado = 'inactiva' 
                    unidad.save()
                    
                    for turno in turnos_abiertos:
                        turno.hora_fin = ahora
                        inicio_dt = datetime.combine(hoy, turno.hora_inicio)
                        fin_dt = datetime.combine(hoy, ahora)
                        diferencia = fin_dt - inicio_dt
                        horas = diferencia.seconds // 3600
                        minutos = (diferencia.seconds % 3600) // 60
                        turno.duracion = f"{horas}h {minutos}m"
                        turno.save()
                    
                    try:
                        channel_layer = get_channel_layer()
                        async_to_sync(channel_layer.group_send)(
                            'mapa_envivo',
                            {'type': 'enviar_ubicacion', 'datos': {'bus_id': str(unidad.id), 'lat': 0, 'lon': 0, 'unidad': unidad.numero_unidad, 'en_servicio': False}}
                        )
                    except Exception:
                        pass
                        
                    return JsonResponse({'status': 'ok', 'msg': 'Turno cerrado y desconectado'})

                # --- LÓGICA DE TRANSMISIÓN ---
                else:
                    lat = data.get('latitud', data.get('lat'))
                    lon = data.get('longitud', data.get('lon'))
                    
                    if lat and lon:
                        unidad.latitud_actual = lat
                        unidad.longitud_actual = lon
                        unidad.estado = 'operativa' 
                        unidad.ultima_actualizacion = timezone.now()
                        unidad.save()

                        if not turnos_abiertos.exists():
                            chofer_default = getattr(unidad, 'propietario_flota', None) or User.objects.first()
                            HistorialTurno.objects.create(bus=unidad, fecha=hoy, hora_inicio=ahora, conductor=chofer_default)

                        try:
                            channel_layer = get_channel_layer()
                            async_to_sync(channel_layer.group_send)(
                                'mapa_envivo', 
                                {'type': 'enviar_ubicacion', 'datos': {'bus_id': str(unidad.id), 'lat': lat, 'lon': lon, 'unidad': unidad.numero_unidad, 'en_servicio': True}}
                            )
                        except Exception:
                            pass

                        return JsonResponse({'status': 'ok', 'msg': 'GPS e Historial sincronizados'})
                        
                    return JsonResponse({'status': 'error', 'msg': 'Faltan coordenadas'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'msg': str(e)}, status=500)
            
    return JsonResponse({'status': 'error', 'msg': 'Método no permitido'}, status=405)



# =========================================================
# API PARA EL MAPA WEB (Respaldo en caso de que WS falle)
# =========================================================

def api_buses_activos(request):
    """API Pública: Envía al mapa web ÚNICAMENTE los buses rodando."""
    try:
        buses = Unidad.objects.all() 
        data_buses = []
        
        for u in buses:
            estado_actual = str(getattr(u, 'estado', '')).lower()
            if estado_actual not in ['operativa', 'activo']:
                continue 
            
            if u.latitud_actual and u.longitud_actual:
                unidad_identificador = getattr(u, 'placa', getattr(u, 'numero', f"N° {u.id}"))
                ruta_obj = getattr(u, 'ruta', getattr(u, 'ruta_asignada', None))
                
                try:
                    lat = float(str(u.latitud_actual).replace(',', '.'))
                    lon = float(str(u.longitud_actual).replace(',', '.'))
                except (ValueError, TypeError):
                    continue 
                
                data_buses.append({
                    'id': u.id,
                    'unidad': unidad_identificador, 
                    'lat': lat,
                    'lon': lon,
                    'ruta_nombre': ruta_obj.nombre if ruta_obj else 'Sin ruta',
                    'ruta_id': ruta_obj.id if ruta_obj else None,
                    'conductor': "Operador Activo" 
                })
                
        return JsonResponse({'buses': data_buses})
        
    except Exception as e:
        return JsonResponse({'error': str(e), 'buses': []}, status=500)


# =========================================================
# VISTAS CLÁSICAS CRUD Y ALERTAS
# =========================================================

@login_required
def api_buses_flota(request):
    unidades = Unidad.objects.filter(propietario_flota=request.user)
    data = []
    ahora = timezone.now()
    
    for u in unidades:
        estado_real = u.estado
        if u.ultima_actualizacion and estado_real.lower() in ['operativa', 'activo']:
            if ahora - u.ultima_actualizacion > timedelta(minutes=2):
                estado_real = 'inactiva'
                u.estado = 'inactiva'
                u.save()

        nombre_empresa = "Independiente"
        if u.propietario_flota and hasattr(u.propietario_flota, 'perfil'):
            if u.propietario_flota.perfil.nombre_flota:
                nombre_empresa = u.propietario_flota.perfil.nombre_flota

        conductor_nombre = f"{u.conductor.first_name} {u.conductor.last_name}".strip() if u.conductor else "No asignado"

        try:
            lat = float(str(u.latitud_actual).replace(',', '.')) if u.latitud_actual else 0.0
            lon = float(str(u.longitud_actual).replace(',', '.')) if u.longitud_actual else 0.0
        except ValueError:
            lat, lon = 0.0, 0.0

        data.append({
            'id': u.id,
            'unidad': getattr(u, 'numero_unidad', f"ID:{u.id}"),
            'estado': estado_real.lower(),
            'conductor_display': conductor_nombre,
            'lat': lat,
            'lon': lon,
            'actualizado': u.ultima_actualizacion.strftime("%H:%M:%S") if u.ultima_actualizacion else "--",
            'ruta': getattr(u, 'ruta_asignada', getattr(u, 'ruta', 'Sin Ruta')),
            'flota': nombre_empresa
        })
        
    return JsonResponse({'buses': data}, safe=False)

@staff_member_required
def listar_unidades(request):
    return render(request, 'flota/listar_unidades.html', {
        'unidades': Unidad.objects.all()
    })

@login_required
def editar_unidad(request, unidad_id):
    unidad = get_object_or_404(Unidad, id=unidad_id)
    if request.method == 'POST':
        form = UnidadForm(request.POST, instance=unidad)
        if form.is_valid():
            form.save()
            return redirect('panel_admin_amigable') 
    else:
        form = UnidadForm(instance=unidad)
        
    return render(request, 'flota/editar_unidad.html', {
        'form': form,
        'object': unidad
    })

class UnidadCreateView(CreateView):
    model = Unidad
    form_class = UnidadForm 
    template_name = 'flota/crear_unidad.html'
    success_url = reverse_lazy('panel_admin_amigable')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo'] = '🚌 Registrar Nueva Unidad de Transporte'
        context['subtitulo'] = 'Asigne un número de control/placa a un operador autenticado.'
        return context

class UnidadUpdateView(UpdateView):
    model = Unidad
    form_class = UnidadForm  
    template_name = 'flota/editar_unidad.html'
    success_url = reverse_lazy('panel_admin_amigable')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['usuarios'] = User.objects.all()
        context['rutas'] = Ruta.objects.all()
        return context
    
@login_required
def agregar_conductor_flota(request):
    if request.method == 'POST' and request.user.perfil.rol == 'flota':
        tipo_registro = request.POST.get('tipo_registro')
        numero_unidad = request.POST.get('numero_unidad')

        unidad_existente = Unidad.objects.filter(numero_unidad=numero_unidad).first()

        if tipo_registro == 'nuevo':
            if unidad_existente:
                messages.error(request, f"Error: La unidad {numero_unidad} ya está registrada.")
                return redirect('dashboard_router')
            
            nuevo_user = User.objects.create_user(username=request.POST.get('username'), password=request.POST.get('password'), first_name=request.POST.get('nombre'))
            PerfilUsuario.objects.create(usuario=nuevo_user, rol='conductor')
            Unidad.objects.create(numero_unidad=numero_unidad, conductor=nuevo_user, propietario_flota=request.user, estado='inactiva')
            messages.success(request, "Conductor y unidad creados.")

        elif tipo_registro == 'existente':
            username_existente = request.POST.get('username_existente')
            try:
                user_existente = User.objects.get(username=username_existente)
                
                if unidad_existente:
                    unidad_existente.conductor = user_existente
                    unidad_existente.propietario_flota = request.user
                    unidad_existente.save()
                    messages.success(request, f"La unidad {numero_unidad} ahora pertenece a tu flota con el conductor {username_existente}.")
                else:
                    Unidad.objects.create(numero_unidad=numero_unidad, conductor=user_existente, propietario_flota=request.user, estado='inactiva')
                    messages.success(request, "Unidad creada y conductor vinculado.")
                    
            except User.DoesNotExist:
                messages.error(request, "El usuario no existe.")
                
    return redirect('dashboard_router')

@login_required
def eliminar_conductor_flota(request, unidad_id):
    if request.method == 'POST' and request.user.perfil.rol == 'flota':
        unidad = Unidad.objects.filter(id=unidad_id, propietario_flota=request.user).first()
        if unidad:
            chofer = unidad.conductor
            unidad.delete() 
            if chofer:
                chofer.delete() 
            messages.success(request, "Conductor y unidad eliminados de su flota.")
    return redirect('dashboard_router') 

@login_required
def enviar_mensaje_chofer(request, unidad_id):
    if request.method == 'POST':
        data = json.loads(request.body)
        texto = data.get('mensaje', '')
        if texto:
            MensajeFlota.objects.create(unidad_id=unidad_id, mensaje=texto)
            return JsonResponse({'status': 'ok'})
    return JsonResponse({'status': 'error'})

@login_required
def leer_alertas_chofer(request):
    unidad = Unidad.objects.filter(conductor=request.user).first()
    if unidad:
        mensaje = MensajeFlota.objects.filter(unidad=unidad, leido=False).order_by('fecha_envio').first()
        if mensaje:
            mensaje.leido = True 
            mensaje.save()
            return JsonResponse({'hay_alerta': True, 'mensaje': mensaje.mensaje})
    return JsonResponse({'hay_alerta': False})

@login_required
def reportar_averia(request, unidad_id):
    if request.method == 'POST':
        unidad = Unidad.objects.filter(id=unidad_id, conductor=request.user).first()
        if unidad:
            unidad.estado = 'averiada' 
            sesion_abierta = RegistroSesion.objects.filter(unidad=unidad, hora_fin__isnull=True).first()
            if sesion_abierta:
                sesion_abierta.hora_fin = timezone.now()
                sesion_abierta.save()
                
            unidad.ultima_actualizacion = timezone.now()
            unidad.save()
    return redirect('dashboard_router')

@csrf_exempt
@login_required
def actualizar_ubicacion_chofer(request):
    """Recibe el GPS desde la página web del chofer y sincroniza idéntico a la App"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            lat = data.get('latitud')
            lon = data.get('longitud')
            en_servicio = data.get('en_servicio') 

            # BLOQUEO ATÓMICO: Igual que en la app
            with transaction.atomic():
                unidad = Unidad.objects.select_for_update().filter(conductor=request.user).first()
                if not unidad:
                    return JsonResponse({'status': 'error', 'msg': 'Unidad no encontrada'})

                hoy = timezone.now().date()
                ahora = timezone.now().time()
                turnos_abiertos = HistorialTurno.objects.filter(bus=unidad, fecha=hoy, hora_fin__isnull=True)

                if lat and lon and lat != 0:
                    unidad.latitud_actual = lat
                    unidad.longitud_actual = lon
                
                # --- LÓGICA DE TRANSMISIÓN WEB ---
                if en_servicio:
                    unidad.estado = 'operativa'
                    if not turnos_abiertos.exists():
                        HistorialTurno.objects.create(bus=unidad, fecha=hoy, hora_inicio=ahora, conductor=request.user)
                
                # --- LÓGICA DE APAGADO WEB ---
                else:
                    unidad.estado = 'inactiva'
                    for turno in turnos_abiertos:
                        turno.hora_fin = ahora
                        inicio_dt = datetime.combine(hoy, turno.hora_inicio)
                        fin_dt = datetime.combine(hoy, ahora)
                        diferencia = fin_dt - inicio_dt
                        horas = diferencia.seconds // 3600
                        minutos = (diferencia.seconds % 3600) // 60
                        turno.duracion = f"{horas}h {minutos}m"
                        turno.save()
                
                unidad.ultima_actualizacion = timezone.now()
                unidad.save()

                # Notificar a los mapas en vivo
                try:
                    channel_layer = get_channel_layer()
                    async_to_sync(channel_layer.group_send)(
                        'mapa_envivo',
                        {
                            'type': 'enviar_ubicacion',
                            'datos': {
                                'bus_id': str(unidad.id),
                                'lat': lat if lat else 0,
                                'lon': lon if lon else 0,
                                'unidad': unidad.numero_unidad,
                                'en_servicio': en_servicio
                            }
                        }
                    )
                except Exception as ws_error:
                    print(f"Error WebSocket Web: {ws_error}")

                return JsonResponse({'status': 'ok'})
        except Exception as e:
            print(f"Error actualización web: {e}") 
            return JsonResponse({'status': 'error', 'msg': str(e)})
            
    return JsonResponse({'status': 'error'})

@login_required
def historial_flota(request):
    """Renderiza la tabla con todos los registros de la flota"""
    # Aquí traemos todos los historiales. 
    # (Si tienes un filtro por empresa, aquí usaríamos .filter(bus__flota=request.user.perfil.flota))
    historiales = HistorialTurno.objects.all().select_related('bus', 'conductor')
    
    return render(request, 'flota/historial_flota.html', {
        'historiales': historiales
    })



@login_required
def mantenimiento_flota(request):
    """Panel de Control de Mantenimiento y Documentación Legal"""
    
    # --- 1. GUARDAR DATOS DEL MODAL ---
    if request.method == 'POST':
        unidad_id = request.POST.get('unidad_id')
        unidad = Unidad.objects.get(id=unidad_id)
        
        # Guardar Mecánica
        mecanica, _ = ControlMecanico.objects.get_or_create(unidad=unidad)
        mecanica.vida_aceite = request.POST.get('vida_aceite', 100)
        mecanica.vida_cauchos = request.POST.get('vida_cauchos', 100)
        mecanica.estado_limpieza = request.POST.get('estado_limpieza', 'Limpio')
        mecanica.estado_mecanico = request.POST.get('estado_mecanico', 'Optimo')
        
        # Manejo de fechas vacías
        f_aceite = request.POST.get('fecha_aceite')
        mecanica.fecha_aceite = f_aceite if f_aceite else None
        f_cauchos = request.POST.get('fecha_cauchos')
        mecanica.fecha_cauchos = f_cauchos if f_cauchos else None
        mecanica.save()
        
        # Guardar Legal
        legal, _ = ControlLegal.objects.get_or_create(unidad=unidad)
        legal.pago_alcaldia = request.POST.get('pago_alcaldia', 'Sin registrar')
        v_rcv = request.POST.get('vencimiento_rcv')
        legal.vencimiento_rcv = v_rcv if v_rcv else None
        v_imttv = request.POST.get('vencimiento_imttv')
        legal.vencimiento_imttv = v_imttv if v_imttv else None
        legal.save()
        
        return redirect('mantenimiento_flota')

    # --- 2. MOSTRAR Y FILTRAR ---
    query = request.GET.get('q', '')
    ruta_id = request.GET.get('ruta', '')
    
    # Traemos TODAS las unidades para que el buscador no falle
    unidades = Unidad.objects.all().order_by('numero_unidad')
    rutas_disponibles = Ruta.objects.all() 
    
    # Buscador por nombre de unidad o nombre de ruta
    if query:
        unidades = unidades.filter(
            Q(numero_unidad__icontains=query) | 
            Q(ruta_asignada__nombre__icontains=query)
        ).distinct()
        
    # Filtro selector de Rutas
    if ruta_id:
        unidades = unidades.filter(ruta_asignada__id=ruta_id)
        
    # Generador de registros base automáticos
    for unidad in unidades:
        ControlMecanico.objects.get_or_create(unidad=unidad)
        ControlLegal.objects.get_or_create(unidad=unidad)

    return render(request, 'flota/mantenimiento_flota.html', {
        'unidades': unidades,
        'query': query,
        'ruta_id': ruta_id,
        'rutas': rutas_disponibles
    })

@login_required
def historial_flota(request):
    """Panel para ver el registro de actividad y horas de los choferes"""
    # Traemos todo el historial, garantizando que el más reciente salga de PRIMERO
    historiales = HistorialTurno.objects.all().order_by('-fecha', '-hora_inicio')
    rutas_disponibles = Ruta.objects.all()

    return render(request, 'flota/historial_flota.html', {
        'historiales': historiales,
        'rutas': rutas_disponibles
    })

@login_required
def limpiar_todo_historial(request):
    """Elimina absolutamente todo el historial de la base de datos"""
    if request.method == 'POST':
        from .models import HistorialTurno
        HistorialTurno.objects.all().delete()
        messages.success(request, 'El historial ha sido purgado por completo exitosamente.')
    return redirect('historial_flota')