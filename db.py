import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).with_name("shelf.db")


DEFAULT_DEVICE_STATE = {
    "power": "off",
    "brightness": "80",
    "color": "#ffffff",
    "whitebalance": "4000",
    "effect": "none",
    "speed": "50",
}

DEFAULT_SETTINGS = {
    "mqtt_host": "localhost",
    "mqtt_port": "1883",
    "led_count": "300",
    "max_brightness": "80",
    "startup_effect": "true",
}


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                time TEXT NOT NULL,
                action TEXT NOT NULL CHECK(action IN ('on', 'off')),
                enabled INTEGER NOT NULL DEFAULT 1,
                repeat_days TEXT NOT NULL DEFAULT 'daily',
                last_run_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS device_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )

        for key, value in DEFAULT_DEVICE_STATE.items():
            conn.execute(
                """
                INSERT OR IGNORE INTO device_state (key, value)
                VALUES (?, ?)
                """,
                (key, value),
            )

        for key, value in DEFAULT_SETTINGS.items():
            conn.execute(
                """
                INSERT OR IGNORE INTO settings (key, value)
                VALUES (?, ?)
                """,
                (key, value),
            )


def row_to_schedule(row):
    return {
        "id": row["id"],
        "time": row["time"],
        "action": row["action"],
        "enabled": bool(row["enabled"]),
        "repeat_days": row["repeat_days"],
        "last_run_at": row["last_run_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def get_schedules():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, time, action, enabled, repeat_days, last_run_at, created_at, updated_at
            FROM schedules
            ORDER BY time ASC, id ASC
            """
        ).fetchall()

    return [row_to_schedule(row) for row in rows]


def add_schedule(time, action, enabled=True, repeat_days="daily"):
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO schedules (time, action, enabled, repeat_days)
            VALUES (?, ?, ?, ?)
            """,
            (time, action, int(enabled), repeat_days),
        )
        row = conn.execute(
            """
            SELECT id, time, action, enabled, repeat_days, last_run_at, created_at, updated_at
            FROM schedules
            WHERE id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()

    return row_to_schedule(row)


def update_schedule(schedule_id, **changes):
    allowed_fields = {"time", "action", "enabled", "repeat_days", "last_run_at"}
    fields = [field for field in changes if field in allowed_fields]

    if not fields:
        return get_schedule(schedule_id)

    assignments = ", ".join(f"{field} = ?" for field in fields)
    values = [
        int(changes[field]) if field == "enabled" else changes[field]
        for field in fields
    ]
    values.append(schedule_id)

    with get_connection() as conn:
        conn.execute(
            f"""
            UPDATE schedules
            SET {assignments}, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            values,
        )

    return get_schedule(schedule_id)


def get_schedule(schedule_id):
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, time, action, enabled, repeat_days, last_run_at, created_at, updated_at
            FROM schedules
            WHERE id = ?
            """,
            (schedule_id,),
        ).fetchone()

    if row is None:
        return None

    return row_to_schedule(row)


def delete_schedule(schedule_id):
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM schedules WHERE id = ?",
            (schedule_id,),
        )

    return cursor.rowcount > 0


def get_device_state():
    with get_connection() as conn:
        rows = conn.execute("SELECT key, value FROM device_state").fetchall()

    return {row["key"]: row["value"] for row in rows}


def set_device_state(key, value):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO device_state (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, str(value)),
        )


def set_device_state_many(values):
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO device_state (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            [(key, str(value)) for key, value in values.items()],
        )


def get_settings():
    with get_connection() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()

    settings = dict(DEFAULT_SETTINGS)
    settings.update({row["key"]: row["value"] for row in rows})
    return settings


def set_settings(values):
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            [(key, str(value)) for key, value in values.items()],
        )

    return get_settings()
