"""
db_adapter.py — Database Abstraction Layer

Modul ini menyediakan interface yang seragam untuk operasi database,
sehingga aplikasi dapat beralih antara Supabase dan PostgreSQL langsung
hanya dengan mengubah variabel DB_PROVIDER di file .env.

Penggunaan:
    from db_adapter import get_db_adapter
    db = get_db_adapter()
    db.insert_detection({...})
"""

import os
import abc
from datetime import datetime
from typing import Optional


# ==============================================================================
# ABSTRACT BASE CLASS
# ==============================================================================

class DatabaseAdapter(abc.ABC):
    """Interface standar untuk semua database adapter."""

    @abc.abstractmethod
    def insert_detection(self, data: dict) -> None:
        """
        Menyimpan satu record deteksi ke database.

        Args:
            data: dict dengan keys:
                - frame_time (str)
                - frame_number (int)
                - object_name (str)
                - confidence (float)
                - tracking_id (int | None)
                - timestamp (str, ISO format)
                - image_path (str)
        """
        pass

    @abc.abstractmethod
    def get_detections(
        self,
        page: int = 1,
        per_page: int = 20,
        object_filter: Optional[str] = None,
        date_filter: Optional[str] = None,
    ) -> tuple:
        """
        Mengambil data deteksi dengan pagination dan filter opsional.

        Returns:
            tuple: (list[dict], total_count: int)
        """
        pass

    @abc.abstractmethod
    def get_all_detections_stats(self) -> list:
        """
        Mengambil semua data deteksi (kecuali 'lost_object') untuk kalkulasi statistik.

        Returns:
            list[dict]
        """
        pass

    @abc.abstractmethod
    def upload_image(self, filename: str, local_path: str) -> str:
        """
        Mengunggah gambar ke storage dan mengembalikan URL yang dapat diakses publik.

        Args:
            filename: Nama file (misal: "violation_100_1_1234567890.jpg")
            local_path: Path absolut ke file lokal

        Returns:
            str: URL publik gambar (cloud URL atau local path URL)
        """
        pass


# ==============================================================================
# SUPABASE ADAPTER
# ==============================================================================

class SupabaseAdapter(DatabaseAdapter):
    """
    Adapter untuk Supabase.
    Menggunakan supabase-py untuk operasi tabel dan Supabase Storage untuk gambar.
    """

    def __init__(self, url: str, key: str):
        try:
            from supabase import create_client
            self.client = create_client(url, key)
            print("[DB] Menggunakan Supabase sebagai database.")
        except ImportError:
            raise ImportError(
                "Library 'supabase' tidak ditemukan. "
                "Install dengan: pip install supabase"
            )

    def insert_detection(self, data: dict) -> None:
        self.client.table("detections").insert(data).execute()

    def get_detections(
        self,
        page: int = 1,
        per_page: int = 20,
        object_filter: Optional[str] = None,
        date_filter: Optional[str] = None,
    ) -> tuple:
        offset = (page - 1) * per_page
        query = (
            self.client.table("detections")
            .select("*", count="exact")
            .order("timestamp", desc=True)
        )
        if object_filter:
            query = query.eq("object_name", object_filter)
        if date_filter:
            query = query.gte("timestamp", f"{date_filter}T00:00:00").lte(
                "timestamp", f"{date_filter}T23:59:59"
            )
        query = query.range(offset, offset + per_page - 1)
        result = query.execute()
        return result.data, result.count

    def get_all_detections_stats(self) -> list:
        result = (
            self.client.table("detections")
            .select("*")
            .neq("object_name", "lost_object")
            .execute()
        )
        return result.data

    def upload_image(self, filename: str, local_path: str) -> str:
        """Upload ke Supabase Storage bucket 'violations', return public URL."""
        with open(local_path, "rb") as f:
            self.client.storage.from_("violations").upload(
                filename, f, {"content-type": "image/jpeg"}
            )
        public_url = self.client.storage.from_("violations").get_public_url(filename)
        return public_url


# ==============================================================================
# POSTGRESQL ADAPTER
# ==============================================================================

