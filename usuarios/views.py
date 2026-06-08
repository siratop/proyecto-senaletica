from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required
from django.views.generic import CreateView, ListView, UpdateView, DeleteView
from django.urls import reverse_lazy
import datetime
from django.contrib.admin.views.decorators import staff_member_required
from .models import Dependiente, RegistroActividad, TarjetaNFC, PerfilUsuario, SolicitudOperador
from .forms import RegistroInclusivoForm
from django.utils import timezone
from datetime import timedelta
from django.contrib import messages
from django.contrib.auth import logout
from django.db import IntegrityError 
from django.http import JsonResponse
# =========================================================
# 1. REGISTRO Y GESTIÓN DE CUENTAS
# =========================================================

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
    contexto = {
        'dependientes': mis_dependientes
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

from django.core.mail import send_mail
from django.conf import settings
from django.shortcuts import render, get_object_or_404

def ficha_sos_publica(request, token_nfc):
    """Pantalla pública de asistencia para personas extraviadas (NFC)"""
    
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
        # 1. Guardar la alerta en el mapa del Centro de Control
        alerta_creada = AlertaOperativa.objects.create(
            tipo='incidente',
            mensaje=mensaje_sos,
            dependiente=dependiente, 
            activa=True,
            latitud=0.0,
            longitud=0.0
        )
        alerta_id = alerta_creada.id 
        print(f" Alerta NFC guardada en Base de Datos para: {dependiente.nombre_completo} (ID: {alerta_id})")
        
        
        asunto_correo = f"🚨 ALERTA DE EMERGENCIA: {dependiente.nombre_completo} necesita ayuda"
        cuerpo_correo = f"""
SISTEMA SEÑALÉTICA+ - ALERTA VITAL
===================================
Se acaba de escanear la pulsera NFC de seguridad de su familiar:

Familiar: {dependiente.nombre_completo}
Condición Registrada: {dependiente.condicion_medica}

Si el rescatista comparte su ubicación (GPS), nuestro sistema lo reflejará en el Centro de Operaciones.
Por favor, manténgase atento a su número principal: {dependiente.telefono_emergencia}

Este es un mensaje automático de seguridad.
"""
        # Ejecutamos el envío del correo electrónico
        send_mail(
            asunto_correo,
            cuerpo_correo,
            settings.DEFAULT_FROM_EMAIL,
            [dependiente.tutor.email], # Extraemos el correo real del padre/tutor
            fail_silently=False
        )
        print("Correo de emergencia enviado al tutor con éxito.")

    except Exception as e:
        print(f"Error al registrar alerta NFC o enviar correo: {e}")

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
    """Edición de una cuenta de usuario existente"""
    model = User
    fields = ['username', 'email', 'first_name', 'last_name', 'is_staff']
    template_name = 'formulario_generico.html'
    success_url = reverse_lazy('listar_usuarios')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo'] = '✏️ Editar Cuenta de Usuario'
        return context

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
        
        # Validar que los campos no vengan vacíos
        if not usuario_id or not codigo_nfc:
            messages.error(request, "Error: Debe seleccionar un usuario y colocar un código NFC.")
            return redirect('asignar_nfc')
            
        try:
            usuario = User.objects.get(id=usuario_id)
            
            # Verificamos si este usuario ya tiene una tarjeta (OneToOneField)
            if hasattr(usuario, 'tarjetanfc'):
                # Actualizamos la tarjeta existente
                usuario.tarjetanfc.codigo_uid = codigo_nfc
                usuario.tarjetanfc.activa = True
                usuario.tarjetanfc.save()
                messages.success(request, f"Tarjeta NFC de {usuario.username} actualizada correctamente.")
            else:
                # Creamos una tarjeta nueva
                TarjetaNFC.objects.create(usuario=usuario, codigo_uid=codigo_nfc, activa=True)
                messages.success(request, f"Tarjeta NFC vinculada a {usuario.username} con éxito.")
                
        except User.DoesNotExist:
            messages.error(request, "Error: El usuario seleccionado no existe en el sistema.")
        except IntegrityError:
            # Si el código NFC (link) ya está en uso por otra persona
            messages.error(request, "Error crítico: El código o enlace NFC ya está asignado a otro usuario distinto.")
        except Exception as e:
            # Captura de errores inesperados (evita el 500)
            print(f"Error inesperado al guardar NFC: {e}")
            messages.error(request, "Error interno al procesar la vinculación NFC.")
            
    return redirect('asignar_nfc')

@login_required
def mi_perfil(request):
    perfil, created = PerfilUsuario.objects.get_or_create(usuario=request.user)
    
    # 1. Lógica del candado de 7 días (Datos Personales)
    puede_editar = True
    dias_restantes = 0
    if perfil.ultima_modificacion:
        tiempo_pasado = timezone.now() - perfil.ultima_modificacion
        if tiempo_pasado.days < 7:
            puede_editar = False
            dias_restantes = 7 - tiempo_pasado.days

    # 2. Lógica del candado de 30 días (Dueños de Flota)
    dias_restantes_flota = 0
    if perfil.rol == 'flota' and not perfil.puede_cambiar_nombre():
        dias_pasados = (timezone.now() - perfil.fecha_cambio_nombre).days
        dias_restantes_flota = 30 - dias_pasados

    if request.method == 'POST':
        action = request.POST.get('action')

        # Acción: Actualizar Datos Personales
        if action == 'update_data' and puede_editar:
            user = request.user
            user.first_name = request.POST.get('nombre')
            user.last_name = request.POST.get('apellido')
            user.email = request.POST.get('email')
            user.save()
            
            perfil.telefono = request.POST.get('telefono')
            perfil.ultima_modificacion = timezone.now() # Iniciamos el candado de 7 días
            perfil.save()
            
            messages.success(request, "Datos actualizados correctamente. Por seguridad, no podrá modificarlos de nuevo hasta dentro de 7 días.")
            return redirect('mi_perfil')

        # Acción: Configurar Identidad de Flota
        elif request.POST.get('guardar_flota'):
            if perfil.rol == 'flota':
                # El teléfono de la flota siempre se puede actualizar libremente
                perfil.telefono = request.POST.get('telefono_flota')
                
                # Verificamos si el candado del nombre está abierto
                if perfil.puede_cambiar_nombre():
                    perfil.nombre_flota = request.POST.get('nombre_flota')
                    perfil.fecha_cambio_nombre = timezone.now()
                    messages.success(request, "Datos de la flota actualizados. El nombre de la empresa ha sido bloqueado por 30 días.")
                else:
                    messages.success(request, "Teléfono de contacto de la flota actualizado. (El nombre comercial sigue bloqueado).")
                
                perfil.save()
            return redirect('mi_perfil')

        # Acción: Solicitud de Operador
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

        # Acción: Zona de Peligro (Eliminar Cuenta)
        elif action == 'eliminar_cuenta':
            user = request.user
            logout(request)
            user.delete()
            return redirect('login') 

    return render(request, 'usuarios/mi_perfil.html', {
        'perfil': perfil,
        'puede_editar': puede_editar,
        'dias_restantes': dias_restantes,
        'dias_restantes_flota': dias_restantes_flota 
    })