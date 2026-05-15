import sys
import os
import time # <--- Add this
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine import CRDTEngine

def test_recovery_visibility():
    engine = CRDTEngine("A")
    engine.apply_schema(["CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT, name TEXT)"])
    
    # 1. First insert (The Winner)
    engine.execute("INSERT INTO users (id, email, name) VALUES (?, ?, ?)", ("u1", "bob@x.com", "Bob"))
    
    time.sleep(0.01) # <--- FORCE THE CLOCK TO TICK FORWARD
    
    # 2. Second insert (The Loser - has a later HLC)
    engine.execute("INSERT INTO users (id, email, name) VALUES (?, ?, ?)", ("u2", "bob@x.com", "Bob 2"))
    
    state = engine.materialize_state()
    emails = [u["email"] for u in state["users"]]
    
    print(f"DEBUG - Final Emails in state: {emails}") # Helps you see what's happening
    
    assert "bob@x.com (CONFLICT_LOSER)" in emails
    print("✅ Recovery Check: Conflicting uniqueness claims are surfaced, not dropped.")

if __name__ == "__main__":
    test_recovery_visibility()