class PostgreSQLAdapter(DatabaseAdapter):
    """
    Adapter untuk PostgreSQL self-hosted.
    Menggunakan psycopg2 untuk operasi database.
    Gambar disimpan lokal di folder 'violations/' dan dilayani oleh Flask.
    Auto-migrate: tabel 'detections' dibuat otomatis jika belum ada.
    """

    def __init__(self, database_url: str):
        try:
            import psycopg2
            import psycopg2.extras
            self.psycopg2 = psycopg2
            self.extras = psycopg2.extras
        except ImportError:
            raise ImportError(
                "Library 'psycopg2' tidak ditemukan. "
                "Install dengan: pip install psycopg2-binary"
            )

        self.database_url = database_url
        print("[DB] Menggunakan PostgreSQL sebagai database.")
        self._auto_migrate()

    def _get_connection(self):
        """Membuat koneksi baru ke PostgreSQL."""
        return self.psycopg2.connect(self.database_url)

    def _auto_migrate(self) -> None:
        """
        Membuat tabel 'detections' secara otomatis jika belum ada.
        Aman untuk dipanggil berulang kali (idempotent).
        """
        create_table_sql = """
            CREATE TABLE IF NOT EXISTS detections (
                id          BIGSERIAL PRIMARY KEY,
                frame_time  TEXT NOT NULL,
                frame_number INTEGER NOT NULL,
                object_name TEXT NOT NULL,
                confidence  FLOAT NOT NULL,
                tracking_id INTEGER,
                timestamp   TIMESTAMPTZ DEFAULT NOW(),
                image_path  TEXT
            );
        """
        try:
            conn = self._get_connection()
            with conn:
                with conn.cursor() as cur:
                    cur.execute(create_table_sql)
            conn.close()
            print("[DB] Auto-migrate selesai: tabel 'detections' siap.")
        except Exception as e:
            print(f"[DB] PERINGATAN: Gagal auto-migrate — {e}")

    def insert_detection(self, data: dict) -> None:
        sql = """
            INSERT INTO detections
                (frame_time, frame_number, object_name, confidence, tracking_id, timestamp, image_path)
            VALUES
                (%(frame_time)s, %(frame_number)s, %(object_name)s, %(confidence)s,
                 %(tracking_id)s, %(timestamp)s, %(image_path)s)
        """
        conn = self._get_connection()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(sql, data)
        finally:
            conn.close()

    def get_detections(
        self,
        page: int = 1,
        per_page: int = 20,
        object_filter: Optional[str] = None,
        date_filter: Optional[str] = None,
    ) -> tuple:
        conditions = []
        params: list = []

        if object_filter:
            conditions.append("object_name = %s")
            params.append(object_filter)
        if date_filter:
            conditions.append("timestamp >= %s AND timestamp <= %s")
            params.append(f"{date_filter} 00:00:00+00")
            params.append(f"{date_filter} 23:59:59+00")

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        offset = (page - 1) * per_page

        count_sql = f"SELECT COUNT(*) FROM detections {where_clause}"
        data_sql = f"""
            SELECT id, frame_time, frame_number, object_name, confidence,
                   tracking_id, timestamp, image_path
            FROM detections
            {where_clause}
            ORDER BY timestamp DESC
            LIMIT %s OFFSET %s
        """

        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=self.extras.RealDictCursor) as cur:
                # Hitung total record
                cur.execute(count_sql, params)
                total_count = cur.fetchone()["count"]

                # Ambil data dengan pagination
                cur.execute(data_sql, params + [per_page, offset])
                rows = cur.fetchall()

            # Konversi ke list of dict dan pastikan timestamp dalam format string ISO
            result = []
            for row in rows:
                row_dict = dict(row)
                if row_dict.get("timestamp") and hasattr(row_dict["timestamp"], "isoformat"):
                    row_dict["timestamp"] = row_dict["timestamp"].isoformat()
                result.append(row_dict)

            return result, int(total_count)
        finally:
            conn.close()

    def get_all_detections_stats(self) -> list:
        sql = """
            SELECT id, frame_time, frame_number, object_name, confidence,
                   tracking_id, timestamp, image_path
            FROM detections
            WHERE object_name != 'lost_object'
            ORDER BY timestamp DESC
        """
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=self.extras.RealDictCursor) as cur:
                cur.execute(sql)
                rows = cur.fetchall()

            result = []
            for row in rows:
                row_dict = dict(row)
                if row_dict.get("timestamp") and hasattr(row_dict["timestamp"], "isoformat"):
                    row_dict["timestamp"] = row_dict["timestamp"].isoformat()
                result.append(row_dict)

            return result
        finally:
            conn.close()

    def upload_image(self, filename: str, local_path: str) -> str:
        """
        Mode PostgreSQL tidak menggunakan cloud storage.
        Gambar sudah disimpan lokal, cukup return URL endpoint Flask.
        """
        return f"/violations/{filename}"


# ==============================================================================
# FACTORY FUNCTION
# ==============================================================================

def get_db_adapter() -> DatabaseAdapter:
    """
    Factory function yang membaca DB_PROVIDER dari environment variable
    dan mengembalikan adapter database yang sesuai.

    Variabel .env yang dibutuhkan:
        DB_PROVIDER     : "supabase" (default) atau "postgresql"

        Jika DB_PROVIDER=supabase:
            SUPABASE_URL : URL project Supabase
            SUPABASE_KEY : API key Supabase (anon atau service role)

        Jika DB_PROVIDER=postgresql:
            DATABASE_URL : Connection string PostgreSQL
                           Contoh: postgresql://user:pass@localhost:5432/dbname

    Returns:
        DatabaseAdapter: Instance dari SupabaseAdapter atau PostgreSQLAdapter.
    """
    provider = os.getenv("DB_PROVIDER", "supabase").strip().lower()

    if provider == "postgresql":
        database_url = os.getenv("DATABASE_URL", "")
        if not database_url:
            raise ValueError(
                "[DB] ERROR: DB_PROVIDER=postgresql tapi DATABASE_URL belum diset di .env!\n"
                "Contoh: DATABASE_URL=postgresql://postgres:password@localhost:5432/lab_violations"
            )
        return PostgreSQLAdapter(database_url)

    elif provider == "supabase":
        supabase_url = os.getenv("SUPABASE_URL", "")
        supabase_key = os.getenv("SUPABASE_KEY", "")
        if not supabase_url or not supabase_key:
            print(
                "[DB] WARNING: SUPABASE_URL atau SUPABASE_KEY belum diset di .env! "
                "Operasi database akan gagal."
            )
        return SupabaseAdapter(supabase_url, supabase_key)

    else:
        raise ValueError(
            f"[DB] ERROR: DB_PROVIDER='{provider}' tidak dikenal. "
            "Gunakan 'supabase' atau 'postgresql'."
        )
