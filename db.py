import sqlite3
import json

DB_FILE = "strava.db"


def get_connection():
    return sqlite3.connect(DB_FILE)


def init_db(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            strava_id INTEGER UNIQUE,
            name TEXT,
            type TEXT,
            sport_type TEXT,
            start_date TEXT,
            distance REAL,
            moving_time INTEGER,
            elapsed_time INTEGER,
            total_elevation_gain REAL,
            average_speed REAL,
            max_speed REAL,
            average_heartrate REAL,
            max_heartrate REAL,
            kudos_count INTEGER,
            raw_json TEXT
        )
    """)
    conn.commit()


def upsert_activity(conn, activity):
    conn.execute("""
        INSERT INTO activities (
            strava_id, name, type, sport_type, start_date,
            distance, moving_time, elapsed_time, total_elevation_gain,
            average_speed, max_speed, average_heartrate, max_heartrate,
            kudos_count, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(strava_id) DO UPDATE SET
            name=excluded.name,
            type=excluded.type,
            sport_type=excluded.sport_type,
            start_date=excluded.start_date,
            distance=excluded.distance,
            moving_time=excluded.moving_time,
            elapsed_time=excluded.elapsed_time,
            total_elevation_gain=excluded.total_elevation_gain,
            average_speed=excluded.average_speed,
            max_speed=excluded.max_speed,
            average_heartrate=excluded.average_heartrate,
            max_heartrate=excluded.max_heartrate,
            kudos_count=excluded.kudos_count,
            raw_json=excluded.raw_json
    """, (
        activity.get("id"),
        activity.get("name"),
        activity.get("type"),
        activity.get("sport_type"),
        activity.get("start_date"),
        activity.get("distance"),
        activity.get("moving_time"),
        activity.get("elapsed_time"),
        activity.get("total_elevation_gain"),
        activity.get("average_speed"),
        activity.get("max_speed"),
        activity.get("average_heartrate"),
        activity.get("max_heartrate"),
        activity.get("kudos_count"),
        json.dumps(activity),
    ))
    conn.commit()


def get_latest_timestamp(conn):
    row = conn.execute(
        "SELECT strftime('%s', MAX(start_date)) FROM activities"
    ).fetchone()
    return int(row[0]) if row and row[0] else None
