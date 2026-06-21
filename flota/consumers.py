import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

# IMPORTANTE: Cambia 'flota' por el nombre real de la carpeta donde tienes tus models y utils
from flota.models import Bus 
from flota.utils import registrar_inicio_turno, registrar_fin_turno

class MapaConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Cuando un ciudadano o chofer abre la app, lo metemos a la sala de transmisión
        self.room_group_name = 'mapa_envivo'
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        # Cuando cierran la app, lo sacamos de la sala
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    # NUEVO: Esta función recibe la señal directamente del teléfono del chofer
    async def receive(self, text_data):
        datos = json.loads(text_data)
        
        # 1. --- LÓGICA DE AUDITORÍA Y CONTROL (HISTORIAL) ---
        bus_id = datos.get('bus_id')
        
        # Verificamos si el json dice que está activo o inactivo (por defecto asumimos True)
        esta_activo = datos.get('en_servicio', True) 
        
        if bus_id:
            # Llamamos a nuestra función segura de base de datos
            await self.gestionar_historial(bus_id, esta_activo)

        # 2. --- REENVÍO AL CIUDADANO ---
        # Disparamos las coordenadas a todos los que estén viendo el mapa en ese momento
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'enviar_ubicacion',
                'datos': datos
            }
        )

    # Esta función recibe las coordenadas del grupo y se las entrega al frontend
    async def enviar_ubicacion(self, event):
        datos = event['datos']
        # Enviamos el JSON por el túnel de WebSocket a la pantalla
        await self.send(text_data=json.dumps(datos))

    # --- PUENTE SEGURO HACIA LA BASE DE DATOS ---
    @database_sync_to_async
    def gestionar_historial(self, bus_id, esta_activo):
        """
        Esta función sirve como traductor entre el mundo súper rápido (async) 
        de WebSockets y el mundo tradicional (sync) de la base de datos de Django.
        """
        try:
            # Buscamos el autobús
            bus = Bus.objects.get(id=bus_id)
            conductor = bus.conductor
            
            # Ejecutamos las funciones de tu utils.py
            if esta_activo:
                registrar_inicio_turno(bus, conductor)
            else:
                registrar_fin_turno(bus, conductor)
                
        except Bus.DoesNotExist:
            # Si mandan un bus_id falso, simplemente lo ignoramos para no tumbar el server
            pass