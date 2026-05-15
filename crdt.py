import collections
from hlc import HLC

class MVRegister:
    """Multi-Value Register: Preserves concurrent history at the cell level."""
    def __init__(self):
        self.variants = {} # peer_id -> (value, hlc)

    def assign(self, peer_id, value, hlc):
        if peer_id not in self.variants or hlc > self.variants[peer_id][1]:
            self.variants[peer_id] = (value, hlc)

    def merge(self, other: 'MVRegister'):
        for p_id, (val, hlc) in other.variants.items():
            if p_id not in self.variants or hlc > self.variants[p_id][1]:
                self.variants[p_id] = (val, hlc)

    def resolve(self):
        if not self.variants: return None
        # Deterministic winner based on lexicographical Peer ID
        winner_peer = sorted(self.variants.keys())[0]
        return self.variants[winner_peer][0]

class ORSet:
    """
    Observed-Remove Set (OR-Set).
    Tracks existence with causal history by converting HLCs to hashable strings.
    """
    def __init__(self):
        self.add_set = collections.defaultdict(set)
        self.remove_set = collections.defaultdict(set)

    def add(self, element, hlc):
        # STR(HLC) makes it hashable for the Python set!
        self.add_set[element].add(str(hlc))

    def remove(self, element, hlc):
        if element in self.add_set:
            # Tombstone all current additions by capturing their string states
            self.remove_set[element].update(self.add_set[element])

    def merge(self, other: 'ORSet'):
        for elem, hlcs in other.add_set.items():
            self.add_set[elem].update(hlcs)
        for elem, hlcs in other.remove_set.items():
            self.remove_set[elem].update(hlcs)

    def contains(self, element):
        adds = self.add_set.get(element, set())
        removes = self.remove_set.get(element, set())
        # If there's an addition that hasn't been tombstoned by a removal
        return any(a not in removes for a in adds)

class EscrowLedger:
    """
    Two-Phase Reservation Protocol.
    Optimized for O(1) lookups to survive high-parameter chaos tests.
    """
    def __init__(self):
        # Maps: resource -> (peer_id, hlc_object)
        self.claims = {}
        # Maps: resource -> set of unique tuples (peer_id, hlc_string)
        self.conflicts = collections.defaultdict(set)

    def claim(self, resource: str, peer_id: str, hlc: HLC):
        peer_id_str = str(peer_id)
        hlc_str = str(hlc)

        # 1. IDEMPOTENCY GUARD: If we already hold this exact primary claim, exit
        if resource in self.claims:
            curr_id, curr_hlc = self.claims[resource]
            if str(curr_id) == peer_id_str and str(curr_hlc) == hlc_str:
                return
            
            # 2. FAST CONFLICT GUARD: O(1) set lookup instead of O(N) list scanning
            if (peer_id_str, hlc_str) in self.conflicts[resource]:
                return

            # 3. TIE-BREAKER LOGIC
            if hlc < curr_hlc:
                # The current winner moves down to the conflict set
                self.conflicts[resource].add((str(curr_id), str(curr_hlc)))
                self.claims[resource] = (peer_id, hlc)
            else:
                # The incoming claim goes straight to the conflict set
                self.conflicts[resource].add((peer_id_str, hlc_str))
        else:
            self.claims[resource] = (peer_id, hlc)

    def get_winner(self, resource: str):
        return self.claims.get(resource, (None, None))

    def merge(self, other: 'EscrowLedger'):
        """Dumb Union Merge: Fully non-recursive."""
        # Process other's primary winning claims
        for res, (p, h) in other.claims.items():
            self.claim(res, p, h)
        
        # Process other's recorded conflict sets safely and rapidly
        for res, conflict_set in other.conflicts.items():
            for p_id_str, h_str in conflict_set:
                # Reconstruct a shadow comparison context if it isn't in conflicts yet
                if (p_id_str, h_str) not in self.conflicts[res]:
                    # If it's not the winner, add it to our local conflict set directly
                    if res in self.claims:
                        curr_id, curr_hlc = self.claims[res]
                        if str(curr_id) == p_id_str and str(curr_hlc) == h_str:
                            continue
                    self.conflicts[res].add((p_id_str, h_str))