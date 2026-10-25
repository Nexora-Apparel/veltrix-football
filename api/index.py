"""Compatibility entrypoint; the main FastAPI app serves /api/telegram."""
from api.telegram import app

__all__ = ["app"]
