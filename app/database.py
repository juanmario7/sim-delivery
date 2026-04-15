import os
import uuid
import psycopg2
import psycopg2.extras
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
                    id          SERIAL PRIMARY KEY,
                    order_ref   VARCHAR(100) NOT NULL,
                    client_name VARCHAR(200) NOT NULL,
                    client_phone VARCHAR(20),
                    token       UUID UNIQUE NOT NULL,
                    status      VARCHAR(20) NOT NULL DEFAULT 'pending',
                    notes       TEXT,
                    address_text TEXT,
                    address_lat  DOUBLE PRECISION,
                    address_lng  DOUBLE PRECISION,
                    confirmed_at TIMESTAMP WITH TIME ZONE,
                    created_at   TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)
        conn.commit()


def create_order(order_ref: str, client_name: str, client_phone: str | None, notes: str | None):
    token = str(uuid.uuid4())
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO orders (order_ref, client_name, client_phone, token, notes)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING *
            """, (order_ref, client_name, client_phone, token, notes))
            row = dict(cur.fetchone())
        conn.commit()
    return row


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


def get_stats():
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    COUNT(*)                                          AS total,
                    COUNT(*) FILTER (WHERE status = 'pending')       AS pending,
                    COUNT(*) FILTER (WHERE status = 'confirmed')     AS confirmed
                FROM orders
            """)
            return dict(cur.fetchone())
