import time

class HLC:
    def __init__(self, ts: int, count: int, peer_id: str):
        self.ts = ts
        self.count = count
        self.peer_id = peer_id

    @classmethod
    def create_initial(cls, peer_id: str):
        """Creates the very first clock for a peer."""
        return cls(int(time.time() * 1000), 0, peer_id)

    def send(self) -> 'HLC':
        """Call this right BEFORE this peer writes an operation."""
        now = int(time.time() * 1000)
        if now > self.ts:
            self.ts = now
            self.count = 0
        else:
            # If events happen in the exact same millisecond, increment the counter
            self.count += 1
        return HLC(self.ts, self.count, self.peer_id)

    def receive(self, remote_hlc_str: str) -> 'HLC':
        """Call this when receiving an operation from another peer during sync."""
        remote = HLC.parse(remote_hlc_str)
        now = int(time.time() * 1000)
        
        # The new timestamp is the max of (local, remote, physical wall clock)
        new_ts = max(self.ts, remote.ts, now)
        
        if new_ts == self.ts and new_ts == remote.ts:
            self.count = max(self.count, remote.count) + 1
        elif new_ts == self.ts:
            self.count += 1
        elif new_ts == remote.ts:
            self.count = remote.count + 1
        else:
            self.count = 0
            
        self.ts = new_ts
        return HLC(self.ts, self.count, self.peer_id)

    def pack(self) -> str:
        """
        Formats the clock as a string: 'TIMESTAMP-COUNTER-PEERID'
        Zero-padded so SQLite can sort them perfectly using standard alphabetical sorting.
        """
        return f"{self.ts:015d}-{self.count:05d}-{self.peer_id}"

    @classmethod
    def parse(cls, hlc_str: str) -> 'HLC':
        parts = hlc_str.split('-')
        return cls(int(parts[0]), int(parts[1]), parts[2])