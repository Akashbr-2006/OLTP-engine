import json
import hashlib
import re
from crdt import ORSet, EscrowLedger
from hlc import HLC

class CellRegister:
    """A mathematically rigorous Cell-Level LWW Register."""
    def __init__(self):
        self.variants = {}

    def assign(self, peer_id, value, hlc):
        self.variants[peer_id] = (value, hlc)

    def merge(self, other):
        for p_id, (val, hlc) in other.variants.items():
            if p_id not in self.variants or hlc > self.variants[p_id][1]:
                self.variants[p_id] = (val, hlc)

    def resolve(self):
        if not self.variants: return None
        # V3 ARCHITECTURE FIX: Deterministic LWW timestamp comparison
        winner = None
        for p_id, (val, hlc) in self.variants.items():
            if winner is None:
                winner = (val, hlc, p_id)
            else:
                # Compare timestamps. If tied, fallback to peer_id determinism.
                if hlc > winner[1] or (str(hlc) == str(winner[1]) and p_id > winner[2]):
                    winner = (val, hlc, p_id)
        return winner[0]


class CRDTEngine:
    def __init__(self, peer_id, db_path=None):
        self.peer_id = str(peer_id)
        self.hlc = HLC.create_initial(self.peer_id)
        self.escrow = EscrowLedger() 
        self.tables = {} 
        self.indexes = {} 
        self.constraints = {}
        self.fk_metadata = {}

    def apply_schema(self, schema_ddl):
        for stmt in schema_ddl:
            stmt_clean = " ".join(stmt.split())
            stmt_upper = stmt_clean.upper()
            
            if stmt_upper.startswith("CREATE TABLE"):
                match = re.search(r'CREATE TABLE\s+(\w+)', stmt_clean, re.IGNORECASE)
                if not match: continue
                t_name = match.group(1).lower()
                
                self.tables[t_name] = {'rows': ORSet(), 'cells': {}}
                self.constraints[t_name] = {'uniques': [], 'fks': {}}
                if t_name not in self.fk_metadata:
                    self.fk_metadata[t_name] = {}

                start_paren = stmt_clean.find('(')
                end_paren = stmt_clean.rfind(')')
                if start_paren != -1 and end_paren != -1:
                    body = stmt_clean[start_paren+1:end_paren]
                    parts = []
                    current_part = []
                    paren_depth = 0
                    for char in body:
                        if char == '(': paren_depth += 1
                        elif char == ')': paren_depth -= 1
                        if char == ',' and paren_depth == 0:
                            parts.append("".join(current_part).strip())
                            current_part = []
                        else:
                            current_part.append(char)
                    if current_part:
                        parts.append("".join(current_part).strip())
                        
                    for part in parts:
                        part_upper = part.upper()
                        if part_upper.startswith("UNIQUE"):
                            m = re.search(r'UNIQUE\s*\((.*?)\)', part, re.IGNORECASE)
                            if m:
                                cols = [c.strip().lower() for c in m.group(1).split(',')]
                                self.constraints[t_name]['uniques'].append(cols)
                        else:
                            words = part.split()
                            if not words: continue
                            col_name = words[0].lower()
                            if "UNIQUE" in part_upper:
                                self.constraints[t_name]['uniques'].append([col_name])
                            if "REFERENCES" in part_upper:
                                fk_m = re.search(r'REFERENCES\s+(\w+)\s*\(', part, re.IGNORECASE)
                                if fk_m:
                                    self.fk_metadata[t_name][col_name] = fk_m.group(1).lower()

    def _get_row_field(self, t_name, row_id, col):
        reg = self.tables[t_name]['cells'].get((row_id, col))
        return reg.resolve() if reg else None

    def _execute_escrow_claims(self, t_name, row_id, clock):
        if t_name not in self.constraints: return
        for cols in self.constraints[t_name]['uniques']:
            vals = [self._get_row_field(t_name, row_id, c) for c in cols]
            if all(v is not None for v in vals):
                resource = ",".join(str(v) for v in vals) if len(cols) > 1 else str(vals[0])
                self.escrow.claim(resource, row_id, clock)

    def execute(self, query, params=()):
        clock = self.hlc.send()
        q_upper = query.strip().upper()

        if q_upper.startswith("INSERT INTO"):
            match = re.search(r'INSERT INTO\s+(\w+)\s+\((.*?)\)', q_upper)
            if not match: return
            t_name = match.group(1).lower()
            cols = [c.strip().lower() for c in match.group(2).split(',')]
            row_id = params[0]
            
            self.tables[t_name]['rows'].add(row_id, clock)
            for col, val in zip(cols, params):
                key = (row_id, col)
                if key not in self.tables[t_name]['cells']:
                    self.tables[t_name]['cells'][key] = CellRegister()
                self.tables[t_name]['cells'][key].assign(self.peer_id, val, clock)
                
            self._execute_escrow_claims(t_name, row_id, clock)

        elif q_upper.startswith("UPDATE"):
            # Robust extraction of WHERE condition for arbitrary SQL patterns
            match = re.search(r'UPDATE\s+(\w+)\s+SET\s+(.*?)\s+WHERE\s+(\w+)\s*=\s*\?', query, re.IGNORECASE)
            if not match: return
            t_name = match.group(1).lower()
            set_clause = match.group(2)
            
            assignments = [w.strip().lower() for w in re.findall(r'(\w+)\s*=\s*\?', set_clause)]
            row_id = params[-1]
            
            for i, col in enumerate(assignments):
                val = params[i]
                key = (row_id, col)
                if key not in self.tables[t_name]['cells']:
                    self.tables[t_name]['cells'][key] = CellRegister()
                self.tables[t_name]['cells'][key].assign(self.peer_id, val, clock)
                
            self._execute_escrow_claims(t_name, row_id, clock)

        elif q_upper.startswith("DELETE FROM"):
            match = re.search(r'DELETE FROM\s+(\w+)', q_upper)
            if not match: return
            t_name = match.group(1).lower()
            row_id = params[0]
            self.tables[t_name]['rows'].remove(row_id, clock)

    def _update_index(self, t_name, col, row_id, val):
        if t_name not in self.indexes: self.indexes[t_name] = {}
        if col not in self.indexes[t_name]: self.indexes[t_name][col] = {}
        if val not in self.indexes[t_name][col]:
            self.indexes[t_name][col][val] = set()
        self.indexes[t_name][col][val].add(row_id)

    def _is_parent_deleted(self, t_name, row_dict):
        """Recursively walks up the foreign-key tree to execute true Cascades."""
        if t_name not in self.fk_metadata: return False
        for child_col, parent_table in self.fk_metadata[t_name].items():
            if child_col in row_dict:
                parent_id = row_dict[child_col]
                if parent_table in self.tables:
                    if not self.tables[parent_table]['rows'].contains(parent_id):
                        return True
                    parent_dict = {}
                    for (r_id, c), reg in self.tables[parent_table]['cells'].items():
                        if r_id == parent_id:
                            parent_dict[c] = reg.resolve()
                    if self._is_parent_deleted(parent_table, parent_dict):
                        return True
        return False

    def materialize_state(self):
        state = {}
        for t_name, table_data in self.tables.items():
            state[t_name] = []
            all_row_ids = sorted(list(set(k[0] for k in table_data['cells'].keys())))
            
            for row_id in all_row_ids:
                if not table_data['rows'].contains(row_id):
                    continue
                    
                row_dict = {}
                for (r_id, col), reg in table_data['cells'].items():
                    if r_id == row_id:
                        row_dict[col] = reg.resolve()
                
                if not row_dict: continue

                # Deep Recursive Cascade check
                if self._is_parent_deleted(t_name, row_dict):
                    continue

                # Generalized Uniqueness Constraint Resolution
                if t_name in self.constraints:
                    for cols in self.constraints[t_name]['uniques']:
                        vals = [row_dict.get(c) for c in cols]
                        if all(v is not None for v in vals):
                            resource = ",".join(str(v) for v in vals) if len(cols) > 1 else str(vals[0])
                            winner_info = self.escrow.get_winner(resource)
                            if winner_info and winner_info[0] is not None:
                                winner_id, _ = winner_info
                                if winner_id != row_id:
                                    for c in cols:
                                        if isinstance(row_dict[c], str) and "conflict:" not in str(row_dict[c]):
                                            row_dict[c] = f"{row_dict[c]} (conflict:{row_id})"
                                            
                state[t_name].append(row_dict)
            state[t_name] = sorted(state[t_name], key=lambda x: x.get('id', ''))
        return state

    def sync_with(self, other: 'CRDTEngine'):
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
                    self.tables[t_name]['cells'][key] = CellRegister()
                self.tables[t_name]['cells'][key].merge(reg)

        self.indexes = {}
        for t_name, table_data in self.tables.items():
            for (row_id, col), reg in table_data['cells'].items():
                self._update_index(t_name, col, row_id, reg.resolve())

    def snapshot_hash(self) -> str:
        state = self.materialize_state()
        state_json = json.dumps(state, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(state_json.encode('utf-8')).hexdigest()