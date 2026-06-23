import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from datetime import datetime

class MapaConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_group_name = 'mapa_envivo'
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        datos = json.loads(text_data)
        
        # Atrapar el ID del bus (sea web o app)
        bus_id = datos.get('bus_id') or datos.get('unidad_id') or datos.get('id')
        esta_activo = datos.get('en_servicio', True)

        if bus_id:
            await self.gestionar_historial(bus_id, esta_activo)
            
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'mapa_mensaje',
                'datos': datos
            }
        )

    async def mapa_mensaje(self, event):
        await self.send(text_data=json.dumps(event['datos']))

    # LÓGICA DE AUDITORÍA PARA LA WEB
    @database_sync_to_async
    def gestionar_historial(self, bus_id_raw, esta_activo):
        try:
            from django.contrib.auth.models import User
            from flota.models import Unidad, HistorialTurno
            
            unidad = Unidad.objects.filter(id=int(bus_id_raw)).first()
            if not unidad:
                return

            hoy = timezone.now().date()
            ahora = timezone.now().time()
            
            turnos_abiertos = HistorialTurno.objects.filter(bus=unidad, fecha=hoy, hora_fin__isnull=True)
            se_esta_apagando = str(esta_activo).lower() in ['false', '0', 'no']

            if se_esta_apagando:
                # Cierra todos los turnos abiertos de la web
                for turno in turnos_abiertos:
                    turno.hora_fin = ahora
                    inicio_dt = datetime.combine(hoy, turno.hora_inicio)
                    fin_dt = datetime.combine(hoy, ahora)
                    diferencia = fin_dt - inicio_dt
                    horas = diferencia.seconds // 3600
                    minutos = (diferencia.seconds % 3600) // 60
                    turno.duracion = f"{horas}h {minutos}m"
                    turno.save()
            else:
                if not turnos_abiertos.exists():
                    chofer_default = getattr(unidad, 'propietario_flota', None) or User.objects.first()
                    HistorialTurno.objects.create(bus=unidad, fecha=hoy, hora_inicio=ahora, conductor=chofer_default)
                elif turnos_abiertos.count() > 1:
                    clones = list(turnos_abiertos)[1:]
                    for c in clones:
                        c.delete()
        except Exception as e:
            print(f"Error WS DB: {e}")