from django.http import JsonResponse

# Reachable without a session: the login flow itself and the uptime check.
PUBLIC_PATHS = ("/api/auth/", "/api/health")


class LoginRequiredMiddleware:
    """Every /api/ route needs a signed-in user, except the login endpoints.

    Answers 401 JSON (not a redirect) because the caller is the SPA, which
    sends people to its own /login page."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if path.startswith("/api/") and not path.startswith(PUBLIC_PATHS) and not request.user.is_authenticated:
            return JsonResponse({"error": "Sign in required", "login": True}, status=401)
        return self.get_response(request)
