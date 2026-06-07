from django.urls import path
from . import views

urlpatterns = [
    # --- ACCESO CIUDADANO ---
    path('registro/', views.SignUpView.as_view(), name='crear_perfil'),
    path('mi-panel/', views.dashboard_ciudadano, name='dashboard_ciudadano'),
    path('mi-panel/agregar-familiar/', views.DependienteCreateView.as_view(), name='crear_dependiente'),
    
    # --- LA FICHA DE EMERGENCIA PÚBLICA (NFC) ---

   path('sos/alerta/<uuid:token_nfc>/', views.ficha_sos_publica, name='ficha_sos_publica'),
    
    # --- CRUD ADMINISTRATIVO (Panel de Cuentas Base) ---
    path('gestionar/cuentas/', views.PerfilUsuarioListView.as_view(), name='listar_usuarios'),
    path('gestionar/cuentas/nueva/', views.PerfilUsuarioCreateView.as_view(), name='crear_usuario_admin'),
    path('gestionar/cuentas/editar/<int:pk>/', views.UsuarioUpdateView.as_view(), name='editar_usuario'),
    path('gestionar/cuentas/eliminar/<int:pk>/', views.UsuarioDeleteView.as_view(), name='eliminar_usuario'),
    path('usuarios/edicion-avanzada/', views.edicion_avanzada_usuarios, name='edicion_avanzada_usuarios'),
    path('nfc/asignar/', views.asignar_nfc, name='asignar_nfc'),
    path('nfc/auditoria/', views.auditoria_nfc, name='auditoria_nfc'),
    path('nfc/guardar/', views.guardar_nfc, name='guardar_nfc'),
    path('mi-perfil/', views.mi_perfil, name='mi_perfil'),
    path('sos/actualizar-gps/', views.actualizar_gps_alerta, name='actualizar_gps_alerta'),
    

]