import sqlite3
import os
import cv2
import time
import io
import csv
import logging
from datetime import datetime
from pathlib import Path
from src.config.settings import get_settings


class Database:
    def __init__(self, db_path: str = None):
        settings = get_settings()
        self.db_path = db_path or settings.db_file
        self.snapshots_dir = settings.snapshots_dir
        os.makedirs(self.snapshots_dir, exist_ok=True)
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS detection_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    camera_name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    label TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    speed_kmh REAL,
                    plate_text TEXT,
                    snapshot_filename TEXT,
                    motion_flag INTEGER DEFAULT 0
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON detection_events(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_camera ON detection_events(camera_name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_category ON detection_events(category)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_plate ON detection_events(plate_text)")
            conn.commit()

    def insert_event(self, camera_name: str, category: str, label: str,
                     confidence: float, speed_kmh: float = None,
                     plate_text: str = None, frame_crop=None,
                     motion_flag: bool = False) -> int:
        snapshot_filename = None
        if frame_crop is not None and frame_crop.size > 0:
            try:
                now_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                clean_cam = camera_name.replace(" ", "_").lower()
                snapshot_filename = f"snap_{clean_cam}_{category}_{now_str}.jpg"
                full_path = os.path.join(self.snapshots_dir, snapshot_filename)
                cv2.imwrite(full_path, frame_crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
            except Exception as e:
                logging.error(f"Failed to save snapshot: {e}")
                snapshot_filename = None

        now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO detection_events (
                    timestamp, camera_name, category, label, confidence,
                    speed_kmh, plate_text, snapshot_filename, motion_flag
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                now_iso, camera_name, category, label, round(confidence, 3),
                round(speed_kmh, 1) if speed_kmh is not None else None,
                plate_text if plate_text else None,
                snapshot_filename,
                1 if motion_flag else 0
            ))
            conn.commit()
            return cursor.lastrowid

    def get_events(self, camera=None, category=None, start_time=None,
                   end_time=None, plate=None, min_speed=None,
                   page=1, per_page=25):
        query = "SELECT * FROM detection_events WHERE 1=1"
        params = []

        if camera:
            query += " AND camera_name = ?"
            params.append(camera)
        if category and category != "all":
            query += " AND category = ?"
            params.append(category)
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time)
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time)
        if plate:
            query += " AND plate_text LIKE ?"
            params.append(f"%{plate}%")
        if min_speed is not None and min_speed != "":
            try:
                ms = float(min_speed)
                query += " AND speed_kmh >= ?"
                params.append(ms)
            except ValueError:
                pass

        count_query = f"SELECT COUNT(*) as total FROM ({query})"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(count_query, params)
            total = cursor.fetchone()["total"]

            query += " ORDER BY id DESC LIMIT ? OFFSET ?"
            offset = (page - 1) * per_page
            params.extend([per_page, offset])

            cursor.execute(query, params)
            rows = [dict(r) for r in cursor.fetchall()]

        total_pages = max(1, (total + per_page - 1) // per_page)
        return {
            "events": rows,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages
        }

    def get_stats(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Total events
            cursor.execute("SELECT COUNT(*) as total FROM detection_events")
            total_events = cursor.fetchone()["total"]

            # Counts by category
            cursor.execute("SELECT category, COUNT(*) as count FROM detection_events GROUP BY category")
            category_counts = {r["category"]: r["count"] for r in cursor.fetchall()}

            # Counts by camera
            cursor.execute("SELECT camera_name, COUNT(*) as count FROM detection_events GROUP BY camera_name")
            camera_counts = {r["camera_name"]: r["count"] for r in cursor.fetchall()}

            # Max & Average speed
            cursor.execute("SELECT AVG(speed_kmh) as avg_speed, MAX(speed_kmh) as max_speed FROM detection_events WHERE speed_kmh IS NOT NULL")
            speed_row = cursor.fetchone()
            avg_speed = round(speed_row["avg_speed"], 1) if speed_row["avg_speed"] else 0
            max_speed = round(speed_row["max_speed"], 1) if speed_row["max_speed"] else 0

            # Plate count
            cursor.execute("SELECT COUNT(*) as plate_count FROM detection_events WHERE plate_text IS NOT NULL AND plate_text != ''")
            plate_count = cursor.fetchone()["plate_count"]

            # Recent 24h count
            cursor.execute("SELECT COUNT(*) as recent_24h FROM detection_events WHERE timestamp >= datetime('now', '-1 day')")
            recent_24h = cursor.fetchone()["recent_24h"]

            # Hourly distribution for today
            cursor.execute("""
                SELECT strftime('%H:00', timestamp) as hour, COUNT(*) as count
                FROM detection_events
                WHERE timestamp >= date('now')
                GROUP BY hour
                ORDER BY hour ASC
            """)
            hourly_stats = {r["hour"]: r["count"] for r in cursor.fetchall()}

        return {
            "total_events": total_events,
            "person_count": category_counts.get("person", 0),
            "vehicle_count": category_counts.get("vehicle", 0),
            "category_counts": category_counts,
            "camera_counts": camera_counts,
            "avg_speed": avg_speed,
            "max_speed": max_speed,
            "plate_count": plate_count,
            "recent_24h": recent_24h,
            "hourly_stats": hourly_stats
        }

    def export_csv(self, camera=None, category=None, start_time=None, end_time=None, plate=None, min_speed=None) -> str:
        # Fetch all matching rows
        query = "SELECT id, timestamp, camera_name, category, label, confidence, speed_kmh, plate_text, snapshot_filename FROM detection_events WHERE 1=1"
        params = []
        if camera:
            query += " AND camera_name = ?"
            params.append(camera)
        if category and category != "all":
            query += " AND category = ?"
            params.append(category)
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time)
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time)
        if plate:
            query += " AND plate_text LIKE ?"
            params.append(f"%{plate}%")
        if min_speed is not None and min_speed != "":
            try:
                ms = float(min_speed)
                query += " AND speed_kmh >= ?"
                params.append(ms)
            except ValueError:
                pass

        query += " ORDER BY id DESC"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID", "Timestamp", "Camera", "Category", "Label", "Confidence", "Speed (km/h)", "License Plate", "Snapshot File"])
        for r in rows:
            writer.writerow([
                r["id"], r["timestamp"], r["camera_name"], r["category"],
                r["label"], r["confidence"],
                r["speed_kmh"] if r["speed_kmh"] is not None else "",
                r["plate_text"] if r["plate_text"] else "",
                r["snapshot_filename"] if r["snapshot_filename"] else ""
            ])
        return output.getvalue()


    def delete_event(self, event_id: int) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT snapshot_filename FROM detection_events WHERE id = ?", (event_id,))
            row = cursor.fetchone()
            if not row:
                return False

            snapshot_file = row["snapshot_filename"]
            if snapshot_file:
                try:
                    fpath = os.path.join(self.snapshots_dir, snapshot_file)
                    if os.path.exists(fpath):
                        os.remove(fpath)
                except Exception as e:
                    logging.warning(f"Error removing snapshot file {snapshot_file}: {e}")

            cursor.execute("DELETE FROM detection_events WHERE id = ?", (event_id,))
            conn.commit()
            return cursor.rowcount > 0

    def delete_all_events(self) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT snapshot_filename FROM detection_events")
            rows = cursor.fetchall()

            for r in rows:
                snap = r["snapshot_filename"]
                if snap:
                    try:
                        fpath = os.path.join(self.snapshots_dir, snap)
                        if os.path.exists(fpath):
                            os.remove(fpath)
                    except Exception as e:
                        logging.warning(f"Error removing snapshot {snap}: {e}")

            cursor.execute("DELETE FROM detection_events")
            count = cursor.rowcount
            conn.commit()
            return count


_db_instance = None


def get_db() -> Database:
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
    return _db_instance

