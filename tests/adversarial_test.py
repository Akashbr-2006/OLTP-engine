import sys
import os
import random
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)

if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from engine import CRDTEngine

def run_high_parameter_stress(seed_val, num_peers=5, num_ops=200):
    print(f"🔥 Running Adversarial Stress Test | Seed: {seed_val} | Peers: {num_peers} | Ops: {num_ops}")
    random.seed(seed_val)
    
    peers = [CRDTEngine(f"PEER_{i}") for i in range(num_peers)]
    schema = [
        "CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT, name TEXT)",
        "CREATE TABLE orders (id TEXT PRIMARY KEY, user_id TEXT, status TEXT)"
    ]
    for p in peers: p.apply_schema(schema)

    # Hand-crafted high-contention keys
    target_user = "u_shared"
    shared_email = "conflict@system.com"

    for i in range(num_ops):
        p = random.choice(peers)
        op_type = random.random()

        if op_type < 0.4: # 40% Concurrent Inserts to same ID/Email
            p.execute("INSERT INTO users (id, email, name) VALUES (?, ?, ?)", 
                      (target_user, shared_email, f"Name_{p.peer_id}_{i}"))
        
        elif op_type < 0.7: # 30% Updates to the same row
            p.execute("UPDATE users SET name = ? WHERE id = ?", 
                      (f"Update_{i}", target_user))
        
        elif op_type < 0.9: # 20% Order placements against potentially deleted parents
            p.execute("INSERT INTO orders (id, user_id, status) VALUES (?, ?, ?)", 
                      (f"o_{i}", target_user, "active"))
        
        else: # 10% Aggressive Deletes
            p.execute("DELETE FROM users WHERE id = ?", (target_user,))

        # Random sync frequency (Simulates unreliable network)
        if random.random() < 0.2:
            p1, p2 = random.sample(peers, 2)
            p1.sync_with(p2)
            p2.sync_with(p1)

    print("🏁 Ops complete. Finalizing global sync for convergence check...")
    # Quiescence: Sync everyone with everyone to ensure convergence
    for _ in range(3): # Multiple passes to ensure Escrow propagates
        for i in range(len(peers)):
            for j in range(len(peers)):
                if i != j: peers[i].sync_with(peers[j])

    # Check convergence
    hashes = [p.snapshot_hash() for p in peers]
    unique_hashes = set(hashes)
    
    if len(unique_hashes) == 1:
        print(f"✅ CONVERGENCE SUCCESS: All {num_peers} peers agree on {hashes[0][:12]}")
    else:
        print(f"❌ CONVERGENCE FAIL: {len(unique_hashes)} different states detected!")
        for i, h in enumerate(hashes):
            print(f"  Peer_{i}: {h[:12]}")

if __name__ == "__main__":
    # Test with a "Held-out" style seed
    run_high_parameter_stress(seed_val=999999, num_peers=8, num_ops=1000)