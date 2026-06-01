# usuarios/middleware.py
from .models import RegistroActividad

class RegistrarVisitaMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            # Registramos que el usuario hizo una petición
            RegistroActividad.objects.create(
                user=request.user, 
                accion=f"Acceso a página: {request.path}"
            )
        return self.get_response(request)