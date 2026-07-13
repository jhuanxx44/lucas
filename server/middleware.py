from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class UserContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.user_id = "default"
        response = await call_next(request)
        return response
