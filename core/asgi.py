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
    # 1. Peticiones normales de la web (Las que ya tenías)
    "http": django_asgi_app,
    
    # 2. Peticiones en tiempo real (El nuevo túnel)
    "websocket": AuthMiddlewareStack(
        URLRouter(
            rutas.routing.websocket_urlpatterns
        )
    ),
})