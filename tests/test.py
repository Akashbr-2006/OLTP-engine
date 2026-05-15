import random
import sys
import os

# Absolute path enforcement for clean execution
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from engine import CRDTEngine

def generate_random_string(length=6):
    return "".join(random.choices("abcdefghijklmnopqrstuvwxyz", k=length))

def run_parameterized_audit(seed_val, num_peers, total_queries):
    print(f"\n============================================================")
    print(f"🔬 Relational CRDT Evaluation Harness")
    print(f"============================================================")
    print(f"  Seed Configuration : {seed_val}")
    print(f"  Target Peer Count  : {num_peers}")
    print(f"  Query Budget       : {total_queries}")
    print(f"------------------------------------------------------------")
    
    random.seed(seed_val)
    
    # Initialize decoupled cluster topology
    peers = [CRDTEngine(f"NODE_{i}") for i in range(num_peers)]
    schema = [
        "CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT, name TEXT)",
        "CREATE TABLE orders (id TEXT PRIMARY KEY, user_id TEXT, status TEXT)"
    ]
    for p in peers:
        p.apply_schema(schema)

    # In-memory tracking lists to choose valid relations dynamically
    active_user_ids = []
    active_order_ids = []
    
    # Pre-populate a pool of potential high-contention keys
    user_pool = [f"u_{i}" for i in range(1, num_peers * 3)]
    order_pool = [f"o_{i}" for i in range(1, total_queries // 2)]
    email_pool = [f"{generate_random_string()}@infrastructure.org" for _ in range(5)] # Heavy email duplicate stress

    for step in range(total_queries):
        p = random.choice(peers)
        query_type = random.choice(["INSERT_USER", "UPDATE_USER", "INSERT_ORDER", "DELETE_USER"])

        if query_type == "INSERT_USER":
            uid = random.choice(user_pool)
            email = random.choice(email_pool) if random.random() < 0.4 else f"{generate_random_string()}@x.com"
            name = f"InitName_{generate_random_string()}"
            p.execute("INSERT INTO users (id, email, name) VALUES (?, ?, ?)", (uid, email, name))
            if uid not in active_user_ids:
                active_user_ids.append(uid)

        elif query_type == "UPDATE_USER":
            if active_user_ids:
                uid = random.choice(active_user_ids)
                # Randomly target 'name' or 'email' to stress cell-level isolation
                if random.random() < 0.5:
                    p.execute("UPDATE users SET name = ? WHERE id = ?", (f"Mutated_{generate_random_string()}", uid))
                else:
                    p.execute("UPDATE users SET email = ? WHERE id = ?", (random.choice(email_pool), uid))

        elif query_type == "INSERT_ORDER":
            if active_user_ids:
                oid = random.choice(order_pool)
                uid = random.choice(active_user_ids) # Relational link
                p.execute("INSERT INTO orders (id, user_id, status) VALUES (?, ?, ?)", (oid, uid, "pending"))
                if oid not in active_order_ids:
                    active_order_ids.append(oid)

        elif query_type == "DELETE_USER":
            if active_user_ids:
                uid = random.choice(active_user_ids)
                p.execute("DELETE FROM users WHERE id = ?", (uid,))
                active_user_ids.remove(uid)

        # Simulating spontaneous asymmetric network syncs
        if random.random() < 0.25:
            p1, p2 = random.sample(peers, 2)
            p1.sync_with(p2)
            p2.sync_with(p1)

    print("🏁 Divergence phase finished. Executing final gossip settlement...")
    
    # Quiescence loop: Exhaustive cluster gossip to verify full convergence stability
    for round_idx in range(4):
        for i in range(num_peers):
            for j in range(num_peers):
                if i != j:
                    peers[i].sync_with(peers[j])

    # Extraction and evaluation of final structural states
    snapshot_hashes = [p.snapshot_hash() for p in peers]
    unique_hashes = set(snapshot_hashes)
    
    if len(unique_hashes) == 1:
        print(f"✅ STATE CONVERGENCE MATCH: All {num_peers} nodes converged perfectly.")
        print(f"   Canonical Cluster Hash: {snapshot_hashes[0]}")
        
        # Sample checking the state layout
        final_sample = peers[0].materialize_state()
        u_count = len(final_sample.get('users', []))
        o_count = len(final_sample.get('orders', []))
        print(f"   Materialized Projection View: {u_count} Active Users | {o_count} Relational History Orders")
    else:
        print(f"❌ CONVERGENCE FAILURE DETECTED!")
        for idx, h in enumerate(snapshot_hashes):
            print(f"   Node_{idx} Reference Hash: {h}")

if __name__ == "__main__":
    # Test Suite Variant 1: Mid-tier volume, moderate peer cluster
    run_parameterized_audit(seed_val=112233, num_peers=5, total_queries=300)
    
    # Test Suite Variant 2: Massively scaled concurrent mutation load
    run_parameterized_audit(seed_val=445566, num_peers=12, total_queries=2500)