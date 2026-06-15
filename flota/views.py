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

# NUEVAS IMPORTACIONES PARA EL DISPARADOR WEBSOCKET
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

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
    """Recibe la ubicación de la App Móvil o la orden de apagado."""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            # 1. Seguridad
            if data.get('token') != "SENALETICA_SECRETO_2026":
                return JsonResponse({'error': 'No autorizado'}, status=403)
                
            unidad_id = data.get('unidad_id')
            unidad = Unidad.objects.filter(numero_unidad=unidad_id).first()
            if not unidad:
                return JsonResponse({'error': 'Unidad no encontrada'}, status=404)

            # ==========================================================
            # EL APAGADOR: Forzamos el estado a 'inactiva'
            # ==========================================================
            if data.get('estado') == 'inactivo':
                unidad.estado = 'inactiva' 
                unidad.save()
                return JsonResponse({'status': 'Bus desconectado del mapa'})

            # ==========================================================
            # SI ESTÁ TRANSMITIENDO: Actualiza coordenadas y fuerza a 'operativa'
            # ==========================================================
            lat = data.get('latitud', data.get('lat'))
            lon = data.get('longitud', data.get('lon'))
            
            if lat and lon:
                unidad.latitud_actual = lat
                unidad.longitud_actual = lon
                unidad.estado = 'operativa' 
                unidad.ultima_actualizacion = timezone.now()
                unidad.save()

                # ----------------------------------------------------
                # AQUI ESTÁ EL DISPARADOR N°1 (Para la App Móvil)
                # ----------------------------------------------------
                try:
                    channel_layer = get_channel_layer()
                    async_to_sync(channel_layer.group_send)(
                        'mapa_envivo', # El nombre de la sala que pusimos en consumers.py
                        {
                            'type': 'enviar_ubicacion',
                            'datos': {
                                'bus_id': str(unidad.id), 
                                'lat': lat,
                                'lon': lon,
                                'unidad': unidad.numero_unidad
                            }
                        }
                    )
                except Exception as ws_error:
                    print(f"Error en WebSocket (App): {ws_error}")
                # ----------------------------------------------------

                return JsonResponse({'status': 'ok', 'msg': 'GPS actualizado'})
                
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
    """Recibe el GPS desde el panel web del chofer y registra el tiempo trabajado"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            lat = data.get('latitud')
            lon = data.get('longitud')
            en_servicio = data.get('en_servicio') 

            unidad = Unidad.objects.filter(conductor=request.user).first()
            if unidad:
                if lat and lon and lat != 0:
                    unidad.latitud_actual = lat
                    unidad.longitud_actual = lon
                
                if en_servicio:
                    unidad.estado = 'operativa'
                    sesion_abierta = RegistroSesion.objects.filter(unidad=unidad, hora_fin__isnull=True).first()
                    if not sesion_abierta:
                        RegistroSesion.objects.create(unidad=unidad)
                else:
                    unidad.estado = 'inactiva'
                    sesion_abierta = RegistroSesion.objects.filter(unidad=unidad, hora_fin__isnull=True).first()
                    if sesion_abierta:
                        sesion_abierta.hora_fin = timezone.now()
                        sesion_abierta.save()
                
                unidad.ultima_actualizacion = timezone.now()
                unidad.save()

                # ----------------------------------------------------
                # AQUI ESTÁ EL DISPARADOR N°2 (Para el Panel Web del Chofer)
                # ----------------------------------------------------
                if en_servicio and lat and lon:
                    try:
                        channel_layer = get_channel_layer()
                        async_to_sync(channel_layer.group_send)(
                            'mapa_envivo',
                            {
                                'type': 'enviar_ubicacion',
                                'datos': {
                                    'bus_id': str(unidad.id),
                                    'lat': lat,
                                    'lon': lon,
                                    'unidad': unidad.numero_unidad
                                }
                            }
                        )
                    except Exception as ws_error:
                        print(f"Error en WebSocket (Web): {ws_error}")
                # ----------------------------------------------------

                return JsonResponse({'status': 'ok'})
        except Exception as e:
            print(f"Error en actualización web de chofer: {e}") 
            pass
            
    return JsonResponse({'status': 'error'})