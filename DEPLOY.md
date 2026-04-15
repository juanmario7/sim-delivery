# Deploy – SIM Delivery Address Collector

## Variables de entorno requeridas

| Variable | Descripción |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string (`postgresql://user:pass@host:5432/db`) |
| `GOOGLE_MAPS_API_KEY` | Google Maps API key (Geocoding API + Places API habilitadas) |
| `BASE_URL` | URL pública del servidor, ej: `https://vmcontigo.co` |

## Instalar dependencias

```bash
pip install -r requirements.txt
```

## Correr en desarrollo

```bash
cp .env.example .env   # edita con tus valores
python run.py
```

## Correr en producción (Heroku / AWS)

```bash
# Heroku
heroku config:set DATABASE_URL=... GOOGLE_MAPS_API_KEY=... BASE_URL=...
git push heroku main

# AWS / Lightsail (con gunicorn)
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Rutas

| Ruta | Descripción |
|---|---|
| `/dashboard` | Panel interno de creación y gestión de pedidos |
| `/address/{token}` | Formulario del cliente (enlace único por pedido) |

## Flujo

1. Operador crea un pedido desde `/dashboard` (número de pedido + nombre + teléfono).
2. El sistema genera un enlace único `/address/{token}`.
3. El operador copia el enlace o lo envía por WhatsApp directamente desde el dashboard.
4. El cliente abre el enlace, ingresa su dirección (con GPS o Google Maps autocomplete) y confirma.
5. El dashboard actualiza el estado de `pending` → `confirmed` y muestra la dirección y coordenadas.

## Base de datos

La tabla `orders` se crea automáticamente al iniciar la app.

```sql
CREATE TABLE orders (
    id           SERIAL PRIMARY KEY,
    order_ref    VARCHAR(100) NOT NULL,
    client_name  VARCHAR(200) NOT NULL,
    client_phone VARCHAR(20),
    token        UUID UNIQUE NOT NULL,
    status       VARCHAR(20) NOT NULL DEFAULT 'pending',
    notes        TEXT,
    address_text TEXT,
    address_lat  DOUBLE PRECISION,
    address_lng  DOUBLE PRECISION,
    confirmed_at TIMESTAMP WITH TIME ZONE,
    created_at   TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```
