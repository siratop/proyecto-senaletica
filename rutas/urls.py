from django.urls import path
from . import views
from flota import views as flota_views

urlpatterns = [
    # ==========================================
    # MENÚ Y PANELES PRINCIPALES
    # ==========================================
    path('', views.inicio_general, name='inicio_general'),
    path('centro-de-control/', views.panel_admin_amigable, name='panel_admin_amigable'),
    path('panel-operativo/', flota_views.dashboard_router, name='dashboard_router'),
    
    # ==========================================
    # VISTAS DEL CIUDADANO (TÓTEM EN LA CALLE)
    # ==========================================
    path('totem/<int:parada_id>/', views.inicio_peaton, name='inicio_peaton'),
    path('alerta/<int:parada_id>/', views.alerta_emergencia, name='alerta_emergencia'),
    
    # ==========================================
    # APIs (TELEMETRÍA Y MÉTRICAS) - ¡AQUÍ ESTÁ LA MAGIA DEL MAPA!
    # ==========================================
    path('api/telemetria/<int:parada_id>/', views.api_telemetria, name='api_telemetria'),
    path('api/reportar/<int:parada_id>/<str:tipo_reporte>/', views.registrar_reporte_ciudadano, name='api_reportar'),
    
    # ESTAS DOS LÍNEAS ERAN LAS QUE FALTABAN PARA QUE EL BUS APAREZCA
    path('flota/api/buses-activos/', flota_views.api_buses_activos, name='api_buses_activos'),
    path('flota/api/buses-tiempo-real/', flota_views.api_buses_flota, name='api_buses_flota'),
    
    # ==========================================
    # CRUD ADMINISTRATIVO (NIVEL 3)
    # ==========================================
    # Paradas
    path('gestionar/paradas/', views.ParadaListView.as_view(), name='listar_paradas'),
    path('paradas/crear/', views.crear_parada, name='crear_parada'),
    path('paradas/editar/<int:pk>/', views.ParadaUpdateView.as_view(), name='editar_parada'),
    path('paradas/eliminar/<int:pk>/', views.ParadaDeleteView.as_view(), name='eliminar_parada'),
    
    # Rutas
    path('gestionar/rutas/', views.RutaListView.as_view(), name='listar_rutas'),
    path('rutas/crear/', views.crear_ruta, name='crear_ruta'),
    path('rutas/editar/<int:pk>/', views.RutaUpdateView.as_view(), name='editar_ruta'),
    path('rutas/eliminar/<int:pk>/', views.RutaDeleteView.as_view(), name='eliminar_ruta'),
    
    # Patrocinadores
    path('gestionar/patrocinadores/', views.PatrocinadorListView.as_view(), name='listar_patrocinadores'),
    path('patrocinadores/crear/', views.PatrocinadorCreateView.as_view(), name='crear_patrocinador'),
    path('patrocinadores/editar/<int:pk>/', views.PatrocinadorUpdateView.as_view(), name='editar_patrocinador'),
    path('patrocinadores/eliminar/<int:pk>/', views.PatrocinadorDeleteView.as_view(), name='eliminar_patrocinador'),
    
    # Funciones de Control y Métricas
    path('api/resetear-metricas/<int:parada_id>/', views.resetear_metricas, name='resetear_metricas'),
    path('guardar-incidente/', views.guardar_incidente, name='guardar_incidente'),
    path('resolver-incidente/<int:incidente_id>/', views.resolver_incidente, name='resolver_incidente'),
    path('publicidad/', views.gestionar_publicidad, name='gestionar_publicidad'),
    path('usuarios/', views.gestionar_usuarios, name='gestionar_usuarios'),
    path('guardar-sugerencia/', views.guardar_sugerencia, name='guardar_sugerencia'),
    path('alertas/', views.gestionar_alertas, name='gestionar_alertas'),
    
    # Sub-rutas del Centro de Control
    path('centro-de-control/alertas/', views.gestionar_alertas, name='gestionar_alertas'),
    path('centro-de-control/alertas/nueva/', views.crear_alerta, name='crear_alerta'),
    path('centro-de-control/buzon/', views.ver_sugerencias, name='ver_sugerencias'),
    path('centro-de-control/alertas/editar/<int:alerta_id>/', views.editar_alerta, name='editar_alerta'),
    path('centro-de-control/alertas/eliminar/<int:alerta_id>/', views.eliminar_alerta, name='eliminar_alerta'),
    path('centro-de-control/buzon/eliminar/<int:sugerencia_id>/', views.eliminar_sugerencia, name='eliminar_sugerencia'),
    path('centro-de-control/unidades/', views.listar_unidades, name='listar_unidades'),
    path('centro-de-control/unidades/editar/<int:unidad_id>/', views.editar_unidad, name='editar_unidad'),
    
    # Publicidad y Unidades
    path('publicidad/nueva-campana/', views.crear_campana, name='crear_campana'),
    path('publicidad/eliminar-campana/<int:campana_id>/', views.eliminar_campana, name='eliminar_campana'),
    path('unidades/eliminar/<int:unidad_id>/', views.eliminar_unidad, name='eliminar_unidad'),
    path('eliminar/<int:campana_id>/', views.eliminar_campana, name='eliminar_campana'),
    path('editar/<int:campana_id>/', views.editar_campana, name='editar_campana'),

    # Ruta para la API de la app del chofer
    path('api/actualizar-gps/', views.actualizar_gps_unidad, name='actualizar_gps_unidad'),

    path('centro-de-control/analitica/', views.panel_estadistico_inteligente, name='panel_estadistico_inteligente'),
    path('api/reporte-waze/', views.registrar_reporte_waze, name='registrar_reporte_waze'),
]