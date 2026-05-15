from hlc import HLC

class LWWRegister:
    """
    Last-Writer-Wins Register.
    Used for cell-level resolution (e.g., updating a user's name or status).
    """
    def __init__(self, value=None, hlc=None):
        self.value = value
        self.hlc = hlc

    def merge(self, other: 'LWWRegister'):
        if self.hlc is None:
            self.value, self.hlc = other.value, other.hlc
        elif other.hlc is not None and other.hlc > self.hlc:
            self.value, self.hlc = other.value, other.hlc

class ORSet:
    """
    Observed-Remove Set.
    Mathematically tracks row existence. Tombstones are natively handled here.
    An element exists if its 'Add' HLC is strictly greater than its 'Remove' HLC.
    """
    def __init__(self):
        self.adds = {}    # row_id -> HLC
        self.removes = {} # row_id -> HLC

    def add(self, element: str, hlc: HLC):
        if element not in self.adds or hlc > self.adds[element]:
            self.adds[element] = hlc

    def remove(self, element: str, hlc: HLC):
        if element not in self.removes or hlc > self.removes[element]:
            self.removes[element] = hlc

    def contains(self, element: str) -> bool:
        if element not in self.adds:
            return False
        # If it was removed AFTER it was added, it is a tombstone (invisible)
        if element in self.removes and self.removes[element] >= self.adds[element]:
            return False
        return True

    def merge(self, other: 'ORSet'):
        for elem, hlc in other.adds.items():
            self.add(elem, hlc)
        for elem, hlc in other.removes.items():
            self.remove(elem, hlc)

class EscrowLedger:
    """
    Two-Phase Reservation Protocol for Uniqueness Constraints.
    Peers claim an email here offline. Lowest HLC wins mathematically.
    """
    def __init__(self):
        # Maps resource_key (e.g., email) -> (peer_id, HLC)
        self.claims = {}

    def claim(self, resource: str, peer_id: str, hlc: HLC):
        if resource not in self.claims:
            self.claims[resource] = (peer_id, hlc)
        else:
            existing_peer, existing_hlc = self.claims[resource]
            # Deterministic tie-breaker: Lowest HLC wins the reservation
            if hlc < existing_hlc:
                self.claims[resource] = (peer_id, hlc)

    def get_winner(self, resource: str):
        return self.claims.get(resource)

    def merge(self, other: 'EscrowLedger'):
        for resource, (peer, hlc) in other.claims.items():
            self.claim(resource, peer, hlc)