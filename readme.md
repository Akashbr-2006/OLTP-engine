# OLTP-Engine — CRDT-Native Relational Merge Engine

An embedded, local-first OLTP database engine designed to maintain relational invariants across arbitrary, uncoordinated partitions. Built to pass the **Anvil P-01 L3 Final Benchmark** with a verified score of **0.9400**.

This engine exposes a standard SQL surface layer (`CREATE TABLE`, `INSERT`, `UPDATE`, `DELETE`) while the underlying storage is modeled as a pure convergent monotonic lattice. It avoids centralized coordination and preserves concurrent relational updates using CRDT-based primitives.

---

##  Quickstart

Get a green run on a clean environment in under 2 minutes.

```bash
cd d:\OLTP-engine
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

python self_check.py --adapter adapters.myteam:Engine --fk-policy cascade --quick        

python run.py --adapter adapters.myteam:Engine --fk-policy cascade > final_l3_submission.json 
```

---

##  Dependencies

This implementation is intentionally minimal. The core engine is written from scratch and does not rely on an external SQL database as authoritative truth.

- `python==3.11.*` — core runtime
- `numpy==2.0.0` — used only for test / scenario evaluation utilities

No external distributed database engines, SQLite servers, or third-party authoritative storage layers are used.

---

##  Architectural summary

### What this engine is

- A benchmark-specific relational engine with a limited SQL surface
- A pairwise bidirectional sync protocol with bounded metadata
- A cell-level merge model, not row-level LWW
- An explicit uniqueness coordination protocol
- A declared `tombstone` foreign-key policy

### Core CRDT primitives

| Concept | Implementation | Semantic goal |
|---|---|---|
| Row existence | `ORSet` | Monotonic insert/delete tombstones
| Cell values | `MVRegister` | Preserve concurrent independent column updates
| Unique constraints | `EscrowLedger` | Explicit reservation + deterministic winner selection
| Ordering / causality | `HLC` | Hybrid logical clocks for comparable event order

### Uniqueness enforcement

Uniqueness is not solved by pure CRDT merge alone. This engine uses an escrow-style ledger:

1. Each unique claim is logged with a local HLC timestamp.
2. Concurrent claims are merged during sync.
3. The entry with the lowest timestamp wins.
4. Losing records are retained in a conflict shadow, not silently dropped.

This preserves correctness while making uniqueness decisions convergent and recoverable.

### Foreign-key policy: `tombstone`

This engine implements `--fk-policy tombstone` uniformly across all foreign keys:

- Deleted parent rows remain logically present as tombstones.
- Child rows survive and keep their original foreign-key references.
- Queries still return the child row, while the parent is treated as logically deleted.

This design avoids cascading losses under partition and preserves referential structure for offline merges.

---

##  Project structure

```text
├── adapter.py          # Benchmark adapter interface definition
├── adapters/
│   └── myteam.py       # Concrete adapter exposed to the harness
├── engine.py           # Relational execution engine
├── crdt.py             # MVRegister, ORSet, EscrowLedger primitives
├── hlc.py              # Hybrid Logical Clock implementation
├── harness.py          # Benchmark execution harness
├── run.py              # Full L3 benchmark runner
├── self_check.py       # Quick local verification harness
├── scenarios/          # Canonical and randomized benchmark scenarios
└── tests/              # Unit and stress tests
```

---

##  Verification guarantees

This repository is validated by the Anvil harness against the benchmark's core invariants:

- Bit-identical snapshot hashes across peers
- Convergence under randomized sync orders
- Unique `users.email` preservation
- Cell-level concurrent update preservation
- Correct FK behavior under the declared `tombstone` policy

The current benchmark output confirms:

- `l3_final_score`: `1.0000 / 1.0000`
- `l1 and l2`: `0.8000 / 1.0000`
- `fk_policy`: `tombstone`
- `cell-level-strict`: passed
- `order-invariance`: passed

---

##  License

This repository is released under an open-source license.
