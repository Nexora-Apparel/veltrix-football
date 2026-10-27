"""Vercel entrypoint and explicit dashboard route aliases."""
from fastapi.responses import HTMLResponse
from api.telegram import app, dashboard, dashboard_data

# Vercel rewrites requests to these explicit paths; keep the public API routes
# unchanged so Telegram webhook traffic is not intercepted.
app.add_api_route("/api/index/dashboard", dashboard, methods=["GET"], response_class=HTMLResponse, include_in_schema=False)
app.add_api_route("/api/index/dashboard-data", dashboard_data, methods=["GET"], include_in_schema=False)

__all__ = ["app"]
