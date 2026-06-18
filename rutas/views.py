import math
import random
import json
import time
import os
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.views.decorators.csrf import csrf_exempt
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.serializers import serialize
from .models import Parada, Ruta, Patrocinador, AlertaOperativa, Sugerencia, Campana
from flota.models import Unidad  
from usuarios.models import PerfilUsuario
from django.core.mail import send_mail
from django.contrib.auth.models import User 
import threading
from django.db.models import Count
from django.utils import timezone
from datetime import timedelta
from .models import ReporteRapido
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from google import genai
from google.genai import types

\

# Configura tu llave de Gemini (Puedes obtenerla gratis en Google AI Studio)
clave_gemini = os.environ.get("GEMINI_API_KEY", "CLAVE_NO_ENCONTRADA")

# =========================================================
# 1. FUNCIONES SATELITALES Y MATEMÁTICAS (Core)
# =========================================================

def calcular_distancia_segmento_km(lat_bus, lon_bus, lat1, lon1, lat2, lon2):
    """Interpolación matemática para distancias en kilómetros"""
    pasos = 10
    min_dist = float('inf')
    for i in range(pasos + 1):
        frac = i / pasos
        lat_inter = lat1 + (lat2 - lat1) * frac
        lon_inter = lon1 + (lon2 - lon1) * frac
        dist = calcular_distancia_haversine(lat_bus, lon_bus, lat_inter, lon_inter)
        if dist < min_dist: min_dist = dist
    return min_dist

def calcular_distancia_haversine(lat1, lon1, lat2, lon2):
    """Calcula la distancia en kilómetros entre dos coordenadas terrestres"""
    R = 6371.0 # Radio de la Tierra en Km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# =========================================================
# MENÚ PRINCIPAL
# =========================================================
def inicio_general(request):
    perfil = None
    if request.user.is_authenticated:
        perfil, created = PerfilUsuario.objects.get_or_create(usuario=request.user)

    rutas = Ruta.objects.all()
    avisos_generales = AlertaOperativa.objects.filter(activa=True, tipo='general')
    
    # --- FILTRO DE SEGURIDAD PARA ALERTAS EN EL MAPA ---
    if request.user.is_authenticated:
        # 1. Si es Superusuario, Staff o tiene rol de ADMINISTRADOR o ATENCION_CLIENTE, ve TODO
        if request.user.is_superuser or request.user.is_staff or (perfil and perfil.rol in ['ADMINISTRADOR', 'ATENCION_CLIENTE']):
            incidentes_mapa = AlertaOperativa.objects.filter(activa=True).exclude(tipo='general')
        else:
            # 2. Si es un ciudadano común autenticado, solo ve las alertas que él mismo creó
            incidentes_mapa = AlertaOperativa.objects.filter(
                activa=True, 
                usuario_creador=request.user
            ).exclude(tipo='general')
    else:
        # 3. Si el usuario ni siquiera ha iniciado sesión (anónimo), no ve incidentes privados en el mapa
        incidentes_mapa = AlertaOperativa.objects.none()
    # ---------------------------------------------------

    campanas_activas = Campana.objects.filter(activa=True)
    lista_patrocinadores = Patrocinador.objects.all()
    
    todas_paradas = []
    for p in Parada.objects.all():
        todas_paradas.append({
            'id': p.id,
            'lat': float(p.latitud),
            'lon': float(p.longitud),
            'nombre': p.nombre,
            'rutas_asociadas': list(p.rutas.values_list('id', flat=True))
        })

    buses_activos = []
    for u in Unidad.objects.filter(estado__in=['operativa', 'activo']):
        if u.latitud_actual and u.longitud_actual:
            buses_activos.append({
                'id': u.id,
                'lat': float(str(u.latitud_actual).replace(',', '.')),
                'lon': float(str(u.longitud_actual).replace(',', '.')),
                'ruta': u.ruta_asignada.nombre if u.ruta_asignada else 'Desconocida'
            })

    contexto = {
        'perfil': perfil,
        'paradas': Parada.objects.all(),
        'paradas_json': json.dumps(todas_paradas),
        'buses_json': json.dumps(buses_activos), 
        'rutas': rutas,
        'avisos_generales': avisos_generales,
        'incidentes_mapa': incidentes_mapa,
        'campanas': campanas_activas,
        'patrocinadores': lista_patrocinadores 
    }

    return render(request, 'rutas/inicio_general.html', contexto)

@staff_member_required
def panel_admin_amigable(request):
    return render(request, 'rutas/panel_admin.html')

# =========================================================
# 2. VISTAS DEL CIUDADANO (Frontend y Tótems)
# =========================================================

