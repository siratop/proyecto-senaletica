import math
import random
import json
import time
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
    incidentes_mapa = AlertaOperativa.objects.filter(activa=True).exclude(tipo='general')
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

    return render(request, 'rutas/inicio_general.html', {
        'perfil': perfil,
        'paradas': Parada.objects.all(),
        'paradas_json': json.dumps(todas_paradas),
        'buses_json': json.dumps(buses_activos), 
        'rutas': rutas,
        'avisos_generales': avisos_generales,
        'incidentes_mapa': incidentes_mapa,
        'campanas': campanas_activas,
        'patrocinadores': lista_patrocinadores 
    })

@staff_member_required
def panel_admin_amigable(request):
    return render(request, 'rutas/panel_admin.html')

# =========================================================
# 2. VISTAS DEL CIUDADANO (Frontend y Tótems)
# =========================================================

def inicio_peaton(request, parada_id):
    parada = get_object_or_404(Parada, id=parada_id)
    rutas_asociadas = Ruta.objects.all()
    
    rutas_data = {}
    tiempo_estimado_default = "--"
    
    for ruta in rutas_asociadas:
        autobus = Unidad.objects.filter(estado__in=['operativa', 'activo'], ruta_asignada=ruta).first()
        eta_ruta = "--"
        
        if autobus and autobus.latitud_actual and autobus.longitud_actual:
            try:
                dist = calcular_distancia_haversine(
                    parada.latitud, parada.longitud, 
                    float(str(autobus.latitud_actual).replace(',','.')), 
                    float(str(autobus.longitud_actual).replace(',','.'))
                )
                mins = math.ceil((dist / 25.0) * 60)
                if mins < 1: eta_ruta = "Llegando"
                elif mins > 120: eta_ruta = "+2h"
                else: eta_ruta = str(mins)
            except:
                pass

        paradas_ruta = [{'lat': float(p.latitud), 'lon': float(p.longitud), 'nombre': p.nombre} for p in Parada.objects.filter(rutas=ruta)]
        
        trazado_calles = []
        if ruta.trazado and ruta.trazado != "[]" and ruta.trazado.strip() != "":
            try:
                trazado_calles = json.loads(ruta.trazado)
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

    todas_paradas = []
    for p in Parada.objects.exclude(id=parada.id): 
        todas_paradas.append({
            'lat': float(p.latitud),
            'lon': float(p.longitud),
            'nombre': p.nombre
        })

    patrocinadores = list(Patrocinador.objects.all())
    patrocinador_actual = random.choice(patrocinadores) if patrocinadores else None

    contexto = {
        'parada': parada,
        'tiempo_estimado': tiempo_estimado_default,
        'patrocinador': patrocinador_actual,
        'patrocinadores': patrocinadores,
        'rutas_data_json': json.dumps(rutas_data), 
        'todas_paradas_json': json.dumps(todas_paradas),
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
# LÓGICA INTELIGENTE DEL BOTÓN S.O.S.
# =========================================================
def alerta_emergencia(request, parada_id):
    parada = get_object_or_404(Parada, id=parada_id)
    
    # 1. Preparar la lista de destinatarios dinámicamente
    destinatarios = []
    
    # A) Correos de los Administradores (El sistema de control)
    admins = User.objects.filter(is_staff=True, email__isnull=False).exclude(email='')
    for admin in admins:
        destinatarios.append(admin.email)
        
    # B) Correo de emergencia del Ciudadano (El familiar del NFC)
    ciudadano_nombre = "Un ciudadano anónimo"
    if request.user.is_authenticated:
        ciudadano_nombre = f"{request.user.first_name} {request.user.last_name} ({request.user.username})"
        try:
            # Traemos el correo que el usuario guardó al crear su NFC
            correo_familiar = request.user.perfil.correo_emergencia
            if correo_familiar:
                destinatarios.append(correo_familiar)
        except Exception:
            pass 
            
    # Protección por si nadie tiene correo configurado
    if not destinatarios:
        destinatarios = ['seguridad_respaldo@senaletica.com']
        
    # 2. Armar un mensaje profesional con enlace a Google Maps
    asunto = f"🚨 EMERGENCIA SOS - Tótem: {parada.nombre}"
    enlace_maps = f"https://www.google.com/maps?q={parada.latitud},{parada.longitud}"
    
    mensaje = f"""
    SE HA ACTIVADO EL BOTÓN DE PÁNICO EN LA RED SEÑALÉTICA+.
    
    👤 Usuario en peligro: {ciudadano_nombre}
    
    📍 Ubicación del Incidente:
    Parada: {parada.nombre}
    Código QR: {parada.codigo}
    
    🗺️ Ver en el mapa (Rastreo GPS):
    {enlace_maps}
    
    Por favor, comuníquese con el usuario o envíe asistencia de inmediato.
    """
    
    #  el correo "robot" de tu sistema (r configurarlo en settings.py)
    remitente = 'francisco.fonseca.farias@gmail.com' 
    
    # 3. Disparar el correo
    try:
        send_mail(asunto, mensaje, remitente, destinatarios, fail_silently=False)
        messages.success(request, "⚠️ ALERTA SOS ENVIADA: Las autoridades y sus contactos de emergencia han sido notificados con su ubicación GPS.")
    except Exception as e:
        print(f"Error de envío: {e}")
        messages.error(request, "Error de red local: La alerta se guardó en la central, pero el envío del correo falló.")

    # Redirigir de vuelta a la parada
    return redirect('inicio_peaton', parada_id=parada.id)