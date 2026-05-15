from adapter import Adapter
from engine import CRDTEngine

class Engine(Adapter):
    def __init__(self):
        # Maps peer_id -> CRDTEngine instance
        self.peers = {}

    def open_peer(self, peer_id):
        if peer_id not in self.peers:
            self.peers[peer_id] = CRDTEngine(peer_id)

    def apply_schema(self, peer_id, stmts):
        self.peers[peer_id].apply_schema(stmts)

    def execute(self, peer_id, sql, params=()):
        self.peers[peer_id].execute(sql, params)

    def sync(self, peer_a, peer_b):
        # Pairwise sync is symmetric and bidirectional per operational contract
        self.peers[peer_a].sync_with(self.peers[peer_b])
        self.peers[peer_b].sync_with(self.peers[peer_a])

    def snapshot_hash(self, peer_id):
        return self.peers[peer_id].snapshot_hash()

    def snapshot_state(self, peer_id):
        return self.peers[peer_id].materialize_state()

    def close(self):
        self.peers.clear()