def inicio_peaton(request, parada_id):
    parada = get_object_or_404(Parada, id=parada_id)
    rutas_asociadas = parada.rutas.all()
    
    rutas_data = {}
    tiempo_estimado_default = "--"
    
    for ruta in rutas_asociadas:
        autobus = Unidad.objects.filter(estado__in=['operativa', 'activo'], ruta_asignada=ruta).first()
        eta_ruta = "--"
        
        if autobus and autobus.latitud_actual and autobus.longitud_actual:
            try:
                dist = calcular_distancia_haversine(
                    float(parada.latitud), float(parada.longitud), 
                    float(str(autobus.latitud_actual).replace(',','.')), 
                    float(str(autobus.longitud_actual).replace(',','.'))
                )
                mins = math.ceil((dist / 15.0) * 60)
                if mins < 1: eta_ruta = "Llegando"
                elif mins > 120: eta_ruta = "+2h"
                else: eta_ruta = str(mins)
            except:
                pass

        paradas_ruta = [{'lat': float(p.latitud), 'lon': float(p.longitud), 'nombre': p.nombre} for p in Parada.objects.filter(rutas=ruta)]
        
        trazado_calles = []
        if ruta.trazado and ruta.trazado.strip() not in ["", "[]"]:
            try:
                # Limpiamos posibles comillas simples antes de leer el JSON
                trazado_limpio = str(ruta.trazado).strip().replace("'", '"')
                trazado_calles = json.loads(trazado_limpio)
            except Exception:
                pass
                
        rutas_data[ruta.id] = {
            'nombre': ruta.nombre,
            'paradas': paradas_ruta,
            'trazado': trazado_calles, 
            'eta': eta_ruta
        }
        
        if tiempo_estimado_default == "--" and eta_ruta != "--":
            tiempo_estimado_default = eta_ruta

    todas_paradas = [{'lat': float(p.latitud), 'lon': float(p.longitud), 'nombre': p.nombre} for p in Parada.objects.exclude(id=parada.id)]
    
    patrocinadores = list(Patrocinador.objects.all())
    patrocinador_actual = random.choice(patrocinadores) if patrocinadores else None

    contexto = {
        'parada': parada,
        'tiempo_estimado': tiempo_estimado_default,
        'patrocinador': patrocinador_actual,
        'patrocinadores': patrocinadores,
    
        'rutas_data_json': rutas_data, 
        'todas_paradas_json': todas_paradas,
    }
    return render(request, 'rutas/inicio.html', contexto)

def api_telemetria(request, parada_id):
    parada = get_object_or_404(Parada, id=parada_id)
    rutas_de_parada = parada.rutas.all()
    
    autobus = Unidad.objects.filter(estado__in=['operativa', 'activo'], ruta_asignada__in=rutas_de_parada).first()
    
    tiempo_estimado = "--"
    bus_lat, bus_lon = None, None
    
    if autobus and autobus.latitud_actual and autobus.longitud_actual:
        try:
            bus_lat = float(str(autobus.latitud_actual).replace(',','.'))
            bus_lon = float(str(autobus.longitud_actual).replace(',','.'))
            
            distancia_a_parada = calcular_distancia_haversine(parada.latitud, parada.longitud, bus_lat, bus_lon)
            tiempo_minutos = math.ceil((distancia_a_parada / 25.0) * 60)
            
            if tiempo_minutos < 1: 
                tiempo_estimado = "Llegando"
            elif tiempo_minutos > 120: 
                tiempo_estimado = "+2h"
            else: 
                tiempo_estimado = str(tiempo_minutos)
        except Exception as e:
            print(f"Error calculando telemetría: {e}")
            pass

    return JsonResponse({
        'tiempo_estimado': tiempo_estimado,
        'bus_lat': bus_lat,
        'bus_lon': bus_lon
    })

def registrar_reporte_ciudadano(request, parada_id, tipo_reporte):
    parada = get_object_or_404(Parada, id=parada_id)
    
    if tipo_reporte == 'limpieza':
        parada.reportes_limpieza += 1
    elif tipo_reporte == 'inseguridad':
        parada.reportes_inseguridad += 1
    elif tipo_reporte == 'afluencia':
        parada.reportes_afluencia += 1
        
    parada.save()
    return JsonResponse({
        'status': 'success',
        'limpieza': parada.reportes_limpieza,
        'inseguridad': parada.reportes_inseguridad,
        'afluencia': parada.reportes_afluencia
    })

# =========================================================
# 3. PANEL DE ADMINISTRACIÓN (Vistas CRUD Nivel 3)
# =========================================================

