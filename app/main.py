import os
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import database, geocoding

load_dotenv()
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
MAPS_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")

app = FastAPI(title="SIM Delivery – Address Collector")


@app.on_event("startup")
def startup():
    database.init_db()


# ── Static & pages ──────────────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory="frontend"), name="static")


@app.get("/")
def root():
    return RedirectResponse("/dashboard")


@app.get("/dashboard")
def dashboard():
    return FileResponse("frontend/dashboard.html")


@app.get("/address/{token}")
def address_form(token: str):
    order = database.get_order_by_token(token)
    if not order:
        raise HTTPException(status_code=404, detail="Enlace no válido")
    return FileResponse("frontend/form.html")


# ── Config (exposes non-secret settings to frontend) ────────────────────────

@app.get("/api/config")
def config():
    return {"maps_api_key": MAPS_KEY, "base_url": BASE_URL}


# ── Orders ───────────────────────────────────────────────────────────────────

class OrderCreate(BaseModel):
    order_ref: str
    client_name: str
    client_phone: Optional[str] = None
    notes: Optional[str] = None


@app.post("/api/orders", status_code=201)
def create_order(body: OrderCreate):
    return database.create_order(body.order_ref, body.client_name, body.client_phone, body.notes)


@app.get("/api/orders")
def list_orders(
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    return database.list_orders(status, date_from, date_to)


@app.get("/api/stats")
def stats():
    return database.get_stats()


# ── Address submission (client-facing) ───────────────────────────────────────

class AddressSubmit(BaseModel):
    address_text: str
    lat: Optional[float] = None
    lng: Optional[float] = None


@app.get("/api/address/{token}")
def get_order_by_token(token: str):
    order = database.get_order_by_token(token)
    if not order:
        raise HTTPException(status_code=404, detail="Enlace no válido")
    return order


@app.post("/api/address/{token}")
def submit_address(token: str, body: AddressSubmit):
    lat, lng = body.lat, body.lng

    # If no GPS coords were provided, geocode the text address
    if not lat or not lng:
        result = geocoding.geocode(body.address_text)
        if result:
            lat, lng = result["lat"], result["lng"]

    order = database.confirm_address(token, body.address_text, lat, lng)
    if not order:
        raise HTTPException(
            status_code=400,
            detail="Este enlace ya fue utilizado o no es válido.",
        )
    return order
