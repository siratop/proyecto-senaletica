from django.urls import re_path
from flota import consumers # Importamos el "locutor" que creamos en la app flota

websocket_urlpatterns = [
    # Esta es la dirección del túnel a la que se conectará el mapa del ciudadano
    re_path(r'ws/mapa/$', consumers.MapaConsumer.as_asgi()),
]