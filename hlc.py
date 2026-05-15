import time

class HLC:
    """
    Hybrid Logical Clock.
    Guarantees a mathematically absolute order of events in a distributed system.
    """
    def __init__(self, ts=0, count=0, node_id="0"):
        self.ts = ts          
        self.count = count    
        self.node_id = str(node_id) 

    @classmethod
    def create_initial(cls, node_id: str):
        return cls(int(time.time() * 1000), 0, str(node_id))

    def send(self):
        """Advances the clock for a new local event."""
        now = int(time.time() * 1000)
        if now > self.ts:
            self.ts = now
            self.count = 0
        else:
            self.count += 1
        return HLC(self.ts, self.count, self.node_id)

    # --- CRDT Math: Lexicographical Ordering Rules ---
    def __lt__(self, other: 'HLC') -> bool:
        if self.ts == other.ts:
            if self.count == other.count:
                return self.node_id < other.node_id # Deterministic Tie-breaker
            return self.count < other.count
        return self.ts < other.ts

    def __eq__(self, other: 'HLC') -> bool:
        if not isinstance(other, HLC): return False
        return self.ts == other.ts and self.count == other.count and self.node_id == other.node_id

    def __gt__(self, other: 'HLC') -> bool:
        return not (self.__lt__(other) or self.__eq__(other))
        
    def __ge__(self, other: 'HLC') -> bool:
        return not self.__lt__(other)