class ParadaListView(ListView):
    model = Parada
    template_name = 'listado_admin.html'
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            'titulo': 'Paradas Virtuales', 'campos': ['Nombre', 'Código'],
            'url_editar': 'editar_parada', 'url_eliminar': 'eliminar_parada'
        })
        return ctx

class ParadaUpdateView(UpdateView):
    model = Parada
    fields = ['nombre', 'latitud', 'longitud', 'referencia', 'tipo', 'estado']
    template_name = 'rutas/formulario_parada_mapa.html'
    success_url = reverse_lazy('listar_paradas')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['rutas'] = Ruta.objects.all()
        context['rutas_seleccionadas'] = self.object.rutas.values_list('id', flat=True)
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        rutas_ids = self.request.POST.getlist('rutas_asociadas')
        self.object.rutas.set(rutas_ids)
        return response

class ParadaDeleteView(DeleteView):
    model = Parada
    template_name = 'confirmar_eliminar.html'
    success_url = reverse_lazy('listar_paradas')

class RutaListView(ListView):
    model = Ruta
    template_name = 'listado_admin.html'
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            'titulo': 'Rutas y Trazados', 'campos': ['Línea', 'ID Registro'],
            'url_editar': 'editar_ruta', 'url_eliminar': 'eliminar_ruta'
        })
        return ctx

class RutaUpdateView(UpdateView):
    model = Ruta
    fields = '__all__'
    template_name = 'formulario_generico.html'
    success_url = reverse_lazy('listar_rutas')
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['titulo'] = '✏️ Editar Ruta'
        return ctx

class RutaDeleteView(DeleteView):
    model = Ruta
    template_name = 'confirmar_eliminar.html'
    success_url = reverse_lazy('listar_rutas')

class PatrocinadorListView(ListView):
    model = Patrocinador
    template_name = 'listado_admin.html'
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            'titulo': 'Patrocinadores', 'campos': ['Comercio', 'ID Registro'],
            'url_editar': 'editar_patrocinador', 'url_eliminar': 'eliminar_patrocinador'
        })
        return ctx

class PatrocinadorCreateView(CreateView):
    model = Patrocinador
    fields = '__all__'
    template_name = 'formulario_generico.html'
    success_url = reverse_lazy('listar_patrocinadores')
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['titulo'] = '🤝 Añadir Patrocinador'
        return ctx

class PatrocinadorUpdateView(UpdateView):
    model = Patrocinador
    fields = '__all__'
    template_name = 'formulario_generico.html'
    success_url = reverse_lazy('listar_patrocinadores')
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['titulo'] = '✏️ Editar Patrocinador'
        return ctx

class PatrocinadorDeleteView(DeleteView):
    model = Patrocinador
    template_name = 'confirmar_eliminar.html'
    success_url = reverse_lazy('listar_patrocinadores')

def resetear_metricas(request, parada_id):
    if request.user.is_staff:
        parada = get_object_or_404(Parada, id=parada_id)
        parada.reportes_limpieza = 0
        parada.reportes_inseguridad = 0
        parada.reportes_afluencia = 0
        parada.save()
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error', 'msg': 'No autorizado'}, status=403)   

@csrf_exempt
def guardar_incidente(request):
    if request.method == 'POST' and request.user.is_staff:
        data = json.loads(request.body)
        AlertaOperativa.objects.create(
            tipo='incidente',
            mensaje=data['descripcion'],
            latitud=data['lat'],
            longitud=data['lng'],
            activa=True
        )
        return JsonResponse({'status': 'ok'})
    return JsonResponse({'status': 'error'}, status=403) 

@csrf_exempt
def resolver_incidente(request, incidente_id):
    if request.method == 'POST' and request.user.is_staff:
        incidente = AlertaOperativa.objects.filter(id=incidente_id).first()
        if incidente:
            incidente.activa = False
            incidente.save()
            return JsonResponse({'status': 'ok'})
    return JsonResponse({'status': 'error'}, status=403)

def gestionar_publicidad(request):
    lista_campanas = Campana.objects.all()
    return render(request, 'rutas/gestionar_publicidad.html', {'campanas': lista_campanas})

def gestionar_usuarios(request):
    from django.contrib.auth.models import User
    return render(request, 'rutas/gestionar_usuarios.html', {'usuarios': User.objects.all()})

