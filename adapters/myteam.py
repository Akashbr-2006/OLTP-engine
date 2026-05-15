import os
import sqlite3
# Adjust these imports if your files are in a parent directory
from engine import CRDTEngine

# Mocking the base Adapter class just in case the bench doesn't expose it perfectly here
class Adapter:
    pass 

class Engine(Adapter):
    def __init__(self):
        self.peers = {}  # peer_id -> CRDTEngine instance

    def open_peer(self, peer_id: str):
        """Called by the bench to spin up a new offline laptop."""
        # Use a unique DB file for each peer during the test
        db_path = f"bench_peer_{peer_id}.db"
        if os.path.exists(db_path):
            os.remove(db_path)
            
        self.peers[peer_id] = CRDTEngine(peer_id, db_path)

    def apply_schema(self, peer_id: str, stmts: list):
        """Called by the bench to set up the tables."""
        cursor = self.peers[peer_id].db.conn.cursor()
        for stmt in stmts:
            try:
                cursor.execute(stmt)
            except sqlite3.OperationalError as e:
                # The harness tries to create tables we already created in db.py. 
                # If it's just an "already exists" error, we safely ignore it.
                if "already exists" in str(e).lower():
                    pass
                else:
                    raise e
        self.peers[peer_id].db.conn.commit()

    def execute(self, peer_id: str, sql: str, params=()):
        """Called by the bench to run an INSERT/UPDATE/DELETE."""
        self.peers[peer_id].execute(sql, params)

    def sync(self, peer_a: str, peer_b: str):
        """Called by the bench to connect two offline laptops."""
        self.peers[peer_a].sync_with(self.peers[peer_b])

    def snapshot_hash(self, peer_id: str) -> str:
        """Called by the bench to verify determinism."""
        return self.peers[peer_id].snapshot_hash()

    def snapshot_state(self, peer_id: str) -> dict:
        """Called by the bench to inspect the actual data."""
        users = [dict(row) for row in self.peers[peer_id].db.query("SELECT * FROM users ORDER BY id")]
        orders = [dict(row) for row in self.peers[peer_id].db.query("SELECT * FROM orders ORDER BY id")]
        return {"users": users, "orders": orders}

    def close(self):
        """Called by the bench at the very end to clean up."""
        for p_id, engine_instance in self.peers.items():
            db_path = engine_instance.db.db_path
            engine_instance.db.close()
            # Clean up the test files
            if os.path.exists(db_path):
                try:
                    os.remove(db_path)
                except:
                    pass
        self.peers.clear()