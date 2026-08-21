from datetime import datetime
import math
import sqlite3

DB_NAME = "defects.db"


def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initializes the defects database table."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS defects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            defect_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            address TEXT,
            elevation REAL,
            is_flood_prone INTEGER,
            status TEXT DEFAULT 'Pending',
            reported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )
    conn.commit()
    conn.close()


def calculate_distance_meters(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """Calculates distance between two coordinates in meters using the Haversine formula."""
    R = 6371000  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def is_duplicate_complaint(
    lat: float, lon: float, threshold_meters: float = 15.0
) -> bool:
    """Checks if a defect was already reported within the threshold radius."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT latitude, longitude FROM defects")
    records = cursor.fetchall()
    conn.close()

    for record in records:
        dist = calculate_distance_meters(
            lat, lon, record["latitude"], record["longitude"]
        )
        if dist <= threshold_meters:
            return True
    return False


def insert_defect(
    defect_type: str,
    severity: str,
    lat: float,
    lon: float,
    address: str,
    elevation: float,
    is_flood_prone: bool,
) -> int:
    """Inserts a new defect record into the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO defects (defect_type, severity, latitude, longitude, address, elevation, is_flood_prone)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
        (
            defect_type,
            severity,
            lat,
            lon,
            address,
            elevation,
            1 if is_flood_prone else 0,
        ),
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return new_id


def get_all_defects():
    """Fetches all defect records."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM defects ORDER BY reported_at DESC")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


# Initialize database upon import
init_db()