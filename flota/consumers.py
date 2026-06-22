import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from flota.models import Bus 
from flota.utils import registrar_inicio_turno, registrar_fin_turno
from django.utils import timezone
from flota.models import Unidad, HistorialTurno

class MapaConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Cuando un ciudadano o chofer abre la app
        self.room_group_name = 'mapa_envivo'
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        # Cuando cierran la app
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        datos = json.loads(text_data)

        # LÓGICA DE AUDITORÍA Y CONTROL (HISTORIAL)
        bus_id = datos.get('bus_id')
        
        # Asumimos que está en servicio si la app envía ubicación
        esta_activo = datos.get('en_servicio', True)

        if bus_id:
            # Llamamos a nuestra función segura de base de datos
            await self.gestionar_historial(bus_id, esta_activo)
            
        # -------------------------------------------------------------
        # AQUÍ DEBE IR TU CÓDIGO PARA RETRANSMITIR EL GPS AL MAPA
        # (El group_send que tenías configurado antes para mover el bus)
        # -------------------------------------------------------------
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'mapa_mensaje',
                'datos': datos
            }
        )

    async def mapa_mensaje(self, event):
        # Envía las coordenadas a todos los conectados
        datos = event['datos']
        await self.send(text_data=json.dumps(datos))

    # 2. FUNCIÓN DE GUARDADO SEGURO EN BASE DE DATOS
    @database_sync_to_async
    def gestionar_historial(self, bus_id, esta_activo):
        try:
            # Buscamos el autobús real
            unidad = Unidad.objects.get(id=bus_id)
            hoy = timezone.now().date()
            ahora = timezone.now().time()
            
            # Buscamos si hay un turno abierto para hoy (que no tenga hora de fin)
            turno_abierto = HistorialTurno.objects.filter(
                bus=unidad, 
                fecha=hoy, 
                hora_fin__isnull=True
            ).first()

            if esta_activo and not turno_abierto:
                # El bus se conectó y no tenía turno abierto -> Creamos uno nuevo
                HistorialTurno.objects.create(
                    bus=unidad,
                    fecha=hoy,
                    hora_inicio=ahora
                )
            elif not esta_activo and turno_abierto:
                # El bus se desconectó o apagó servicio -> Cerramos su turno
                turno_abierto.hora_fin = ahora
                turno_abierto.save()
                
        except Unidad.DoesNotExist:
            # Si el GPS manda un ID que no existe, lo ignoramos para no tumbar el servidor
            pass