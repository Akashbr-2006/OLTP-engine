import os
from engine import CRDTEngine

def run_tests():
    print("--- Running Tombstone FK Policy Verification ---")
    
    test_db_file = "test_peer_A_tombstone.db"
    if os.path.exists(test_db_file):
        os.remove(test_db_file)
        
    engine = CRDTEngine(peer_id="A", db_path=test_db_file)
    
    # 1. Create a User and their Order
    engine.execute("INSERT INTO users (id, email, name) VALUES (?, ?, ?)", ("u1", "alice@x.com", "Alice"))
    engine.execute("INSERT INTO orders (id, user_id, status, total_cents) VALUES (?, ?, ?, ?)", ("o1", "u1", "pending", 1200))
    
    # 2. Execute the DELETE (Simulating partition / concurrent delete)
    print("\nExecuting: DELETE FROM users WHERE id = 'u1'")
    engine.execute("DELETE FROM users WHERE id = ?", ("u1",))
    
    # Verify 1: The user is gone from the read cache
    users = engine.db.query("SELECT * FROM users")
    print(f"Users in SQLite: {len(users)} (Expected: 0)")
    assert len(users) == 0, "FAIL: User was not deleted from read-cache."
    
    # Verify 2: The order SURVIVED (Tombstone policy success)
    orders = engine.db.query("SELECT * FROM orders")
    print(f"Orders in SQLite: {len(orders)} (Expected: 1, Order ID: {orders[0]['id']})")
    assert len(orders) == 1, "FAIL: Order was incorrectly cascaded/deleted."
    
    # Verify 3: The Tombstone exists in the CRDT metadata
    tombstones = engine.db.query("SELECT * FROM crr_tombstones")
    print(f"Tombstones in CRDT: Row ID '{tombstones[0]['row_id']}' deleted at HLC {tombstones[0]['deleted_at_hlc']}")
    assert len(tombstones) == 1 and tombstones[0]['row_id'] == 'u1', "FAIL: Tombstone not created."

    print("\n✅ FK Tombstone Policy Verified! The child row survived and the parent was tombstoned.")
    
    engine.db.clear_db()

if __name__ == "__main__":
    run_tests()