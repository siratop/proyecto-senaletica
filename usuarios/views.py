from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required
from django.views.generic import CreateView, ListView, UpdateView, DeleteView
from django.urls import reverse_lazy
import datetime
from django.contrib.admin.views.decorators import staff_member_required
from rutas.models import AlertaOperativa
from rutas.models import Sugerencia
from .models import Dependiente, RegistroActividad, TarjetaNFC, PerfilUsuario, SolicitudOperador
from .forms import RegistroInclusivoForm
from django.utils import timezone
from datetime import timedelta
from django.contrib import messages
from django.contrib.auth import logout
from django.db import IntegrityError 
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from .models import Dependiente, PerfilUsuario
from django.db.models import Q
from .models import TicketSoporte
from flota.models import SuscripcionTelegram
import requests
from django.http import HttpResponse
try:
    from rutas.models import AlertaOperativa
except ImportError:
    AlertaOperativa = None

# =========================================================
# 1. REGISTRO Y GESTIÓN DE CUENTAS
# =========================================================
TELEGRAM_TOKEN = "8830888723:AAF_iLtjGOpNN2muaE-4v9fxYnUceD0MXkU"

class SignUpView(CreateView):
    """Vista pública para que un ciudadano se registre"""
    model = User
    form_class = RegistroInclusivoForm  
    template_name = 'formulario_generico.html'
    success_url = reverse_lazy('login')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo'] = '📱 Registro de Ciudadano'
        context['subtitulo'] = 'Crea tu cuenta segura para gestionar pulseras NFC y reportes viales.'
        return context

class PerfilUsuarioCreateView(CreateView):
    """Vista para que el administrador cree cuentas desde el panel"""
    model = User
    form_class = RegistroInclusivoForm  
    template_name = 'formulario_generico.html'
    success_url = reverse_lazy('listar_usuarios')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo'] = '➕ Registrar Nueva Cuenta (Admin)'
        context['subtitulo'] = 'Creación de un nuevo perfil base con contraseña encriptada.'
        return context


# =========================================================
# 2. PANEL DEL CIUDADANO (NIVEL 1) Y CONTROL PARENTAL
# =========================================================
@login_required
def dashboard_ciudadano(request):
    """Panel de Control Nivel 1: El ciudadano gestiona su cuenta y pulseras NFC"""
    mis_dependientes = Dependiente.objects.filter(tutor=request.user)
    
    # LA MAGIA: Buscamos alertas creadas por el usuario (tráfico, etc) 
    # O (|) alertas que pertenezcan a los dependientes de este usuario (SOS NFC)
    mis_reportes = AlertaOperativa.objects.filter(
        Q(usuario_creador=request.user) | Q(dependiente__tutor=request.user)
    ).order_by('-fecha_creacion')

    contexto = {
        'dependientes': mis_dependientes,
        'reportes': mis_reportes
    }
    return render(request, 'usuarios/dashboard_ciudadano.html', contexto)

class DependienteCreateView(CreateView):
    """Formulario para añadir un niño o adulto mayor al núcleo familiar"""
    model = Dependiente
    fields = ['nombre_completo', 'relacion', 'condicion_medica', 'telefono_emergencia']
    template_name = 'formulario_generico.html'
    success_url = reverse_lazy('dashboard_ciudadano')

    def form_valid(self, form):
        form.instance.tutor = self.request.user
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo'] = '➕ Registrar Miembro Familiar'
        context['subtitulo'] = 'Configure los datos médicos y genere su enlace criptográfico NFC.'
        return context


