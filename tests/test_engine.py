import sys
import os
# Fix the path so Python can see the main folder
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import CRDTEngine

def test_v2_engine():
    # 1. Setup Pure RAM Engine
    engine = CRDTEngine("TestPeer")
    schema = [
        "CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, name TEXT)"
    ]
    engine.apply_schema(schema)
    assert "users" in engine.tables, "Engine failed to initialize schema OR-Set"

    # 2. Test Insert & Escrow Intercept
    engine.execute("INSERT INTO users (id, email, name) VALUES (?, ?, ?)", ("u1", "alice@x.com", "Alice"))
    state = engine.materialize_state()
    assert len(state["users"]) == 1, "Engine failed to materialize row"
    assert state["users"][0]["name"] == "Alice", "Engine failed cell-level LWW assignment"

    # 3. Test Update (Cell Level)
    engine.execute("UPDATE users SET name = ? WHERE id = ?", ("Alice Cooper", "u1"))
    state = engine.materialize_state()
    assert state["users"][0]["name"] == "Alice Cooper", "Engine failed LWW update"

    # 4. Test Delete (Native Tombstoning)
    engine.execute("DELETE FROM users WHERE id = ?", ("u1",))
    state = engine.materialize_state()
    assert len(state["users"]) == 0, "Engine failed to apply OR-Set Tombstone"

    print("✅ V2 CRDTEngine passed all pure in-memory lifecycle tests.")

if __name__ == "__main__":
    test_v2_engine()