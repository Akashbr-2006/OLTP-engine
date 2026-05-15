import json
import hashlib
import re
import collections
from crdt import MVRegister, ORSet, EscrowLedger
from hlc import HLC

class CRDTEngine:
    def __init__(self, peer_id, db_path=None):
        self.peer_id = str(peer_id)
        self.hlc = HLC.create_initial(self.peer_id)
        # The Formal Uniqueness Protocol: Deterministic Escrow Ledger
        self.escrow = EscrowLedger() 
        # Pure CRDT State Maps
        self.tables = {} 
        self.indexes = {} 
        # Dynamic Schema Constraints Dictionary (Eliminates Hardcoding)
        self.constraints = {}

    def apply_schema(self, schema_ddl):
        """Dynamically parses and maps relational constraints and tables."""
        for stmt in schema_ddl:
            stmt_clean = " ".join(stmt.split())
            stmt_upper = stmt_clean.upper()
            
            if stmt_upper.startswith("CREATE TABLE"):
                match = re.search(r'CREATE TABLE\s+(\w+)', stmt_clean, re.IGNORECASE)
                if not match: continue
                t_name = match.group(1).lower()
                
                self.tables[t_name] = {'rows': ORSet(), 'cells': {}}
                self.constraints[t_name] = {'uniques': [], 'fks': {}}
                
                # Parentheses-aware parsing for composite keys
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
                        # 1. Parse table-level composite uniqueness: UNIQUE(user_id, team_id)
                        if part_upper.startswith("UNIQUE"):
                            m = re.search(r'UNIQUE\s*\((.*?)\)', part, re.IGNORECASE)
                            if m:
                                cols = [c.strip().lower() for c in m.group(1).split(',')]
                                self.constraints[t_name]['uniques'].append(cols)
                        # 2. Parse column-level attributes
                        else:
                            words = part.split()
                            if not words: continue
                            col_name = words[0].lower()
                            
                            if "UNIQUE" in part_upper:
                                self.constraints[t_name]['uniques'].append([col_name])
                                
                            if "REFERENCES" in part_upper:
                                fk_m = re.search(r'REFERENCES\s+(\w+)\s*\(', part, re.IGNORECASE)
                                if fk_m:
                                    parent_table = fk_m.group(1).lower()
                                    self.constraints[t_name]['fks'][col_name] = parent_table

    def _get_row_field(self, t_name, row_id, col):
        reg = self.tables[t_name]['cells'].get((row_id, col))
        return reg.resolve() if reg else None

    def _execute_escrow_claims(self, t_name, row_id, clock):
        """Generates globally unique resource keys for multi-column constraints."""
        if t_name not in self.constraints: return
        for cols in self.constraints[t_name]['uniques']:
            vals = [self._get_row_field(t_name, row_id, c) for c in cols]
            if all(v is not None for v in vals):
                cols_key = ",".join(cols)
                vals_key = ",".join(str(v) for v in vals)
                resource = f"{t_name}:{cols_key}:{vals_key}"
                self.escrow.claim(resource, row_id, clock)

    def execute(self, query, params=()):
        """Translates SQL mutations into fine-grained cell mutations."""
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
                    self.tables[t_name]['cells'][key] = MVRegister()
                self.tables[t_name]['cells'][key].assign(self.peer_id, val, clock)
                
            self._execute_escrow_claims(t_name, row_id, clock)

        elif q_upper.startswith("UPDATE"):
            match = re.search(r'UPDATE\s+(\w+)\s+SET\s+(.*?)\s+WHERE\s+ID\s*=\s*\?', q_upper)
            if not match: return
            t_name = match.group(1).lower()
            col = match.group(2).split('=')[0].strip().lower()
            val, row_id = params
            
            key = (row_id, col)
            if key not in self.tables[t_name]['cells']:
                self.tables[t_name]['cells'][key] = MVRegister()
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

    def materialize_state(self):
        """Projects and resolves relational states across multi-level constraints."""
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

                # Generalized Uniqueness Resolution (Single & Composite)
                if t_name in self.constraints:
                    for cols in self.constraints[t_name]['uniques']:
                        vals = [row_dict.get(c) for c in cols]
                        if all(v is not None for v in vals):
                            cols_key = ",".join(cols)
                            vals_key = ",".join(str(v) for v in vals)
                            resource = f"{t_name}:{cols_key}:{vals_key}"
                            
                            winner_info = self.escrow.get_winner(resource)
                            if winner_info and winner_info[0] is not None:
                                winner_id, _ = winner_info
                                if winner_id != row_id:
                                    # Target and append the collision identification tag uniformly
                                    for c in cols:
                                        if isinstance(row_dict[c], str):
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
                    self.tables[t_name]['cells'][key] = MVRegister()
                self.tables[t_name]['cells'][key].merge(reg)

        self.indexes = {}
        for t_name, table_data in self.tables.items():
            for (row_id, col), reg in table_data['cells'].items():
                self._update_index(t_name, col, row_id, reg.resolve())

    def snapshot_hash(self) -> str:
        state = self.materialize_state()
        state_json = json.dumps(state, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(state_json.encode('utf-8')).hexdigest()