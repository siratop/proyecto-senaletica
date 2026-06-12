from django.urls import path
from . import views
from flota import views as flota_views
urlpatterns = [

    path('panel/', views.panel_chofer, name='panel_chofer'),
    path('api/gps/', views.actualizar_gps, name='actualizar_gps'),
    path('unidades/', views.listar_unidades, name='listar_unidades'),
    path('unidades/editar/<int:unidad_id>/', views.editar_unidad, name='editar_unidad'),
    path('crear-unidad/', views.UnidadCreateView.as_view(), name='crear_unidad'),
    path('api/buses-tiempo-real/', views.api_buses_activos, name='api_buses_activos'),
    path('editar-usuario/<int:usuario_id>/', views.editar_usuario, name='editar_usuario'),
    path('gestionar-usuarios/', views.gestionar_usuarios, name='gestionar_usuarios'),
    path('flota/agregar-conductor/', views.agregar_conductor_flota, name='agregar_conductor_flota'),
    path('flota/eliminar-conductor/<int:unidad_id>/', views.eliminar_conductor_flota, name='eliminar_conductor_flota'),
    path('api/actualizar-ubicacion/', views.actualizar_ubicacion_chofer, name='api_actualizar_ubicacion'),
    path('api/flota/buses-activos/', views.api_buses_flota, name='api_buses_flota'),
    path('dashboard/', flota_views.dashboard_router, name='dashboard_router'),
    path('api/enviar-mensaje/<int:unidad_id>/', views.enviar_mensaje_chofer, name='enviar_mensaje'),
    path('api/leer-alertas/', views.leer_alertas_chofer, name='leer_alertas'),
    path('reportar-averia/<int:unidad_id>/', views.reportar_averia, name='reportar_averia'),
    path('api/actualizar-gps/', views.actualizar_ubicacion_chofer, name='actualizar_gps_bus'),
    path('api/buses-activos-json/', views.api_buses_json, name='api_buses_json'),
]