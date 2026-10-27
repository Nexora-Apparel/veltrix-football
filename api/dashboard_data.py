"""Dedicated Vercel entrypoint for published dashboard data."""
from fastapi import FastAPI
from api.telegram import dashboard_data

app = FastAPI(title="Veltrix Football Dashboard Data")


@app.get("/", name="dashboard_data_root")
@app.get("/dashboard-data", name="dashboard_data_hyphen")
@app.get("/api/dashboard-data", name="dashboard_data_api_hyphen")
@app.get("/dashboard_data", name="dashboard_data_underscore")
@app.get("/api/dashboard_data", name="dashboard_data_api_underscore")
def get_dashboard_data() -> dict:
    return dashboard_data()
