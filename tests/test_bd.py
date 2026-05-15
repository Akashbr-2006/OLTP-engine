import os
from db import CRDTDatabase

def run_tests():
    print("--- Running Database Schema Verification ---")
    
    test_db_file = "test_peer_A.db"
    
    # Ensure clean slate
    if os.path.exists(test_db_file):
        os.remove(test_db_file)
        
    # Initialize DB
    db = CRDTDatabase(test_db_file)
    
    # Query sqlite_master to get all table names
    tables = db.query("SELECT name FROM sqlite_master WHERE type='table';")
    table_names = [row['name'] for row in tables]
    
    print(f"Tables found in database: {table_names}")
    
    # Verify exact tables exist
    required_tables = ['users', 'orders', 'crr_log', 'crr_tombstones', 'crr_conflicts']
    for req in required_tables:
        assert req in table_names, f"FAIL: Missing required table '{req}'"
        print(f"✓ Table '{req}' successfully created.")
        
    db.clear_db() # Clean up
    print("\n✅ All Database Tests Passed. Ready for Step 3.")

if __name__ == "__main__":
    run_tests()