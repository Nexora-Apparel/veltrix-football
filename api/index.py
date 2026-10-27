"""Vercel entrypoint with query-dispatched dashboard aliases."""
from api.telegram import app

@app.middleware("http")
async def dispatch_dashboard_rewrites(request, call_next):
    # Vercel Python functions are routed by the exact /api/index function path;
    # deeper rewrite destinations do not reliably invoke this function.
    # Route both public dashboard URLs through /api/index and dispatch here.
    if request.url.path == "/api/index":
        route = request.query_params.get("route")
        if route == "dashboard":
            request.scope["path"] = "/"
            request.scope["raw_path"] = b"/"
        elif route == "dashboard-data":
            request.scope["path"] = "/api/dashboard-data"
            request.scope["raw_path"] = b"/api/dashboard-data"
    return await call_next(request)

__all__ = ["app"]