def ficha_sos_publica(request, token_nfc):
    """Pantalla pública de asistencia para personas extraviadas (NFC) - SIN CORREO"""
    dependiente = get_object_or_404(Dependiente, token_nfc=token_nfc)
    
    from rutas.models import AlertaOperativa  
    
    tutor_nombre = f"{dependiente.tutor.first_name} {dependiente.tutor.last_name}".strip() or dependiente.tutor.username
    
    mensaje_sos = (
        f"🚨 INCIDENTE NFC: Se ha escaneado la pulsera de {dependiente.nombre_completo}. "
        f"Parentesco: {dependiente.get_relacion_display()}. "
        f"Representante: {tutor_nombre}. "
        f"Teléfono de Contacto: {dependiente.telefono_emergencia}."
    )
    
    alerta_id = None 
    
    try:
        alerta_creada = AlertaOperativa.objects.create(
            tipo='incidente',
            mensaje=mensaje_sos,
            dependiente=dependiente, 
            activa=True,
            latitud=0.0,
            longitud=0.0
        )
        alerta_id = alerta_creada.id 
        print(f"✅ Alerta SOS registrada (ID: {alerta_id}). (Módulo de correo desactivado)", flush=True)

        # =========================================================
        # 🚀 AVISO TELEGRAM: LECTURA DE TARJETA NFC
        # =========================================================
        try:
            # Buscamos si el tutor de este dependiente tiene Telegram vinculado
            suscripcion = SuscripcionTelegram.objects.filter(usuario=dependiente.tutor, activo=True).first()
            
            if suscripcion and suscripcion.chat_id:
                mensaje_nfc = (
                    f"🚨 ¡ALERTA DE SEGURIDAD NFC!\n\n"
                    f"Se acaba de escanear la pulsera de emergencia de *{dependiente.nombre_completo}*.\n\n"
                    f"📅 Fecha: {timezone.now().strftime('%d/%m/%Y %I:%M %p')}\n"
                    f"⚠️ Ingrese a su panel de control para ver los detalles del reporte."
                )
                
                url_telegram = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                requests.post(url_telegram, json={'chat_id': suscripcion.chat_id, 'text': mensaje_nfc, 'parse_mode': 'Markdown'})
                print("✅ Notificación NFC enviada por Telegram exitosamente.")
        except Exception as e:
            print(f"❌ Error enviando aviso Telegram por NFC: {e}")
        # =========================================================

    except Exception as e:
        print(f"❌ ERROR AL CREAR ALERTA SOS: {e}", flush=True)

    contexto = {
        'dependiente': dependiente,
        'alerta_id': alerta_id  
    }
    return render(request, 'usuarios/ficha_sos_publica.html', contexto)


# =========================================================
# 3. CRUD ADMINISTRATIVO (Para el panel de control)
# =========================================================

class PerfilUsuarioListView(ListView):
    """Listado general de usuarios para el administrador"""
    model = User
    template_name = 'listado_admin.html'
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            'titulo': 'Cuentas Base', 
            'campos': ['Usuario Registrado', 'Rol de Sistema'],
            'url_editar': 'editar_usuario', 
            'url_eliminar': 'eliminar_usuario'
        })
        return ctx

class UsuarioUpdateView(UpdateView):
    """Edición de una cuenta de usuario existente y su Rol de Perfil"""
    model = User
    fields = ['username', 'email', 'first_name', 'last_name']
    template_name = 'formulario_generico.html'
    success_url = reverse_lazy('listar_usuarios')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo'] = '✏️ Editar Cuenta y Rol de Usuario'
        context['roles_disponibles'] = PerfilUsuario._meta.get_field('rol').choices
        
        perfil, created = PerfilUsuario.objects.get_or_create(usuario=self.object)
        context['rol_actual'] = perfil.rol
        return context

    def form_valid(self, form):
        usuario = form.save(commit=False)
        nuevo_rol = self.request.POST.get('rol_usuario')
        
        if nuevo_rol:
            perfil, created = PerfilUsuario.objects.get_or_create(usuario=usuario)
            perfil.rol = nuevo_rol
            perfil.save()
            
            if nuevo_rol == 'soporte':
                usuario.is_staff = True
            else:
                usuario.is_staff = False
                
        usuario.save()
        messages.success(self.request, f"La cuenta de {usuario.username} y su rol han sido actualizados.")
        return super().form_valid(form)

class UsuarioDeleteView(DeleteView):
    """Eliminación segura de un usuario"""
    model = User
    template_name = 'confirmar_eliminar.html'
    success_url = reverse_lazy('listar_usuarios')

@staff_member_required
def edicion_avanzada_usuarios(request):
    """Vista para listar y editar usuarios con permisos avanzados"""
    usuarios = User.objects.all()
    return render(request, 'usuarios/edicion_avanzada.html', {'usuarios': usuarios})

@staff_member_required
def asignar_nfc(request):
    """Vista para el formulario de vinculación de tarjetas NFC"""
    dependientes = Dependiente.objects.all().select_related('tutor')
    return render(request, 'usuarios/asignar_nfc.html', {'dependientes': dependientes})

