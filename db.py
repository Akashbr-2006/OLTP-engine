import sqlite3
import os

class CRDTDatabase:
    def __init__(self, db_path: str):
        self.db_path = db_path
        # We use check_same_thread=False so our test scripts don't complain
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        # Return rows as dictionaries for easier handling later
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        cursor = self.conn.cursor()
        
        # --- 1. THE REFERENCE SCHEMA (From the Hackathon Prompt) ---
        # Note: We keep the exact schema they requested.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id    TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                name  TEXT
            );
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id          TEXT PRIMARY KEY,
                user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                status      TEXT NOT NULL,
                total_cents INTEGER NOT NULL DEFAULT 0
            );
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS orders_by_user ON orders(user_id, status);")

        # --- 2. THE CRDT SHADOW TABLES (Our Secret Weapon) ---
        
        # The Op-Log: Stores the highest HLC for every single cell
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS crr_log (
                table_name  TEXT,
                row_id      TEXT,
                column_name TEXT,
                value       TEXT,  -- We store all values as strings in the log
                hlc         TEXT,
                PRIMARY KEY (table_name, row_id, column_name)
            );
        """)

        # Tombstones: Satisfies the FK policy. When a parent is deleted, it goes here.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS crr_tombstones (
                table_name     TEXT,
                row_id         TEXT,
                deleted_at_hlc TEXT,
                PRIMARY KEY (table_name, row_id)
            );
        """)

        # Conflicts: Satisfies the Uniqueness policy. Losers of the email battle go here.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS crr_conflicts (
                table_name   TEXT,
                column_name  TEXT,
                value        TEXT,
                loser_row_id TEXT,
                hlc          TEXT,
                PRIMARY KEY (table_name, column_name, loser_row_id)
            );
        """)

        self.conn.commit()

    def query(self, sql: str, params: tuple = ()):
        """Helper to run a query and fetch results."""
        cursor = self.conn.cursor()
        cursor.execute(sql, params)
        return cursor.fetchall()
        
    def close(self):
        self.conn.close()

    def clear_db(self):
        """Helper to wipe the DB for fresh tests."""
        self.conn.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)