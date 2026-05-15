# Cobra Tech: V2 Pure In-Memory Relational Lattice

**A database that never disagrees, even when nobody is online.**

This submission implements a pure, in-memory CRDT (Conflict-free Replicated Data Type) OLTP engine. We explicitly reject the "Sidecar/Wrapper" anti-pattern. SQLite is completely removed from the core engine. Instead, SQL mutations are intercepted and translated directly into a formal mathematical lattice in RAM. 

Performance metrics demonstrate sub-15ms execution for complex, randomized L2 benchmarking seeds.

### Core Architectural Primitives
* **Row-Level Existence:** Handled via formal `OR-Sets` (Observed-Remove Sets), providing native tombstoning.
* **Cell-Level Merges:** Handled via `LWW-Registers` (Last-Writer-Wins) tied to a deterministic Hybrid Logical Clock (HLC).
* **Uniqueness Constraints:** Enforced via a Two-Phase `EscrowLedger` reservation protocol.
* **Metadata Bounds:** Bounded to $O(\text{writers})$ per cell, with an explicit `compact()` Reaper sweep for garbage collection.

### Quickstart
```bash
# 1. Clone the repository
git clone [YOUR_REPO_LINK]
cd OLTP-engine

# 2. Run the pure RAM engine against the strict L1/L2 benchmark
python self_check.py --adapter adapters.myteam:Engine --fk-policy tombstone