@staff_member_required
def auditoria_nfc(request):
    tarjetas = TarjetaNFC.objects.all().order_by('-fecha_creacion')
    return render(request, 'usuarios/auditoria_nfc.html', {'tarjetas_nfc': tarjetas})

@staff_member_required
def ficha_monitoreo_usuario(request, user_id):
    usuario = get_object_or_404(User, id=user_id)
    logs = RegistroActividad.objects.filter(user=usuario).order_by('-fecha')
    
    contexto = {
        'usuario': usuario,
        'logs': logs,
        'total_escaneos': logs.filter(accion__contains="Escaneo").count()
    }
    return render(request, 'usuarios/ficha_monitoreo.html', contexto)


@staff_member_required
def guardar_nfc(request):
    if request.method == 'POST':
        usuario_id = request.POST.get('usuario_id')
        codigo_nfc = request.POST.get('codigo_nfc')
        
        if not usuario_id or not codigo_nfc:
            messages.error(request, "Error: Debe seleccionar un usuario y colocar un código NFC.")
            return redirect('asignar_nfc')
            
        try:
            usuario = User.objects.get(id=usuario_id)
            
            if hasattr(usuario, 'tarjetanfc'):
                usuario.tarjetanfc.codigo_uid = codigo_nfc
                usuario.tarjetanfc.activa = True
                usuario.tarjetanfc.save()
                messages.success(request, f"Tarjeta NFC de {usuario.username} actualizada correctamente.")
            else:
                TarjetaNFC.objects.create(usuario=usuario, codigo_uid=codigo_nfc, activa=True)
                messages.success(request, f"Tarjeta NFC vinculada a {usuario.username} con éxito.")
                
        except User.DoesNotExist:
            messages.error(request, "Error: El usuario seleccionado no existe en el sistema.")
        except IntegrityError:
            messages.error(request, "Error crítico: El código o enlace NFC ya está asignado a otro usuario distinto.")
        except Exception as e:
            print(f"Error unexpected al guardar NFC: {e}")
            messages.error(request, "Error interno al procesar la vinculación NFC.")
            
    return redirect('asignar_nfc')

@login_required
def mi_perfil(request):
    perfil, created = PerfilUsuario.objects.get_or_create(usuario=request.user)
    
    # --- LÓGICA DE TELEGRAM AÑADIDA ---
    # Buscamos o creamos el código secreto de vinculación para este usuario
    from flota.models import SuscripcionTelegram
    suscripcion, created_sub = SuscripcionTelegram.objects.get_or_create(usuario=request.user)
    
    puede_editar = True
    dias_restantes = 0
    if perfil.ultima_modificacion:
        tiempo_pasado = timezone.now() - perfil.ultima_modificacion
        if tiempo_pasado.days < 7:
            puede_editar = False
            dias_restantes = 7 - tiempo_pasado.days

    dias_restantes_flota = 0
    if perfil.rol == 'flota' and not perfil.puede_cambiar_nombre():
        dias_pasados = (timezone.now() - perfil.fecha_cambio_nombre).days
        dias_restantes_flota = 30 - dias_pasados

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'update_data' and puede_editar:
            user = request.user
            user.first_name = request.POST.get('nombre')
            user.last_name = request.POST.get('apellido')
            user.email = request.POST.get('email')
            user.save()
            
            perfil.telefono = request.POST.get('telefono')
            perfil.ultima_modificacion = timezone.now()
            perfil.save()
            
            messages.success(request, "Datos actualizados correctamente. Por seguridad, no podrá modificarlos de nuevo hasta dentro de 7 días.")
            return redirect('mi_perfil')

        elif request.POST.get('guardar_flota'):
            if perfil.rol == 'flota':
                perfil.telefono = request.POST.get('telefono_flota')
                
                if perfil.puede_cambiar_nombre():
                    perfil.nombre_flota = request.POST.get('nombre_flota')
                    perfil.fecha_cambio_nombre = timezone.now()
                    messages.success(request, "Datos de la flota actualizados. El nombre de la empresa ha sido bloqueado por 30 días.")
                else:
                    messages.success(request, "Teléfono de contacto de la flota actualizado. (El nombre comercial sigue bloqueado).")
                
                perfil.save()
            return redirect('mi_perfil')

        elif action == 'solicitud_empleo':
            SolicitudOperador.objects.create(
                usuario=request.user,
                telefono_contacto=request.POST.get('telefono_contacto'),
                experiencia_anios=request.POST.get('experiencia'),
                tipo_licencia=request.POST.get('licencia'),
                mensaje=request.POST.get('mensaje')
            )
            messages.success(request, "¡Su solicitud ha sido enviada al departamento de transporte! Lo contactaremos pronto.")
            return redirect('mi_perfil')

        elif action == 'eliminar_cuenta':
            user = request.user
            logout(request)
            user.delete()
            return redirect('login') 

    # --- NUEVO: Buscamos los tickets de soporte del usuario ---
    tickets_usuario = TicketSoporte.objects.filter(usuario=request.user).order_by('-fecha_creacion')

    # --- ACTUALIZADO: Pasamos las variables al HTML ---
    return render(request, 'usuarios/mi_perfil.html', {
        'perfil': perfil,
        'puede_editar': puede_editar,
        'dias_restantes': dias_restantes,
        'dias_restantes_flota': dias_restantes_flota,
        'tickets': tickets_usuario,
        'suscripcion': suscripcion  # <--- Pasamos la suscripción aquí
    })