@csrf_exempt
def guardar_sugerencia(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            Sugerencia.objects.create(
                tipo=data.get('tipo'),
                sector=data.get('sector'),
                referencia=data.get('referencia', ''),
                detalles=data.get('detalles')
            )
            return JsonResponse({'status': 'ok'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'msg': str(e)}, status=400)
    return JsonResponse({'status': 'error'}, status=405)

@staff_member_required
def gestionar_alertas(request):
    alertas = AlertaOperativa.objects.all().order_by('-fecha_creacion')
    return render(request, 'rutas/gestionar_alertas.html', {'alertas': alertas})

@staff_member_required
def crear_alerta(request):
    if request.method == 'POST':
        tipo = request.POST.get('tipo')
        mensaje = request.POST.get('mensaje')
        latitud = request.POST.get('latitud')
        longitud = request.POST.get('longitud')
        
        AlertaOperativa.objects.create(
            tipo=tipo,
            mensaje=mensaje,
            latitud=latitud if latitud else None,
            longitud=longitud if longitud else None,
            activa=True
        )
        return redirect('gestionar_alertas')
    return render(request, 'rutas/crear_alerta.html')

@staff_member_required
def ver_sugerencias(request):
    sugerencias = Sugerencia.objects.all().order_by('-id')
    return render(request, 'rutas/ver_sugerencias.html', {'sugerencias': sugerencias})

@staff_member_required
def editar_alerta(request, alerta_id):
    alerta = get_object_or_404(AlertaOperativa, id=alerta_id)
    if request.method == 'POST':
        alerta.tipo = request.POST.get('tipo')
        alerta.mensaje = request.POST.get('mensaje')
        alerta.latitud = request.POST.get('latitud') if request.POST.get('latitud') else None
        alerta.longitud = request.POST.get('longitud') if request.POST.get('longitud') else None
        alerta.activa = request.POST.get('activa') == 'on'
        alerta.save()
        return redirect('gestionar_alertas')
    
    return render(request, 'rutas/editar_alerta.html', {'alerta': alerta})

@staff_member_required
def eliminar_alerta(request, alerta_id):
    alerta = get_object_or_404(AlertaOperativa, id=alerta_id)
    alerta.delete()
    return redirect('gestionar_alertas')

@staff_member_required
def eliminar_sugerencia(request, sugerencia_id):
    sugerencia = get_object_or_404(Sugerencia, id=sugerencia_id)
    sugerencia.delete()
    return redirect('ver_sugerencias')

@staff_member_required
def listar_unidades(request):
    unidades = Unidad.objects.all()
    return render(request, 'flota/listar_unidades.html', {'unidades': unidades})  

@staff_member_required
def editar_unidad(request, unidad_id):
    unidad = get_object_or_404(Unidad, id=unidad_id)
    rutas = Ruta.objects.all()

    if request.method == 'POST':
        unidad.placa = request.POST.get('placa')
        unidad.modelo = request.POST.get('modelo')
        
        ruta_id = request.POST.get('ruta_actual')
        unidad.ruta_actual = Ruta.objects.get(id=ruta_id) if ruta_id else None
        unidad.en_servicio = (request.POST.get('en_servicio') == 'on')
        
        unidad.save()
        return redirect('listar_unidades')
    
    return render(request, 'flota/editar_unidad.html', {
        'unidad': unidad,
        'rutas': rutas
    })  

@staff_member_required
def crear_campana(request):
    if request.method == 'POST':
        nombre = request.POST.get('nombre')
        fecha_inicio = request.POST.get('fecha_inicio')
        fecha_fin = request.POST.get('fecha_fin')
        activa = request.POST.get('activa') == 'on'
        
        #  Se captura el archivo que envía el usuario (importante el request.FILES)
        imagen = request.FILES.get('imagen_banner') 
        
        patrocinador_id = request.POST.get('patrocinador')
        patrocinador_obj = None
        if patrocinador_id:
            patrocinador_obj = Patrocinador.objects.filter(id=patrocinador_id).first()

        if nombre and fecha_inicio:
            Campana.objects.create(
                nombre=nombre,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                imagen_banner=imagen,
                activa=activa,
                patrocinador=patrocinador_obj 
            )
            return redirect('gestionar_publicidad') 

    patrocinadores_lista = Patrocinador.objects.all()
    return render(request, 'publicidad/crear_campana.html', {
        'patrocinadores': patrocinadores_lista 
    })

@staff_member_required
def eliminar_campana(request, campana_id):
    if request.method == 'POST':
        campana = get_object_or_404(Campana, id=campana_id)
        campana.delete() 
    return redirect('gestionar_publicidad')

@staff_member_required
def crear_parada(request):
    if request.method == 'POST':
        nombre = request.POST.get('nombre')
        latitud = request.POST.get('latitud')
        longitud = request.POST.get('longitud')
        referencia = request.POST.get('referencia', '')
        tipo = request.POST.get('tipo', 'OFICIAL')
        estado = request.POST.get('estado', 'ACTIVA')
        rutas_ids = request.POST.getlist('rutas_asociadas')

        if nombre and latitud and longitud:
            try:
                nueva_parada = Parada(
                    nombre=nombre, latitud=float(latitud), longitud=float(longitud),
                    referencia=referencia, tipo=tipo, estado=estado
                )
                nueva_parada.save() 
                if rutas_ids:
                    nueva_parada.rutas.set(rutas_ids)
                return redirect('listar_paradas')
            except Exception as e:
                print(f"Error crítico al guardar parada: {e}")
    
    rutas_disponibles = Ruta.objects.all()
    return render(request, 'rutas/crear_parada.html', {'rutas': rutas_disponibles})

@staff_member_required
def crear_ruta(request):
    if request.method == 'POST':
        nombre = request.POST.get('nombre')
        trazado = request.POST.get('trazado') 

        if nombre:
            if not trazado or trazado == "":
                trazado = "[]"
            nueva_ruta = Ruta(nombre=nombre, trazado=trazado, activa=True)
            nueva_ruta.save()
            return redirect('listar_rutas') 
            
    return render(request, 'rutas/formulario_ruta_mapa.html')

def eliminar_unidad(request, unidad_id):
    unidad = get_object_or_404(Unidad, id=unidad_id)
    if request.method == 'POST':
        unidad.delete()
    return redirect('listar_unidades')

def vista_admin_protegida(request):
    if not request.user.is_staff:
        messages.error(request, "⚠️ Acceso denegado: Necesitas una cuenta de Administrador para entrar aquí.")
        return redirect('login')
    
@staff_member_required
def editar_campana(request, campana_id):
    campana = get_object_or_404(Campana, id=campana_id)
    if request.method == 'POST':
        campana.nombre = request.POST.get('nombre')
        campana.fecha_inicio = request.POST.get('fecha_inicio')
        campana.fecha_fin = request.POST.get('fecha_fin')
        campana.activa = 'activa' in request.POST
        
        patrocinador_id = request.POST.get('patrocinador')
        if patrocinador_id:
            campana.patrocinador_id = patrocinador_id
        else:
            campana.patrocinador = None
            
        #  Se captura el archivo si fue modificado
        if 'imagen_banner' in request.FILES:
            campana.imagen_banner = request.FILES['imagen_banner']
        campana.save()
        return redirect('gestionar_publicidad') 
    
    patrocinadores_lista = Patrocinador.objects.all()
    return render(request, 'publicidad/editar_campana.html', {
        'campana': campana,
        'patrocinadores': patrocinadores_lista
    })

# =========================================================
# LÓGICA INTELIGENTE DEL BOTÓN S.O.S. (VERSIÓN PANEL INTERNO)
# =========================================================

def alerta_emergencia(request, parada_id):
   
    if request.method == 'POST':
        parada = get_object_or_404(Parada, id=parada_id)
        
        # 1. Identificar al ciudadano
        ciudadano_nombre = "Un ciudadano anónimo"
        if request.user.is_authenticated:
            ciudadano_nombre = f"{request.user.first_name} {request.user.last_name} ({request.user.username})"

        # 2. Guardar en Base de Datos
        mensaje_sos = f"🚨 PÁNICO S.O.S. activado por {ciudadano_nombre} en la estación: {parada.nombre} (QR: {parada.codigo})"
        
        try:
            AlertaOperativa.objects.create(
                tipo='incidente', 
                mensaje=mensaje_sos, 
                latitud=parada.latitud, 
                longitud=parada.longitud, 
                activa=True
            )
            print("✅ Alerta SOS de parada registrada en BD", flush=True)
        except Exception as e:
            print(f"❌ Error guardando SOS de parada en DB: {e}", flush=True)
            
        # 3. Notificar al usuario
        messages.success(request, "⚠️ ALERTA SOS ENVIADA: Nuestra central ha sido notificada.")
        return redirect('inicio_peaton', parada_id=parada.id)
    
    # Si Chrome o un bot entra a fisgonear por GET, lo devolvemos sin hacer nada
    return redirect('inicio_peaton', parada_id=parada_id)

@csrf_exempt
def actualizar_gps_unidad(request):
    """
    API para recibir las coordenadas en segundo plano desde la App del Chofer.
    Actualizado con WebSockets para desaparecer la unidad al desconectar.
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            # 1. Leer si el chofer sigue transmitiendo o si apagó el botón
            en_servicio = data.get('en_servicio', True) 
            
            # 2. Seguridad básica: Un token secreto para que nadie más envíe datos falsos
            token_recibido = data.get('token')
            token_servidor = "SENALETICA_SECRETO_2026" # En el futuro lo puedes poner en variables de entorno (.env)
            
            # (Si no envías token desde el JS del chofer, puedes comentar el return de abajo)
            if token_recibido and token_recibido != token_servidor:
                return JsonResponse({'error': 'Acceso no autorizado'}, status=401)

            # 3. Extraer los datos del autobús
            unidad_id = data.get('unidad_id')
            lat = data.get('latitud')
            lon = data.get('longitud')

            # Respaldo: Si no viene unidad_id en el JSON, la sacamos del chofer que inició sesión
            if not unidad_id and request.user.is_authenticated:
                unidad_obj = Unidad.objects.filter(conductor=request.user).first()
                if unidad_obj:
                    unidad_id = unidad_obj.id

            if not unidad_id:
                return JsonResponse({'error': 'Faltan datos (unidad_id)'}, status=400)

            # 4. Buscar la unidad en la base de datos y actualizar
            unidad = Unidad.objects.get(id=unidad_id)
            
            if en_servicio:
                unidad.latitud_actual = lat
                unidad.longitud_actual = lon
                unidad.estado = 'operativa'
            else:
                unidad.estado = 'inactiva'
                
            unidad.save()

            # =========================================================
            # 📡 TÚNEL WEBSOCKET: Avisar al Panel que se movió o apagó
            # =========================================================
           
            
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                'mapa_envivo',
                {
                    'type': 'enviar_ubicacion',
                    'datos': {
                        'bus_id': str(unidad.id),
                        'unidad': str(unidad.numero_unidad),
                        'lat': lat if lat else 0,
                        'lon': lon if lon else 0,
                        'en_servicio': en_servicio  # <--- Esta llave le dice al mapa que lo borre
                    }
                }
            )
            # =========================================================

            return JsonResponse({
                'status': 'ok', 
                'msg': f'GPS actualizado para la unidad {unidad_id}'
            })

        except Unidad.DoesNotExist:
            return JsonResponse({'error': 'La unidad especificada no existe'}, status=404)
        except Exception as e:
            return JsonResponse({'error': f'Error interno: {str(e)}'}, status=500)
            
    return JsonResponse({'error': 'Método no permitido. Usa POST.'}, status=405)


@login_required
def panel_estadistico_inteligente(request):
    if not request.user.is_staff:
        return redirect('dashboard_ciudadano')
        
    # ==========================================
    # 1. MÉTRICAS BÁSICAS Y GRÁFICO DE ALERTAS
    # ==========================================
    total_alertas = AlertaOperativa.objects.count()
    alertas_activas = AlertaOperativa.objects.filter(activa=True).count()
    alertas_resueltas = AlertaOperativa.objects.filter(activa=False).count()
    
    conteo_por_tipo = AlertaOperativa.objects.values('tipo').annotate(total=Count('tipo'))
    labels_map = {'general': '📢 Avisos Generales', 'trafico': '🚗 Congestión / Tráfico', 'incidente': '⚠️ Accidentes / Vías Cerradas'}
    
    chart_labels = [labels_map.get(item['tipo'], item['tipo']) for item in conteo_por_tipo]
    chart_data = [item['total'] for item in conteo_por_tipo]

    # ==========================================
    # 2. CAPAS DEL MAPA DE CALOR (DATOS REALES)
    # ==========================================
    
    # Capa Roja: Alertas
    alertas_con_gps = AlertaOperativa.objects.filter(latitud__isnull=False, longitud__isnull=False).exclude(latitud="", longitud="")
    puntos_alertas = []
    for alerta in alertas_con_gps:
        try:
            # Reemplazamos coma por punto para evitar fallos matemáticos
            lat = float(str(alerta.latitud).replace(',', '.'))
            lon = float(str(alerta.longitud).replace(',', '.'))
            puntos_alertas.append([lat, lon, 1.0 if alerta.activa else 0.4])
        except ValueError:
            continue

    # Capa Azul: Buses Activos (Unidades)
    buses_activos = Unidad.objects.filter(estado__in=['operativa', 'activo'], latitud_actual__isnull=False, longitud_actual__isnull=False)
    puntos_buses = []
    for bus in buses_activos:
        try:
            lat = float(str(bus.latitud_actual).replace(',', '.'))
            lon = float(str(bus.longitud_actual).replace(',', '.'))
            puntos_buses.append([lat, lon, 0.9])
        except ValueError:
            continue

    # Capa Verde: Paradas Registradas
    paradas = Parada.objects.filter(latitud__isnull=False, longitud__isnull=False)
    puntos_paradas = []
    for parada in paradas:
        try:
            lat = float(str(parada.latitud).replace(',', '.'))
            lon = float(str(parada.longitud).replace(',', '.'))
            puntos_paradas.append([lat, lon, 0.7])
        except ValueError:
            continue

    # ==========================================
    # 3. GRÁFICOS INFERIORES: RUTAS (REAL)
    # ==========================================
    rutas_conteo = {}
    todas_las_unidades = Unidad.objects.all()
    for u in todas_las_unidades:
        # Buscamos de forma segura a qué ruta pertenece el bus (como lo tienes en tu código)
        ruta_obj = getattr(u, 'ruta', getattr(u, 'ruta_asignada', None))
        if ruta_obj:
            rutas_conteo[ruta_obj.nombre] = rutas_conteo.get(ruta_obj.nombre, 0) + 1

    rutas_labels = list(rutas_conteo.keys())
    rutas_data = list(rutas_conteo.values())

# ==========================================
    # 4. GRÁFICOS INFERIORES: PARADAS (DATOS REALES)
    # ==========================================
    # Ordenamos las paradas de mayor a menor según sus reportes de afluencia 
    # y tomamos solo el Top 5 para no saturar el gráfico
    top_paradas = Parada.objects.all().order_by('-reportes_afluencia')[:5]
    
    paradas_labels = [p.nombre for p in top_paradas]
    paradas_data = [p.reportes_afluencia for p in top_paradas]
            
    contexto = {
        'total_alertas': total_alertas, 'alertas_activas': alertas_activas, 'alertas_resueltas': alertas_resueltas,
        'chart_labels': json.dumps(chart_labels), 'chart_data': json.dumps(chart_data),
        
        # Las 3 capas reales para el mapa:
        'puntos_alertas_json': json.dumps(puntos_alertas),
        'puntos_buses_json': json.dumps(puntos_buses),
        'puntos_paradas_json': json.dumps(puntos_paradas),
        
        'rutas_labels': json.dumps(rutas_labels), 'rutas_data': json.dumps(rutas_data),
        
        # Aquí inyectamos los datos reales de la demanda
        'paradas_labels': json.dumps(paradas_labels), 'paradas_data': json.dumps(paradas_data),
    }
    return render(request, 'panel_estadistico.html', contexto)

@csrf_exempt # Quitamos el @login_required de aquí arriba
def registrar_reporte_waze(request):
    if request.method == 'POST':
        # Validación elegante para AJAX: Si no ha iniciado sesión, le avisamos
        if not request.user.is_authenticated:
            return JsonResponse({'status': 'error', 'msg': 'Debes iniciar sesión para ayudar con reportes comunitarios.'})

        try:
            data = json.loads(request.body)
            tipo_reporte = data.get('tipo')
            ruta_id = data.get('ruta_id')
            parada_id = data.get('parada_id')

            ruta_obj = Ruta.objects.filter(id=ruta_id).first() if ruta_id else None
            parada_obj = Parada.objects.filter(id=parada_id).first() if parada_id else None

            # 1. Guardamos el reporte
            ReporteRapido.objects.create(
                usuario=request.user,
                tipo=tipo_reporte,
                ruta=ruta_obj,
                parada=parada_obj
            )

            # 2. Lógica Waze (3 reportes en 15 min)
            hace_15_minutos = timezone.now() - timedelta(minutes=15)
            conteo_reportes = ReporteRapido.objects.filter(
                tipo=tipo_reporte,
                ruta=ruta_obj,
                parada=parada_obj,
                fecha_creacion__gte=hace_15_minutos
            ).count()

            # 3. Disparo de Alerta Global
            if conteo_reportes >= 3:
                mensaje_alerta = ""
                tipo_alerta_global = "trafico"

                if tipo_reporte == 'bus_lleno' and ruta_obj:
                    mensaje_alerta = f"⚠️ Comunidad reporta: Unidades de la {ruta_obj.nombre} se encuentran saturadas (Buses llenos)."
                elif tipo_reporte == 'trafico' and ruta_obj:
                    mensaje_alerta = f"🚗 Retraso vial crítico detectado en el trayecto de la {ruta_obj.nombre}."
                elif tipo_reporte == 'parada_sucia' and parada_obj:
                    tipo_alerta_global = "general"
                    mensaje_alerta = f"📢 Reporte de mantenimiento: Incidencias en la infraestructura de la {parada_obj.nombre}."

                if mensaje_alerta:
                    alerta_existente = AlertaOperativa.objects.filter(mensaje=mensaje_alerta, activa=True).exists()
                    if not alerta_existente:
                        AlertaOperativa.objects.create(tipo=tipo_alerta_global, mensaje=mensaje_alerta, activa=True)

            return JsonResponse({'status': 'ok', 'msg': 'Reporte procesado por la comunidad.'})
        
        except Exception as e:
            # Si hay un error interno de base de datos, lo enviamos al frontend para saber qué pasó
            return JsonResponse({'status': 'error', 'msg': f'Error del servidor: {str(e)}'})
            
    return JsonResponse({'status': 'error', 'msg': 'Método no permitido'})

@login_required
def buzon_reportes(request):
    """Bandeja de entrada para que el administrador lea el feedback de la comunidad"""
    # Seguridad: Solo personal autorizado
    if not request.user.is_staff:
        return redirect('dashboard_ciudadano')
        
    # Traemos todos los reportes ordenados por fecha (los más recientes primero)
    # Seleccionamos también las rutas y paradas relacionadas para que la base de datos no se sature
    reportes = ReporteRapido.objects.select_related('usuario', 'ruta', 'parada').all().order_by('-fecha_creacion')
    
    return render(request, 'buzon_reportes.html', {'reportes': reportes})   

@login_required
def eliminar_reporte_waze(request, reporte_id):
    """Elimina un solo reporte del radar comunitario"""
    if not request.user.is_staff:
        return redirect('dashboard_ciudadano')
        
    if request.method == 'POST':
        reporte = get_object_or_404(ReporteRapido, id=reporte_id)
        reporte.delete()
        messages.success(request, "Reporte eliminado correctamente.")
        
    return redirect('buzon_reportes')

@login_required
def limpiar_buzon_waze(request):
    """Vacia por completo la tabla de reportes rápidos"""
    if not request.user.is_staff:
        return redirect('dashboard_ciudadano')
        
    if request.method == 'POST':
        ReporteRapido.objects.all().delete()
        messages.success(request, "El buzón ha sido limpiado por completo.")
        
    return redirect('buzon_reportes') 

@csrf_exempt
def operador_inteligente_api(request):
    """API que conecta el chat ciudadano con la IA de Gemini utilizando el SDK moderno"""
    if request.method == 'POST':
        try:
            # 1. Parseamos el mensaje del usuario
            data = json.loads(request.body)
            mensaje_usuario = data.get('mensaje', '')

            # 2. Obtenemos la clave desde las variables de entorno
            clave_gemini = os.environ.get("GEMINI_API_KEY")
            
            if not clave_gemini:
                return JsonResponse({'status': 'error', 'respuesta': 'Error de configuración en el servidor.'})

            # 3. Inicializamos el cliente con la nueva librería
            client = genai.Client(api_key=clave_gemini)

            # 4. Definimos el contexto/personalidad del Operador Inteligente
            contexto_sistema = """
            Eres el 'Operador Inteligente' del sistema de transporte Señal Ética + en Ciudad Guayana (Puerto Ordaz y San Félix).
            
            Tus funciones y reglas de comportamiento son estrictamente las siguientes:
            1. Tono de voz: Sé sumamente empático, paciente, amable y servicial. Actúa como un operador local con mucha calidez humana.
            2. Guía de Movilidad y Turismo Local: Orienta sobre rutas de transporte para llegar a restaurantes, centros comerciales, parques (La Llovizna, Cachamay) y lugares populares del Municipio Caroní.
            3. Universidades: Limita la información universitaria a lo básico (qué ruta tomar para llegar a la UNEG, UCAB, UNEXPO, etc.). No des asesoría académica.
            4. Regla estricta sobre el clima: Puedes dar consejos generales por el calor o la lluvia. TIENES PROHIBIDO sugerir a los usuarios que se resguarden en las paradas de autobús, ya que no cuentan con techo.
            5. Seguridad: Si el usuario reporta una emergencia o inseguridad, indícale con calma que utilice el botón rojo de 'S.O.S. Emergencia' disponible en el tótem o la app.
            6. Formato: Mantén tus respuestas breves, precisas y fáciles de leer rápidamente en una pantalla en la calle.
            """

            # 5. Generamos la respuesta con el modelo moderno
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=mensaje_usuario,
                config=types.GenerateContentConfig(
                    system_instruction=contexto_sistema,
                    temperature=0.7 # Un poco de creatividad para que suene más humano
                )
            )
            
            return JsonResponse({'status': 'ok', 'respuesta': response.text})

        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                return JsonResponse({
                    'status': 'error', 
                    'respuesta': 'Estamos teniendo muchas consultas ahora mismo. Por favor, espera unos segundos y vuelve a preguntar.'
                })
            print(f"Error en Gemini API: {e}")
            return JsonResponse({
                'status': 'error', 
                'respuesta': 'Disculpa, el operador está descansando un momento. Intenta de nuevo.'
            })
   