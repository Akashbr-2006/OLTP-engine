import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from crdt import MVRegister, EscrowLedger
from hlc import HLC

def test_mv_and_escrow_recovery():
    # 1. Test MVRegister Conflict Storage
    reg = MVRegister("A", "Alice", HLC(100, 0, "A"))
    reg.merge(MVRegister("B", "Bob", HLC(100, 0, "B")))
    assert len(reg.values) == 2
    print("✅ MV-Register preserved both concurrent values.")

    # 2. Test Escrow Recovery
    escrow = EscrowLedger()
    escrow.claim("alice@x.com", "row_2", HLC(200, 0, "B")) # Late claim
    escrow.claim("alice@x.com", "row_1", HLC(100, 0, "A")) # Early claim wins
    
    winner, _ = escrow.get_winner("alice@x.com")
    assert winner == "row_1"
    assert "alice@x.com" in escrow.conflicts
    assert escrow.conflicts["alice@x.com"][0][0] == "row_2"
    print("✅ Escrow Ledger recovered the loser into the conflicts list.")

if __name__ == "__main__":
    test_mv_and_escrow_recovery()