import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
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
            from django.contrib.auth.models import User
            
            unidad = Unidad.objects.get(id=bus_id)
            hoy = timezone.now().date()
            ahora = timezone.now().time()
            
            turno_abierto = HistorialTurno.objects.filter(
                bus=unidad, fecha=hoy, hora_fin__isnull=True
            ).first()

            if esta_activo and not turno_abierto:
                # Buscamos al dueño de la flota o al primer chofer para que no falle si es obligatorio
                chofer_default = unidad.propietario_flota or User.objects.first()
                
                try:
                    HistorialTurno.objects.create(
                        bus=unidad,
                        fecha=hoy,
                        hora_inicio=ahora,
                        conductor=chofer_default # Previene el error de "conductor_id is null"
                    )
                    print(f"✅ GPS: Turno ABIERTO para la unidad {unidad.numero_unidad}")
                except Exception as e:
                    print(f"❌ GPS ERROR AL GUARDAR: {e}")

            elif not esta_activo and turno_abierto:
                turno_abierto.hora_fin = ahora
                turno_abierto.save()
                print(f"🔴 GPS: Turno CERRADO para la unidad {unidad.numero_unidad}")
                
        except Unidad.DoesNotExist:
            print(f"⚠️ GPS: El teléfono envió un bus_id que no existe en BD ({bus_id})")