import os
import json
import sqlite3
import time
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import asdict

from .models import ComponentInfo


logger = logging.getLogger(__name__)


class CacheManager:

    DEFAULT_EXPIRY_SECONDS = 7 * 24 * 60 * 60

    def __init__(self, cache_dir: Optional[str] = None):
        if cache_dir is None:
            cache_dir = os.path.join(
                os.path.expanduser("~"),
                ".lcsc_grabber",
                "cache"
            )

        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.db_path = self.cache_dir / "components.db"
        self._init_database()

    def _init_database(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS components (
                    lcsc_id TEXT PRIMARY KEY,
                    mpn TEXT,
                    manufacturer TEXT,
                    description TEXT,
                    datasheet_url TEXT,
                    package TEXT,
                    category TEXT,
                    stock INTEGER,
                    price REAL,
                    image_url TEXT,
                    symbol_data TEXT,
                    footprint_data TEXT,
                    model_3d_uuid TEXT,
                    cached_at INTEGER,
                    last_accessed INTEGER
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS search_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT,
                    timestamp INTEGER
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_cached_at
                ON components(cached_at)
            """)

            conn.commit()

    def get_component(self, lcsc_id: str) -> Optional[ComponentInfo]:
        lcsc_id = lcsc_id.upper()

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM components WHERE lcsc_id = ?",
                (lcsc_id,)
            )
            row = cursor.fetchone()

            if row is None:
                return None

            cached_at = row["cached_at"]
            if time.time() - cached_at > self.DEFAULT_EXPIRY_SECONDS:
                logger.info(f"Cache expired for {lcsc_id}")
                return None

            conn.execute(
                "UPDATE components SET last_accessed = ? WHERE lcsc_id = ?",
                (int(time.time()), lcsc_id)
            )

            component = ComponentInfo(
                lcsc_id=row["lcsc_id"],
                mpn=row["mpn"] or "",
                manufacturer=row["manufacturer"] or "",
                description=row["description"] or "",
                datasheet_url=row["datasheet_url"] or "",
                package=row["package"] or "",
                category=row["category"] or "",
                stock=row["stock"] or 0,
                price=row["price"] or 0.0,
                image_url=row["image_url"] or "",
            )

            if row["symbol_data"]:
                try:
                    component.symbol_data = json.loads(row["symbol_data"])
                except json.JSONDecodeError:
                    pass

            if row["footprint_data"]:
                try:
                    component.footprint_data = json.loads(row["footprint_data"])
                except json.JSONDecodeError:
                    pass

            if row["model_3d_uuid"]:
                component.model_3d_uuid = row["model_3d_uuid"]

            logger.info(f"Cache hit for {lcsc_id}")
            return component

    def put_component(self, component: ComponentInfo):
        now = int(time.time())

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO components (
                    lcsc_id, mpn, manufacturer, description, datasheet_url,
                    package, category, stock, price, image_url,
                    symbol_data, footprint_data, model_3d_uuid,
                    cached_at, last_accessed
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                component.lcsc_id.upper(),
                component.mpn,
                component.manufacturer,
                component.description,
                component.datasheet_url,
                component.package,
                component.category,
                component.stock,
                component.price,
                component.image_url,
                json.dumps(component.symbol_data) if component.symbol_data else None,
                json.dumps(component.footprint_data) if component.footprint_data else None,
                component.model_3d_uuid,
                now,
                now
            ))
            conn.commit()

        logger.info(f"Cached component {component.lcsc_id}")

    def delete_component(self, lcsc_id: str):
        lcsc_id = lcsc_id.upper()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM components WHERE lcsc_id = ?",
                (lcsc_id,)
            )
            conn.commit()

        self._delete_cached_files(lcsc_id)

        logger.info(f"Deleted cached component {lcsc_id}")

    def _delete_cached_files(self, lcsc_id: str):
        for ext in [".step", ".wrl", ".obj"]:
            file_path = self.cache_dir / f"{lcsc_id}{ext}"
            if file_path.exists():
                file_path.unlink()

    def clear_expired(self):
        cutoff = int(time.time()) - self.DEFAULT_EXPIRY_SECONDS

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT lcsc_id FROM components WHERE cached_at < ?",
                (cutoff,)
            )
            expired = [row[0] for row in cursor.fetchall()]

            conn.execute(
                "DELETE FROM components WHERE cached_at < ?",
                (cutoff,)
            )
            conn.commit()

        for lcsc_id in expired:
            self._delete_cached_files(lcsc_id)

        logger.info(f"Cleared {len(expired)} expired cache entries")

    def clear_all(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM components")
            conn.execute("DELETE FROM search_history")
            conn.commit()

        for file_path in self.cache_dir.iterdir():
            if file_path.suffix in [".step", ".wrl", ".obj"]:
                file_path.unlink()

        logger.info("Cleared entire cache")

    def get_cache_stats(self) -> Dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM components")
            total = cursor.fetchone()[0]

            cutoff = int(time.time()) - self.DEFAULT_EXPIRY_SECONDS
            cursor = conn.execute(
                "SELECT COUNT(*) FROM components WHERE cached_at < ?",
                (cutoff,)
            )
            expired = cursor.fetchone()[0]

            cache_size = sum(
                f.stat().st_size
                for f in self.cache_dir.iterdir()
                if f.is_file()
            )

        return {
            "total_components": total,
            "expired_components": expired,
            "cache_size_bytes": cache_size,
            "cache_dir": str(self.cache_dir)
        }

    def add_search_history(self, query: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO search_history (query, timestamp) VALUES (?, ?)",
                (query, int(time.time()))
            )

            conn.execute("""
                DELETE FROM search_history
                WHERE id NOT IN (
                    SELECT id FROM search_history
                    ORDER BY timestamp DESC
                    LIMIT 50
                )
            """)
            conn.commit()

    def get_search_history(self, limit: int = 10) -> List[str]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT DISTINCT query FROM search_history
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,)
            )
            return [row[0] for row in cursor.fetchall()]

    def save_3d_model(
        self,
        lcsc_id: str,
        step_data: Optional[bytes] = None,
        obj_data: Optional[str] = None
    ) -> Optional[str]:
        lcsc_id = lcsc_id.upper()
        saved_path = None

        if step_data:
            step_path = self.cache_dir / f"{lcsc_id}.step"
            step_path.write_bytes(step_data)
            saved_path = str(step_path)
            logger.info(f"Saved STEP model: {step_path}")

        if obj_data:
            obj_path = self.cache_dir / f"{lcsc_id}.obj"
            obj_path.write_text(obj_data, encoding="utf-8")
            logger.info(f"Saved OBJ model: {obj_path}")

        return saved_path

    def get_3d_model_path(self, lcsc_id: str) -> Optional[str]:
        lcsc_id = lcsc_id.upper()

        step_path = self.cache_dir / f"{lcsc_id}.step"
        if step_path.exists():
            return str(step_path)

        return None


_default_cache: Optional[CacheManager] = None


def get_cache() -> CacheManager:
    global _default_cache
    if _default_cache is None:
        _default_cache = CacheManager()
    return _default_cache
