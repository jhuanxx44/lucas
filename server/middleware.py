from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class UserContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        user_id = request.headers.get("X-User-Id", "default")
        request.state.user_id = user_id
        response = await call_next(request)
        return response
