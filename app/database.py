import os
import uuid
import psycopg2
import psycopg2.extras
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Railway may expose the URL under different names depending on the plugin version
DATABASE_URL = (
    os.getenv("DATABASE_URL")
    or os.getenv("POSTGRES_URL")
    or os.getenv("POSTGRESQL_URL")
    or os.getenv("DATABASE_PRIVATE_URL")
    or os.getenv("POSTGRES_PRIVATE_URL")
)

if not DATABASE_URL:
    _db_vars = [k for k in os.environ if "postgres" in k.lower() or "database" in k.lower() or "pg" in k.lower()]
    raise RuntimeError(
        f"DATABASE_URL is not set. DB-related env vars found: {_db_vars or 'none'}"
    )


def get_conn():
    return psycopg2.connect(DATABASE_URL)


def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id              SERIAL PRIMARY KEY,
                    order_ref       VARCHAR(100) NOT NULL,
                    client_name     VARCHAR(200) NOT NULL,
                    client_phone    VARCHAR(20),
                    token           UUID UNIQUE NOT NULL,
                    status          VARCHAR(20) NOT NULL DEFAULT 'pending',
                    novedad         TEXT,
                    fecha_novedad   DATE,
                    direccion_actual TEXT,
                    ciudad          VARCHAR(100),
                    correo          VARCHAR(100),
                    notes           TEXT,
                    address_text    TEXT,
                    address_lat     DOUBLE PRECISION,
                    address_lng     DOUBLE PRECISION,
                    confirmed_at    TIMESTAMP WITH TIME ZONE,
                    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)
            # Migrate existing tables
            for col, definition in [
                ("novedad",          "TEXT"),
                ("fecha_novedad",    "DATE"),
                ("direccion_actual", "TEXT"),
                ("ciudad",           "VARCHAR(100)"),
                ("correo",           "VARCHAR(100)"),
            ]:
                cur.execute(f"""
                    ALTER TABLE orders ADD COLUMN IF NOT EXISTS {col} {definition}
                """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS whatsapp_queue (
                    id          SERIAL PRIMARY KEY,
                    order_id    INTEGER NOT NULL REFERENCES orders(id),
                    order_ref   VARCHAR(100) NOT NULL,
                    client_name VARCHAR(200) NOT NULL,
                    phone       VARCHAR(20) NOT NULL,
                    form_link   TEXT NOT NULL,
                    status      VARCHAR(20) NOT NULL DEFAULT 'pending',
                    queued_at   TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    sent_at     TIMESTAMP WITH TIME ZONE
                )
            """)
        conn.commit()


def _blank_to_none(v):
    """Convert empty/whitespace strings to None (safe for DATE/numeric columns)."""
    if isinstance(v, str):
        return v.strip() or None
    return v


def create_order(order_ref, client_name, client_phone=None, novedad=None,
                 fecha_novedad=None, direccion_actual=None, ciudad=None, correo=None, notes=None):
    token = str(uuid.uuid4())
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO orders
                    (order_ref, client_name, client_phone, token,
                     novedad, fecha_novedad, direccion_actual, ciudad, correo, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
            """, (order_ref, client_name, _blank_to_none(client_phone), token,
                  _blank_to_none(novedad), _blank_to_none(fecha_novedad),
                  _blank_to_none(direccion_actual), _blank_to_none(ciudad),
                  _blank_to_none(correo), _blank_to_none(notes)))
            row = dict(cur.fetchone())
        conn.commit()
    return row


def create_orders_bulk(orders: list):
    results = []
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            for o in orders:
                token = str(uuid.uuid4())
                cur.execute("""
                    INSERT INTO orders
                        (order_ref, client_name, client_phone, token,
                         novedad, fecha_novedad, direccion_actual, ciudad, correo, notes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING *
                """, (o['order_ref'], o['client_name'],
                      _blank_to_none(o.get('client_phone')), token,
                      _blank_to_none(o.get('novedad')),
                      _blank_to_none(o.get('fecha_novedad')),
                      _blank_to_none(o.get('direccion_actual')),
                      _blank_to_none(o.get('ciudad')),
                      _blank_to_none(o.get('correo')),
                      _blank_to_none(o.get('notes'))))
                results.append(dict(cur.fetchone()))
        conn.commit()
    return results


