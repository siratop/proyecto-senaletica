from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from usuarios import views
from django.views.generic import TemplateView
urlpatterns = [
    path('admin/', admin.site.urls), 
    path('', include('rutas.urls')),
    path('usuarios/', include('usuarios.urls')),
    path('flota/', include('flota.urls')),
    path('accounts/', include('django.contrib.auth.urls')),
    path('centro-de-control/', views.edicion_avanzada_usuarios, name='panel_control'),
    path('manifest.json', TemplateView.as_view(template_name='manifest.json', content_type='application/json'), name='manifest'),
    path('sw.js', TemplateView.as_view(template_name='sw.js', content_type='application/javascript'), name='sw'),


]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)