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
    novedad: Optional[str] = None
    fecha_novedad: Optional[str] = None
    direccion_actual: Optional[str] = None
    ciudad: Optional[str] = None
    correo: Optional[str] = None
    notes: Optional[str] = None


@app.post("/api/orders", status_code=201)
def create_order(body: OrderCreate):
    return database.create_order(
        body.order_ref, body.client_name, body.client_phone,
        body.novedad, body.fecha_novedad, body.direccion_actual,
        body.ciudad, body.correo, body.notes,
    )


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


class OrderUpdate(BaseModel):
    order_ref: Optional[str] = None
    client_name: Optional[str] = None
    client_phone: Optional[str] = None
    novedad: Optional[str] = None
    fecha_novedad: Optional[str] = None
    direccion_actual: Optional[str] = None
    ciudad: Optional[str] = None
    correo: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None


@app.put("/api/orders/{order_id}")
def update_order(order_id: int, body: OrderUpdate):
    order = database.update_order(order_id, body.model_dump(exclude_unset=True))
    if not order:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    return order


# ── WhatsApp queue ───────────────────────────────────────────────────────────

class WhatsAppQueueRequest(BaseModel):
    order_ids: list[int]


class WhatsAppStatusUpdate(BaseModel):
    status: str   # 'sent' | 'failed'


@app.post("/api/whatsapp-queue", status_code=201)
def enqueue_whatsapp(body: WhatsAppQueueRequest):
    results = database.queue_whatsapp(body.order_ids, BASE_URL)
    if not results:
        raise HTTPException(status_code=400, detail="Ningún pedido válido para encolar (verifica que tengan teléfono).")
    return results


@app.get("/api/whatsapp-queue")
def get_whatsapp_queue(status: Optional[str] = None):
    return database.list_whatsapp_queue(status)


@app.put("/api/whatsapp-queue/{item_id}")
def update_whatsapp_status(item_id: int, body: WhatsAppStatusUpdate):
    item = database.update_whatsapp_status(item_id, body.status)
    if not item:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    return item


class OrderBulkItem(BaseModel):
    order_ref: str
    client_name: str
    client_phone: Optional[str] = None
    novedad: Optional[str] = None
    fecha_novedad: Optional[str] = None
    direccion_actual: Optional[str] = None
    ciudad: Optional[str] = None
    correo: Optional[str] = None
    notes: Optional[str] = None


@app.post("/api/orders/bulk", status_code=201)
def create_orders_bulk(body: list[OrderBulkItem]):
    return database.create_orders_bulk([o.model_dump() for o in body])


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
