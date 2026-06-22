import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone


class MapaConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_group_name = 'mapa_envivo'
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        datos = json.loads(text_data)

        # 1. ATRApar EL ID COMO SEA QUE VENGA DEL GPS
        bus_id = datos.get('bus_id') or datos.get('unidad_id') or datos.get('id')
        esta_activo = datos.get('en_servicio', True)

        if bus_id:
            await self.gestionar_historial(bus_id, esta_activo)
            
        # Retransmitir al mapa
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'mapa_mensaje',
                'datos': datos
            }
        )

    async def mapa_mensaje(self, event):
        datos = event['datos']
        await self.send(text_data=json.dumps(datos))

    # 2. GUARDADO BLINDADO EN BASE DE DATOS
    @database_sync_to_async
    def gestionar_historial(self, bus_id_raw, esta_activo):
        try:
            from django.contrib.auth.models import User
            from flota.models import Unidad, HistorialTurno
            
            # Buscar la unidad asegurándonos de que sea un número entero
            unidad = Unidad.objects.filter(id=int(bus_id_raw)).first()
            
            if not unidad:
                print(f"⚠️ [GPS] Ignorado: ID {bus_id_raw} no existe en la base de datos.")
                return

            hoy = timezone.now().date()
            ahora = timezone.now().time()
            
            turno_abierto = HistorialTurno.objects.filter(
                bus=unidad, fecha=hoy, hora_fin__isnull=True
            ).first()

            if esta_activo and not turno_abierto:
                # Asignar chofer por defecto sin fallar
                chofer_default = unidad.propietario_flota
                if not chofer_default:
                    chofer_default = User.objects.first()
                
                try:
                    HistorialTurno.objects.create(
                        bus=unidad,
                        fecha=hoy,
                        hora_inicio=ahora,
                        conductor=chofer_default
                    )
                    print(f"✅ [GPS] Turno CREADO para unidad: {unidad.numero_unidad}")
                except Exception as e:
                    print(f"❌ [GPS] ERROR AL CREAR TURNO: {str(e)}")

            elif not esta_activo and turno_abierto:
                turno_abierto.hora_fin = ahora
                turno_abierto.save()
                print(f"🔴 [GPS] Turno CERRADO para unidad: {unidad.numero_unidad}")
                
        except Exception as e:
            print(f"🚨 [GPS] FALLO CRÍTICO en gestionar_historial: {str(e)}")