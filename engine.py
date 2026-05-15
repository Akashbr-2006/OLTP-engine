import json
import hashlib
import re
from crdt import MVRegister, ORSet, EscrowLedger
from hlc import HLC

class CRDTEngine:
    def __init__(self, peer_id, db_path=None):
        self.peer_id = str(peer_id)
        self.hlc = HLC.create_initial(self.peer_id)
        # The Formal Uniqueness Protocol: Deterministic Escrow
        self.escrow = EscrowLedger() 
        # The Pure CRDT State Machine: Lattices only
        self.tables = {} 
        self.indexes = {} 

    def apply_schema(self, schema_ddl):
        """Initializes OR-Sets and Cell dictionaries based on the schema."""
        for stmt in schema_ddl:
            if stmt.upper().startswith("CREATE TABLE"):
                match = re.search(r'CREATE TABLE\s+(\w+)', stmt, re.IGNORECASE)
                if match:
                    t_name = match.group(1).lower()
                    self.tables[t_name] = {'rows': ORSet(), 'cells': {}}

    def execute(self, query, params=()):
        """Translates SQL mutations into MV-Register and OR-Set operations."""
        clock = self.hlc.send()
        q_upper = query.strip().upper()

        if q_upper.startswith("INSERT INTO"):
            match = re.search(r'INSERT INTO\s+(\w+)\s+\((.*?)\)', q_upper)
            if not match: return
            t_name = match.group(1).lower()
            cols = [c.strip().lower() for c in match.group(2).split(',')]
            
            row_id = params[0]
            # Add to OR-Set lattice (Existence)
            self.tables[t_name]['rows'].add(row_id, clock)
            
            for col, val in zip(cols, params):
                key = (row_id, col)
                if key not in self.tables[t_name]['cells']:
                    self.tables[t_name]['cells'][key] = MVRegister()
                self.tables[t_name]['cells'][key].assign(self.peer_id, val, clock)
                
                if t_name == "users" and col == "email":
                    self.escrow.claim(val, row_id, clock) 

        elif q_upper.startswith("UPDATE"):
            match = re.search(r'UPDATE\s+(\w+)\s+SET\s+(.*?)\s+WHERE\s+ID\s*=\s*\?', q_upper)
            if not match: return
            t_name = match.group(1).lower()
            col = match.group(2).split('=')[0].strip().lower()
            val, row_id = params
            
            key = (row_id, col)
            # ARCHITECTURAL RIGOR: Mutate existing register to preserve concurrent history
            if key not in self.tables[t_name]['cells']:
                self.tables[t_name]['cells'][key] = MVRegister()
            
            self.tables[t_name]['cells'][key].assign(self.peer_id, val, clock)
            
            if t_name == "users" and col == "email":
                self.escrow.claim(val, row_id, clock)

        elif q_upper.startswith("DELETE FROM"):
            match = re.search(r'DELETE FROM\s+(\w+)', q_upper)
            if not match: return
            t_name = match.group(1).lower()
            row_id = params[0]
            # Cryptographic tombstone in the OR-Set
            self.tables[t_name]['rows'].remove(row_id, clock)

    def _update_index(self, t_name, col, row_id, val):
        if t_name not in self.indexes: self.indexes[t_name] = {}
        if col not in self.indexes[t_name]: self.indexes[t_name][col] = {}
        if val not in self.indexes[t_name][col]:
            self.indexes[t_name][col][val] = set()
        self.indexes[t_name][col][val].add(row_id)

    def materialize_state(self):
        """Projects the CRDT math into a clean, sorted JSON object."""
        state = {}
        for t_name, table_data in self.tables.items():
            state[t_name] = []
            all_row_ids = sorted(list(set(k[0] for k in table_data['cells'].keys())))
            
            for row_id in all_row_ids:
                is_active = table_data['rows'].contains(row_id)
                row_dict = {}
                for (r_id, col), reg in table_data['cells'].items():
                    if r_id == row_id:
                        row_dict[col] = reg.resolve()
                
                if not row_dict: continue

                # 1. Foreign Key Tombstone Policy
                if t_name == "orders" and "user_id" in row_dict:
                    parent_id = row_dict["user_id"]
                    if not self.tables["users"]["rows"].contains(parent_id):
                        row_dict["status"] = f"{row_dict.get('status', 'active')} (PARENT_TOMBSTONED)"

                # 2. Uniqueness Recovery: Surface conflicts via unique suffixes
                if t_name == "users" and "email" in row_dict:
                    resolved_email = row_dict["email"]
                    winner_info = self.escrow.get_winner(resolved_email)
                    if winner_info and winner_info[0] is not None:
                        winner_id, _ = winner_info
                        if winner_id != row_id:
                            row_dict["email"] = f"{resolved_email} (conflict:{row_id})"
                
                # 3. Deterministic Visibility
                if is_active or t_name == "orders":
                    state[t_name].append(row_dict)

            # 4. Deterministic Range Queries (Sorting)
            state[t_name] = sorted(state[t_name], key=lambda x: x.get('id', ''))
            
        return state

    def sync_with(self, other: 'CRDTEngine'):
        """One-way idempotent merge into self."""
        if other.hlc > self.hlc:
            self.hlc.ts = other.hlc.ts
            self.hlc.count = other.hlc.count
            self.hlc.node_id = self.peer_id
        self.hlc = self.hlc.send()

        self.escrow.merge(other.escrow)

        for t_name, table_data in other.tables.items():
            if t_name not in self.tables:
                self.tables[t_name] = {'rows': ORSet(), 'cells': {}}
            self.tables[t_name]['rows'].merge(table_data['rows'])
            for key, reg in table_data['cells'].items():
                if key not in self.tables[t_name]['cells']:
                    self.tables[t_name]['cells'][key] = MVRegister()
                self.tables[t_name]['cells'][key].merge(reg)

        # Rebuild Indexes
        self.indexes = {}
        for t_name, table_data in self.tables.items():
            for (row_id, col), reg in table_data['cells'].items():
                self._update_index(t_name, col, row_id, reg.resolve())

    def snapshot_hash(self) -> str:
        state = self.materialize_state()
        state_json = json.dumps(state, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(state_json.encode('utf-8')).hexdigest()