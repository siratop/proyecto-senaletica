import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from datetime import datetime

import json
from channels.generic.websocket import AsyncWebsocketConsumer

class MapaConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_group_name = 'mapa_envivo'
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        datos = json.loads(text_data)
        
        # Solo reenviamos la información a todos los conectados para pintar el mapa.
        # ELIMINAMOS la conexión a la base de datos aquí para evitar la duplicación de historiales.
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'enviar_ubicacion', # Unificado con el nombre que manda views.py
                'datos': datos
            }
        )

    # Handler unificado que recibe tanto los mensajes de la App como los del Views.py
    async def enviar_ubicacion(self, event):
        await self.send(text_data=json.dumps(event['datos']))