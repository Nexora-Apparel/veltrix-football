"""Dedicated Vercel entrypoint for the mobile command-centre dashboard."""
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from api.telegram import DASHBOARD_HTML

app = FastAPI(title="Veltrix Football Dashboard")


@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
@app.get("/api/dashboard", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    return HTMLResponse(DASHBOARD_HTML)
