"""Vercel entrypoint with query-dispatched dashboard aliases."""
from api.telegram import app

@app.middleware("http")
async def dispatch_dashboard_rewrites(request, call_next):
    # Query-based dispatch works regardless of whether Vercel preserves or
    # strips the function prefix while forwarding an internal rewrite.
    route = request.query_params.get("route")
    if route == "dashboard":
        request.scope["path"] = "/"
        request.scope["raw_path"] = b"/"
    elif route == "dashboard-data":
        request.scope["path"] = "/api/dashboard-data"
        request.scope["raw_path"] = b"/api/dashboard-data"
    return await call_next(request)

__all__ = ["app"]