def update_order(order_id: int, fields: dict):
    editable = ['order_ref', 'client_name', 'client_phone', 'novedad', 'fecha_novedad',
                'direccion_actual', 'ciudad', 'correo', 'notes', 'status']
    set_clauses = []
    params = []
    for k in editable:
        if k in fields:
            set_clauses.append(f"{k} = %s")
            params.append(fields[k])

    if not set_clauses:
        return None

    # Reverting to pending clears confirmed address
    if fields.get('status') == 'pending':
        set_clauses += ['address_text = NULL', 'address_lat = NULL',
                        'address_lng = NULL', 'confirmed_at = NULL']

    params.append(order_id)
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"UPDATE orders SET {', '.join(set_clauses)} WHERE id = %s RETURNING *",
                params,
            )
            row = cur.fetchone()
        conn.commit()
    return dict(row) if row else None


def get_order_by_token(token: str):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM orders WHERE token = %s", (token,))
            row = cur.fetchone()
    return dict(row) if row else None


def confirm_address(token: str, address_text: str, lat: float | None, lng: float | None):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                UPDATE orders
                SET address_text  = %s,
                    address_lat   = %s,
                    address_lng   = %s,
                    status        = 'confirmed',
                    confirmed_at  = NOW()
                WHERE token = %s AND status = 'pending'
                RETURNING *
            """, (address_text, lat, lng, token))
            row = cur.fetchone()
        conn.commit()
    return dict(row) if row else None


def list_orders(status: str | None = None, date_from: str | None = None, date_to: str | None = None):
    conditions, params = [], []
    if status and status != "all":
        conditions.append("status = %s")
        params.append(status)
    if date_from:
        conditions.append("created_at >= %s")
        params.append(date_from)
    if date_to:
        conditions.append("created_at <= %s::date + interval '1 day'")
        params.append(date_to)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(f"SELECT * FROM orders {where} ORDER BY created_at DESC", params)
            rows = cur.fetchall()
    return [dict(r) for r in rows]


def queue_whatsapp(order_ids: list, base_url: str):
    results = []
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            for oid in order_ids:
                cur.execute("SELECT * FROM orders WHERE id = %s", (oid,))
                o = cur.fetchone()
                if not o or not o['client_phone']:
                    continue
                form_link = f"{base_url}/address/{o['token']}"
                cur.execute("""
                    INSERT INTO whatsapp_queue (order_id, order_ref, client_name, phone, form_link)
                    VALUES (%s, %s, %s, %s, %s) RETURNING *
                """, (o['id'], o['order_ref'], o['client_name'], o['client_phone'], form_link))
                results.append(dict(cur.fetchone()))
                cur.execute("UPDATE orders SET status = 'contactado' WHERE id = %s", (oid,))
        conn.commit()
    return results


def list_whatsapp_queue(status: str | None = None):
    where = "WHERE status = %s" if status else ""
    params = [status] if status else []
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(f"SELECT * FROM whatsapp_queue {where} ORDER BY queued_at ASC", params)
            rows = cur.fetchall()
    return [dict(r) for r in rows]


def update_whatsapp_status(item_id: int, status: str):
    sent_at = "NOW()" if status == 'sent' else "NULL"
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(f"""
                UPDATE whatsapp_queue SET status = %s, sent_at = {sent_at}
                WHERE id = %s RETURNING *
            """, (status, item_id))
            row = cur.fetchone()
        conn.commit()
    return dict(row) if row else None


def get_stats():
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    COUNT(*)                                              AS total,
                    COUNT(*) FILTER (WHERE status = 'pending')           AS pending,
                    COUNT(*) FILTER (WHERE status = 'contactado')        AS contactado,
                    COUNT(*) FILTER (WHERE status = 'confirmed')         AS confirmed
                FROM orders
            """)
            return dict(cur.fetchone())