# =========================================================
# 4. MONITOR DE EMERGENCIAS Y CENTRAL DE SERVICIO AL CLIENTE
# =========================================================

@login_required
def panel_servicio_cliente(request):
    """Panel Exclusivo para Operadores / Servicio al Cliente y usuarios con reportes"""
    
    # 1. Obtenemos el perfil para verificar su rol
    from usuarios.models import PerfilUsuario
    perfil, created = PerfilUsuario.objects.get_or_create(usuario=request.user)
    
    from rutas.models import AlertaOperativa
    
   
    if request.user.is_staff or perfil.rol == 'soporte':
        alertas_activas = AlertaOperativa.objects.filter(activa=True).order_by('-id')
        alertas_historial = AlertaOperativa.objects.filter(activa=False).order_by('-id')[:50]
    else:
        # Filtramos por el usuario que creó la alerta
        alertas_activas = AlertaOperativa.objects.filter(activa=True, usuario_creador=request.user).order_by('-id')
        alertas_historial = AlertaOperativa.objects.filter(activa=False, usuario_creador=request.user).order_by('-id')[:20]

    contexto = {
        'alertas_activas': alertas_activas,
        'alertas_historial': alertas_historial,
    }
    return render(request, 'usuarios/panel_servicio_cliente.html', contexto)


@login_required
def gestionar_alerta_sos(request, alerta_id, accion):
    """Permite al Operador solucionar o eliminar una emergencia"""
    if not request.user.is_staff:
        return redirect('dashboard_ciudadano')

    from rutas.models import AlertaOperativa
    alerta = get_object_or_404(AlertaOperativa, id=alerta_id)

    if accion == 'resolver':
        alerta.activa = False
        alerta.save()
        
        # MAGIA: Detectamos si la alerta tiene una persona asignada o si viene de una parada
        if alerta.dependiente:
            nombre = alerta.dependiente.nombre_completo
        else:
            nombre = "la estación/parada"
            
        messages.success(request, f"¡Emergencia de {nombre} marcada como Resuelta!")
        
    elif accion == 'eliminar':
        alerta.delete()
        messages.success(request, "El registro de la alerta ha sido eliminado.")

    return redirect('panel_servicio_cliente')


