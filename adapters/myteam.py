from engine import CRDTEngine

class Engine:
    """
    The Adapter required by the Hackathon Benchmark Harness.
    Routes harness commands to our pure in-memory CRDT Engine.
    """
    def __init__(self):
        self.peers = {}

    def open_peer(self, peer_id: str):
        # V2: No SQLite database path needed anymore! Pure RAM.
        self.peers[peer_id] = CRDTEngine(peer_id)

    def apply_schema(self, peer_id: str, schema_ddl: list):
        # Route DDL directly to the CRDT initializer
        self.peers[peer_id].apply_schema(schema_ddl)

    def execute(self, peer_id: str, query: str, params: tuple = ()):
        # Route DML directly to our pure Python parser
        self.peers[peer_id].execute(query, params)

    def sync(self, peer_a: str, peer_b: str):
        # Two-way sync to simulate full partition healing
        self.peers[peer_a].sync_with(self.peers[peer_b])
        self.peers[peer_b].sync_with(self.peers[peer_a])

    def snapshot_hash(self, peer_id: str) -> str:
        return self.peers[peer_id].snapshot_hash()

    def snapshot_state(self, peer_id: str) -> dict: # <--- FIXED THIS NAME
        return self.peers[peer_id].materialize_state()

    def close(self):
        # V2: Since we are entirely in-memory, there are no temporary 
        # bench_peer_*.db files left to delete! Instant cleanup.
        self.peers.clear()