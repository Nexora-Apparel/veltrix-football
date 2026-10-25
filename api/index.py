"""Default Vercel Python entrypoint for the Veltrix Telegram webhook."""
from api.telegram import handler

__all__ = ["handler"]