@csrf_exempt
def actualizar_gps_alerta(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            alerta_id = data.get('alerta_id')
            lat = data.get('lat')
            lon = data.get('lon')

           
            print(f"DEBUG: Recibiendo GPS -> ID: {alerta_id}, Lat: {lat}, Lon: {lon}", flush=True)

            if alerta_id and lat and lon:
                from rutas.models import AlertaOperativa
               
                alerta = AlertaOperativa.objects.get(id=int(alerta_id))
                alerta.latitud = float(lat)
                alerta.longitud = float(lon)
                alerta.save()
                return JsonResponse({'status': 'ok'})
            return JsonResponse({'status': 'error', 'msg': 'Faltan datos'}, status=400)
        except Exception as e:
            print(f"Error en GPS: {e}", flush=True)
            return JsonResponse({'status': 'error', 'msg': str(e)}, status=400)
    return JsonResponse({'status': 'error'}, status=405)

@login_required
def enviar_ticket(request):
    if request.method == 'POST':
        asunto = request.POST.get('asunto')
        mensaje = request.POST.get('mensaje')
        
        # Creamos el ticket asociado al usuario que está logueado
        if asunto and mensaje:
            TicketSoporte.objects.create(
                usuario=request.user,
                asunto=asunto,
                mensaje=mensaje
            )
            messages.success(request, '✅ Tu mensaje ha sido enviado a soporte. Te responderemos pronto.')
        else:
            messages.error(request, '⚠️ Debes completar todos los campos del formulario.')
            
        return redirect('mi_perfil') # ¡Redirección corregida!
    
@login_required
def panel_soporte(request):
    """Panel Exclusivo para la Mesa de Ayuda y Tickets de Soporte"""
    from usuarios.models import PerfilUsuario, TicketSoporte
    
    perfil, created = PerfilUsuario.objects.get_or_create(usuario=request.user)
    
    # Validar si es del equipo de soporte
    es_agente = request.user.is_staff or request.user.is_superuser or perfil.rol == 'soporte'

    if es_agente:
        tickets_abiertos = TicketSoporte.objects.filter(estado='Abierto').order_by('-fecha_creacion')
        tickets_resueltos = TicketSoporte.objects.exclude(estado='Abierto').order_by('-fecha_creacion')[:30]
    else:
        tickets_abiertos = TicketSoporte.objects.filter(usuario=request.user, estado='Abierto').order_by('-fecha_creacion')
        tickets_resueltos = TicketSoporte.objects.filter(usuario=request.user).exclude(estado='Abierto').order_by('-fecha_creacion')[:20]

    contexto = {
        'tickets_abiertos': tickets_abiertos,
        'tickets_resueltos': tickets_resueltos,
        'es_agente': es_agente,
    }
    return render(request, 'usuarios/panel_soporte.html', contexto)   

@login_required
def responder_ticket(request, ticket_id):
    """Pantalla vistosa para que el agente responda o elimine un ticket específico"""
    from usuarios.models import PerfilUsuario, TicketSoporte
    
    perfil, created = PerfilUsuario.objects.get_or_create(usuario=request.user)
    es_agente = request.user.is_staff or request.user.is_superuser or perfil.rol == 'soporte'

    if not es_agente:
        return redirect('inicio_general')

    # Buscamos el ticket exacto
    ticket = get_object_or_404(TicketSoporte, id=ticket_id)

    if request.method == 'POST':
        # --- LÓGICA PARA ELIMINAR EL TICKET ---
        if 'eliminar' in request.POST:
            ticket.delete()
            return redirect('panel_soporte')
        # --------------------------------------

        # --- LÓGICA PARA GUARDAR RESPUESTA ---
        respuesta = request.POST.get('respuesta_admin')
        estado = request.POST.get('estado')

        ticket.respuesta_admin = respuesta
        ticket.estado = estado
        ticket.save()

        return redirect('panel_soporte')

    return render(request, 'usuarios/responder_ticket.html', {'ticket': ticket})

@csrf_exempt
def telegram_webhook(request):
    """Recibe la notificación directa de Telegram cuando el usuario le da a INICIAR"""
    if request.method == 'POST':
        try:
            update = json.loads(request.body)
            
            if 'message' in update:
                chat_id = update['message']['chat']['id']
                texto = update['message'].get('text', '')

                if texto.startswith('/start '):
                    codigo = texto.split(' ')[1]
                    
                    suscripcion = SuscripcionTelegram.objects.filter(codigo_vinculacion=codigo).first()
                    
                    if suscripcion:
                        suscripcion.chat_id = str(chat_id)
                        suscripcion.save()
                        
                        # Aquí se utiliza la variable global declarada arriba
                        url_telegram = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                        mensaje_exito = "✅ ¡Excelente! Tu cuenta de Señalética Plus ha sido vinculada correctamente. A partir de ahora, cuando solicites un aviso en el mapa, te notificaré por aquí cuando tu autobús esté cerca."
                        
                        requests.post(url_telegram, json={
                            'chat_id': chat_id,
                            'text': mensaje_exito
                        })
        except Exception as e:
            # Esto te ayudará a ver cualquier otro error interno en los logs de gunicorn
            print(f"Error procesando webhook de Telegram: {e}")
            
    return HttpResponse("OK", status=200)