import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "pricing.db"

DEFAULT_SETTINGS: dict[str, str] = {
    "labour_rate_gbp_per_hr": "35",
    "vat_enabled": "1",
    "vat_rate_pct": "20",
    "commission_deposit_pct": "50",
    "estimate_variance_pct": "10",
    "estimate_valid_days": "7",
    "metal_waste_pct": "5",
    "overhead_pct": "10",
    "target_profit_margin_pct": "25",
    "troy_oz_to_grams": "31.1034768",
    "price_cache_ttl_minutes": "60",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS metal_prices (
            symbol TEXT PRIMARY KEY,
            price_gbp_per_oz REAL NOT NULL,
            fetched_at TEXT NOT NULL,
            provider TEXT NOT NULL
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS stones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stone_type TEXT NOT NULL,
            size_mm_or_carat TEXT NOT NULL,
            grade TEXT NOT NULL,
            supplier TEXT NOT NULL,
            cost_gbp REAL NOT NULL,
            default_markup_pct REAL NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS commission_quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT,
            quote_type TEXT NOT NULL DEFAULT 'quote',
            metal_symbol TEXT NOT NULL,
            alloy_label TEXT,
            weight_grams REAL NOT NULL,
            labour_hours REAL NOT NULL,
            settings_json TEXT NOT NULL,
            breakdown_json TEXT NOT NULL,
            final_price_gbp REAL NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    quote_columns = [
        row["name"]
        for row in conn.execute("PRAGMA table_info(commission_quotes)").fetchall()
    ]
    if "quote_type" not in quote_columns:
        cursor.execute(
            "ALTER TABLE commission_quotes ADD COLUMN quote_type TEXT NOT NULL DEFAULT 'quote'"
        )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS quote_stones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quote_id INTEGER NOT NULL,
            stone_id INTEGER NOT NULL,
            qty INTEGER NOT NULL,
            applied_markup_pct REAL NOT NULL,
            unit_cost_gbp REAL NOT NULL,
            FOREIGN KEY (quote_id) REFERENCES commission_quotes(id),
            FOREIGN KEY (stone_id) REFERENCES stones(id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS workshop_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            template_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS workshop_quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            template_name TEXT,
            inputs_json TEXT NOT NULL,
            breakdown_json TEXT NOT NULL,
            final_total_gbp REAL NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    for key, value in DEFAULT_SETTINGS.items():
        cursor.execute(
            """
            INSERT OR IGNORE INTO settings (key, value, updated_at)
            VALUES (?, ?, ?)
            """,
            (key, value, utc_now_iso()),
        )

    conn.commit()


def get_all_settings(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    raw = {row["key"]: row["value"] for row in rows}

    def get_float(key: str) -> float:
        try:
            return float(raw.get(key, DEFAULT_SETTINGS[key]))
        except (TypeError, ValueError):
            return float(DEFAULT_SETTINGS[key])

    return {
        "labour_rate_gbp_per_hr": get_float("labour_rate_gbp_per_hr"),
        "vat_enabled": raw.get("vat_enabled", DEFAULT_SETTINGS["vat_enabled"]) == "1",
        "vat_rate_pct": get_float("vat_rate_pct"),
        "commission_deposit_pct": get_float("commission_deposit_pct"),
        "estimate_variance_pct": get_float("estimate_variance_pct"),
        "estimate_valid_days": int(get_float("estimate_valid_days")),
        "metal_waste_pct": get_float("metal_waste_pct"),
        "overhead_pct": get_float("overhead_pct"),
        "target_profit_margin_pct": get_float("target_profit_margin_pct"),
        "troy_oz_to_grams": get_float("troy_oz_to_grams"),
        "price_cache_ttl_minutes": int(get_float("price_cache_ttl_minutes")),
    }


def save_settings(conn: sqlite3.Connection, settings: dict[str, Any]) -> None:
    now = utc_now_iso()
    payload = {
        "labour_rate_gbp_per_hr": str(settings["labour_rate_gbp_per_hr"]),
        "vat_enabled": "1" if settings["vat_enabled"] else "0",
        "vat_rate_pct": str(settings["vat_rate_pct"]),
        "commission_deposit_pct": str(settings["commission_deposit_pct"]),
        "estimate_variance_pct": str(settings["estimate_variance_pct"]),
        "estimate_valid_days": str(settings["estimate_valid_days"]),
        "metal_waste_pct": str(settings["metal_waste_pct"]),
        "overhead_pct": str(settings["overhead_pct"]),
        "target_profit_margin_pct": str(settings["target_profit_margin_pct"]),
        "troy_oz_to_grams": str(settings["troy_oz_to_grams"]),
        "price_cache_ttl_minutes": str(settings["price_cache_ttl_minutes"]),
    }

    for key, value in payload.items():
        conn.execute(
            """
            INSERT INTO settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (key, value, now),
        )
    conn.commit()


def get_cached_prices(conn: sqlite3.Connection, symbols: list[str]) -> dict[str, sqlite3.Row]:
    placeholders = ",".join("?" for _ in symbols)
    rows = conn.execute(
        f"SELECT symbol, price_gbp_per_oz, fetched_at, provider FROM metal_prices WHERE symbol IN ({placeholders})",
        symbols,
    ).fetchall()
    return {row["symbol"]: row for row in rows}


def save_price(conn: sqlite3.Connection, symbol: str, price_gbp_per_oz: float, provider: str) -> None:
    conn.execute(
        """
        INSERT INTO metal_prices (symbol, price_gbp_per_oz, fetched_at, provider)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(symbol)
        DO UPDATE SET
            price_gbp_per_oz = excluded.price_gbp_per_oz,
            fetched_at = excluded.fetched_at,
            provider = excluded.provider
        """,
        (symbol, price_gbp_per_oz, utc_now_iso(), provider),
    )
    conn.commit()


def is_price_fresh(fetched_at_iso: str, max_age_minutes: int) -> bool:
    try:
        fetched_at = datetime.fromisoformat(fetched_at_iso)
    except ValueError:
        return False
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - fetched_at <= timedelta(minutes=max_age_minutes)


def list_stones(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM stones ORDER BY stone_type, size_mm_or_carat, supplier"
    ).fetchall()


def add_stone(conn: sqlite3.Connection, stone: dict[str, Any]) -> None:
    now = utc_now_iso()
    conn.execute(
        """
        INSERT INTO stones
        (stone_type, size_mm_or_carat, grade, supplier, cost_gbp, default_markup_pct, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            stone["stone_type"],
            stone["size_mm_or_carat"],
            stone["grade"],
            stone["supplier"],
            stone["cost_gbp"],
            stone["default_markup_pct"],
            stone.get("notes", ""),
            now,
            now,
        ),
    )
    conn.commit()


def update_stone(conn: sqlite3.Connection, stone_id: int, stone: dict[str, Any]) -> None:
    conn.execute(
        """
        UPDATE stones
        SET stone_type = ?, size_mm_or_carat = ?, grade = ?, supplier = ?,
            cost_gbp = ?, default_markup_pct = ?, notes = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            stone["stone_type"],
            stone["size_mm_or_carat"],
            stone["grade"],
            stone["supplier"],
            stone["cost_gbp"],
            stone["default_markup_pct"],
            stone.get("notes", ""),
            utc_now_iso(),
            stone_id,
        ),
    )
    conn.commit()


def delete_stone(conn: sqlite3.Connection, stone_id: int) -> None:
    conn.execute("DELETE FROM stones WHERE id = ?", (stone_id,))
    conn.commit()


def import_stones_from_df(conn: sqlite3.Connection, df: Any) -> int:
    import pandas as pd

    required = [
        "stone_type",
        "size_mm_or_carat",
        "grade",
        "supplier",
        "cost_gbp",
        "default_markup_pct",
        "notes",
    ]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    inserted = 0
    for _, row in df.iterrows():
        add_stone(
            conn,
            {
                "stone_type": str(row["stone_type"]).strip(),
                "size_mm_or_carat": str(row["size_mm_or_carat"]).strip(),
                "grade": str(row["grade"]).strip(),
                "supplier": str(row["supplier"]).strip(),
                "cost_gbp": float(row["cost_gbp"]),
                "default_markup_pct": float(row["default_markup_pct"]),
                "notes": "" if pd.isna(row["notes"]) else str(row["notes"]),
            },
        )
        inserted += 1
    return inserted


def save_commission_quote(
    conn: sqlite3.Connection,
    quote_payload: dict[str, Any],
    stone_items: list[dict[str, Any]],
) -> int:
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO commission_quotes
        (customer_name, quote_type, metal_symbol, alloy_label, weight_grams, labour_hours, settings_json, breakdown_json, final_price_gbp, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            quote_payload.get("customer_name"),
            quote_payload.get("quote_type", "quote"),
            quote_payload["metal_symbol"],
            quote_payload.get("alloy_label", ""),
            quote_payload["weight_grams"],
            quote_payload["labour_hours"],
            json.dumps(quote_payload["settings_snapshot"]),
            json.dumps(quote_payload["breakdown"]),
            quote_payload["breakdown"]["final_price_gbp"],
            utc_now_iso(),
        ),
    )
    quote_id = cursor.lastrowid

    for item in stone_items:
        cursor.execute(
            """
            INSERT INTO quote_stones (quote_id, stone_id, qty, applied_markup_pct, unit_cost_gbp)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                quote_id,
                item["stone_id"],
                item["qty"],
                item["applied_markup_pct"],
                item["unit_cost_gbp"],
            ),
        )

    conn.commit()
    return int(quote_id)


def list_commission_quotes(conn: sqlite3.Connection, limit: int = 100) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT id, customer_name, quote_type, metal_symbol, final_price_gbp, created_at
        FROM commission_quotes
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def upsert_workshop_template(conn: sqlite3.Connection, name: str, template: dict[str, Any]) -> None:
    now = utc_now_iso()
    conn.execute(
        """
        INSERT INTO workshop_templates (name, template_json, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(name)
        DO UPDATE SET template_json = excluded.template_json, updated_at = excluded.updated_at
        """,
        (name, json.dumps(template), now, now),
    )
    conn.commit()


def list_workshop_templates(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM workshop_templates ORDER BY name").fetchall()


def delete_workshop_template(conn: sqlite3.Connection, template_id: int) -> None:
    conn.execute("DELETE FROM workshop_templates WHERE id = ?", (template_id,))
    conn.commit()


def save_workshop_quote(
    conn: sqlite3.Connection,
    template_name: str | None,
    inputs_payload: dict[str, Any],
    breakdown: dict[str, Any],
) -> int:
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO workshop_quotes (template_name, inputs_json, breakdown_json, final_total_gbp, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            template_name,
            json.dumps(inputs_payload),
            json.dumps(breakdown),
            breakdown["final_total_gbp"],
            utc_now_iso(),
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def list_workshop_quotes(conn: sqlite3.Connection, limit: int = 100) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT id, template_name, final_total_gbp, created_at
        FROM workshop_quotes
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
