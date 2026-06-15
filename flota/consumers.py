import json
from channels.generic.websocket import AsyncWebsocketConsumer

class MapaConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Cuando un ciudadano abre la app, lo metemos a la sala de transmisión
        self.room_group_name = 'mapa_envivo'
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        # Cuando el ciudadano cierra la app, lo sacamos de la sala
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    # Esta función recibe las coordenadas del bus y se las dispara al teléfono del ciudadano
    async def enviar_ubicacion(self, event):
        datos = event['datos']
        # Enviamos el JSON por el túnel de WebSocket
        await self.send(text_data=json.dumps(datos))