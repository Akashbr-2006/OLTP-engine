from hlc import HLC
import time

def run_tests():
    print("--- Running HLC Verification ---")
    
    # 1. Test basic send increment
    clock_a = HLC.create_initial("A")
    op1_time = clock_a.send().pack()
    op2_time = clock_a.send().pack()
    
    print(f"Peer A Op 1: {op1_time}")
    print(f"Peer A Op 2: {op2_time}")
    assert op1_time < op2_time, "FAIL: Clock did not move forward"
    print("✓ Test 1 Passed: Clocks increment correctly.")

    # 2. Test tie-breaking (Lexicographical Sorting)
    # Force a physical tie between Peer A and Peer B
    fake_time = 1715000000000 
    clock_a = HLC(fake_time, 0, "A")
    clock_b = HLC(fake_time, 0, "B")
    
    str_a = clock_a.pack()
    str_b = clock_b.pack()
    
    print(f"\nForced Tie - Peer A: {str_a}")
    print(f"Forced Tie - Peer B: {str_b}")
    
    # Because 'A' < 'B' alphabetically, Peer A will always win conflicts if times match!
    assert str_a < str_b, "FAIL: Tie-breaker failed."
    print("✓ Test 2 Passed: Deterministic tie-breaking works (A wins over B).")

    # 3. Test Receive (Causality)
    clock_a = HLC.create_initial("A")
    clock_b = HLC.create_initial("B")
    
    # Simulate B having a clock far in the future
    clock_b.ts += 5000 
    b_sync_str = clock_b.pack()
    
    # A receives B's future clock
    clock_a.receive(b_sync_str)
    a_new_str = clock_a.send().pack()
    
    print(f"\nPeer B sends: {b_sync_str}")
    print(f"Peer A updates and sends: {a_new_str}")
    assert a_new_str > b_sync_str, "FAIL: Causality violated."
    print("✓ Test 3 Passed: Clocks absorb future times correctly (Causality maintained).")
    
    print("\n✅ All HLC Tests Passed. Ready for Step 2.")

if __name__ == "__main__":
    run_tests()