import os
from engine import CRDTEngine

def run_tests():
    print("--- Running SQL Interceptor Verification ---")
    
    test_db_file = "test_peer_A_engine.db"
    if os.path.exists(test_db_file):
        os.remove(test_db_file)
        
    # Initialize Peer A's engine
    engine = CRDTEngine(peer_id="A", db_path=test_db_file)
    
    # 1. Test INSERT interception
    print("\nExecuting: INSERT INTO users (u1, alice@x.com, Alice)")
    engine.execute(
        "INSERT INTO users (id, email, name) VALUES (?, ?, ?)", 
        ("u1", "alice@x.com", "Alice")
    )
    
    # Verify the read-cache (SQLite)
    users = engine.db.query("SELECT * FROM users")
    print(f"Read-Cache (SQLite) contains: {dict(users[0])}")
    assert users[0]['name'] == 'Alice', "FAIL: Read cache not updated."

    # Verify the CRDT Op-Log (The Source of Truth)
    logs = engine.db.query("SELECT * FROM crr_log WHERE row_id = 'u1'")
    print("\nCRDT Op-Log contains:")
    for log in logs:
        print(f"  -> Column: {log['column_name']}, Value: {log['value']}, HLC: {log['hlc']}")
        
    assert len(logs) == 2, "FAIL: Should be 2 logs (email, name), ID is skipped."
    print("✓ Test 1 Passed: INSERT successfully split into cell-level logs.")

    # 2. Test UPDATE interception
    print("\nExecuting: UPDATE users SET name = 'Alice Cooper' WHERE id = 'u1'")
    engine.execute(
        "UPDATE users SET name = ? WHERE id = ?", 
        ("Alice Cooper", "u1")
    )
    
    # Verify Op-Log updated the name with a new HLC
    logs = engine.db.query("SELECT * FROM crr_log WHERE row_id = 'u1' AND column_name = 'name'")
    print(f"Updated CRDT Log for Name: {logs[0]['value']} at HLC: {logs[0]['hlc']}")
    
    assert logs[0]['value'] == 'Alice Cooper', "FAIL: Op-Log not updated."
    print("✓ Test 2 Passed: UPDATE successfully recorded with new HLC.")

    # Cleanup
    engine.db.clear_db()
    print("\n✅ All Interceptor Tests Passed. Ready for Phase 3 (Foreign Keys & Uniqueness).")

if __name__ == "__main__":
    run_tests()