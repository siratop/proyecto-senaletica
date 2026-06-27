from django.urls import path
from . import views
from flota import views as flota_views
from .views import activar_alerta_parada, telegram_webhook
urlpatterns = [
    # Panel y CRUD
    path('panel/', views.panel_chofer, name='panel_chofer'),
    path('dashboard/', flota_views.dashboard_router, name='dashboard_router'),
    path('unidades/', views.listar_unidades, name='listar_unidades'),
    path('unidades/editar/<int:unidad_id>/', views.editar_unidad, name='editar_unidad'),
    path('crear-unidad/', views.UnidadCreateView.as_view(), name='crear_unidad'),
    
    # Gestión de Usuarios y Flota
    path('editar-usuario/<int:usuario_id>/', views.editar_usuario, name='editar_usuario'),
    path('gestionar-usuarios/', views.gestionar_usuarios, name='gestionar_usuarios'),
    path('flota/agregar-conductor/', views.agregar_conductor_flota, name='agregar_conductor_flota'),
    path('flota/eliminar-conductor/<int:unidad_id>/', views.eliminar_conductor_flota, name='eliminar_conductor_flota'),
    
    # Alertas y Web Chofer
    path('api/actualizar-ubicacion/', views.actualizar_ubicacion_chofer, name='api_actualizar_ubicacion'),
    path('api/enviar-mensaje/<int:unidad_id>/', views.enviar_mensaje_chofer, name='enviar_mensaje'),
    path('api/leer-alertas/', views.leer_alertas_chofer, name='leer_alertas'),
    path('reportar-averia/<int:unidad_id>/', views.reportar_averia, name='reportar_averia'),
    
    # =======================================================
    # RUTAS VIP PARA EL MAPA CIUDADANO Y LA APP MÓVIL (EXPO)
    # =======================================================
    # 1. Por aquí el dueño de la flota ve todos sus buses
    path('api/flota/buses-activos/', views.api_buses_flota, name='api_buses_flota'),
    
    # 2. Por aquí la App Móvil manda el GPS y el aviso de apagado
    path('api/actualizar-gps/', views.actualizar_gps, name='actualizar_gps'),
    
    # 3. Por aquí el Mapa Web público pide los buses para mostrarlos
    path('api/buses-activos/', views.api_buses_activos, name='api_buses_activos'),
   
    path('panel/historial/', views.historial_flota, name='historial_flota'),
   
    path('mantenimiento/', views.mantenimiento_flota, name='mantenimiento_flota'),
    path('historial/', views.historial_flota, name='historial_flota'),
    path('historial/eliminar/<int:historial_id>/', views.eliminar_historial, name='eliminar_historial'),
    path('historial/purgar/', views.limpiar_todo_historial, name='limpiar_todo_historial'),
    path('telegram-webhook/', telegram_webhook, name='telegram_webhook'),
    path('api/activar-alerta/', activar_alerta_parada, name='activar_alerta_parada'),
    path('panel/unidad/eliminar/<int:unidad_id>/', views.eliminar_unidad, name='eliminar_unidad'),
]