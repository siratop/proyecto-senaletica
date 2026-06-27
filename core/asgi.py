import os
from django.core.asgi import get_asgi_application

# Establecer settings antes de importar componentes de Channels
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

# Cargar la aplicación HTTP normal
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import rutas.routing

application = ProtocolTypeRouter({
    
    "http": django_asgi_app,
    
   
    "websocket": AuthMiddlewareStack(
        URLRouter(
            rutas.routing.websocket_urlpatterns
        )
    ),
})