import sys
import os
import time
# This tells Python to look in the parent directory!
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crdt import LWWRegister, ORSet, EscrowLedger
from hlc import HLC

def test_primitives():
    # --- 1. Test LWW Register ---
    clock_a = HLC.create_initial("A")
    clock_b = HLC.create_initial("B")
    
    reg_a = LWWRegister("Alice", clock_a.send())
    time.sleep(0.01) # Force time difference
    reg_b = LWWRegister("Alice Cooper", clock_b.send())
    
    reg_a.merge(reg_b)
    assert reg_a.value == "Alice Cooper", "LWW Register Failed"
    print("✅ LWW Register passed cell-level merge.")

    # --- 2. Test OR-Set (Tombstones) ---
    row_set = ORSet()
    row_id = "u1"
    
    # Add row
    add_clock = clock_a.send()
    row_set.add(row_id, add_clock)
    assert row_set.contains(row_id) == True
    
    # Delete row (Tombstone)
    time.sleep(0.01)
    del_clock = clock_a.send()
    row_set.remove(row_id, del_clock)
    assert row_set.contains(row_id) == False
    print("✅ OR-Set passed native tombstoning.")

    # --- 3. Test Escrow Ledger ---
    ledger = EscrowLedger()
    
    # Peer B claims email at ts=100
    b_clock = HLC(100, 0, "B")
    ledger.claim("alice@x.com", "B", b_clock)
    
    # Peer A claims same email at ts=90 (Earlier time wins!)
    a_clock = HLC(90, 0, "A")
    ledger.claim("alice@x.com", "A", a_clock)
    
    winner, winning_hlc = ledger.get_winner("alice@x.com")
    assert winner == "A", "Escrow failed to pick lowest HLC"
    print("✅ Escrow Ledger passed deterministic offline reservation.")

if __name__ == "__main__":
    test_primitives()