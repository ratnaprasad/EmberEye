import os
import json
import threading
import sqlite3


_LOCK = threading.Lock()
_JSON_PATH = os.path.join(os.path.dirname(__file__), 'ip_loc_map.json')
_DB_PATH = os.path.join(os.path.dirname(__file__), 'ip_loc_map.db')
_cache = None


def _db_conn():
    try:
        conn = sqlite3.connect(_DB_PATH, timeout=2)
        conn.execute("CREATE TABLE IF NOT EXISTS mappings (ip TEXT PRIMARY KEY, loc_id TEXT)")
        return conn
    except Exception:
        return None


def _json_load():
    global _cache
    if _cache is not None:
        return _cache
    if os.path.exists(_JSON_PATH):
        try:
            with open(_JSON_PATH, 'r') as f:
                _cache = json.load(f)
        except Exception:
            _cache = {}
    else:
        _cache = {}
    return _cache


def _json_save():
    if _cache is None:
        return
    try:
        with open(_JSON_PATH, 'w') as f:
            json.dump(_cache, f, indent=2)
    except Exception:
        pass


def set_mapping(ip: str, loc_id: str):
    """Persist mapping from client IP to loc_id (SQLite first, JSON fallback)."""
    if not ip or not loc_id:
        return
    with _LOCK:
        conn = _db_conn()
        if conn:
            try:
                conn.execute("INSERT OR REPLACE INTO mappings (ip, loc_id) VALUES (?, ?)", (ip, loc_id))
                conn.commit()
                conn.close()
                return
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass
        # Fallback to JSON
        m = _json_load()
        m[ip] = loc_id
        _json_save()


def get_loc_id(ip: str):
    """Return loc_id mapped to IP, if available (SQLite first, JSON fallback)."""
    if not ip:
        return None
    with _LOCK:
        conn = _db_conn()
        if conn:
            try:
                cur = conn.execute("SELECT loc_id FROM mappings WHERE ip=?", (ip,))
                row = cur.fetchone()
                conn.close()
                if row:
                    return row[0]
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass
        # Fallback
        m = _json_load()
        return m.get(ip)


def clear_mapping(ip: str):
    """Remove mapping for an IP (SQLite first, JSON fallback)."""
    if not ip:
        return
    with _LOCK:
        conn = _db_conn()
        if conn:
            try:
                conn.execute("DELETE FROM mappings WHERE ip=?", (ip,))
                conn.commit()
                conn.close()
                return
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass
        m = _json_load()
        if ip in m:
            del m[ip]
            _json_save()


def export_json(path: str) -> bool:
    """Export all mappings to a JSON file."""
    try:
        data = {}
        conn = _db_conn()
        if conn:
            try:
                for ip, loc in conn.execute("SELECT ip, loc_id FROM mappings").fetchall():
                    data[ip] = loc
            finally:
                conn.close()
        else:
            data = _json_load().copy()
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception:
        return False


def import_json(path: str) -> bool:
    """Import mappings from a JSON file (overwrites existing keys)."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return False
        with _LOCK:
            conn = _db_conn()
            if conn:
                try:
                    conn.execute("BEGIN")
                    for ip, loc in data.items():
                        conn.execute("INSERT OR REPLACE INTO mappings (ip, loc_id) VALUES (?, ?)", (ip, loc))
                    conn.commit()
                finally:
                    conn.close()
            else:
                m = _json_load()
                m.update({str(k): str(v) for k, v in data.items()})
                _json_save()
        return True
    except Exception:
        return False


def export_csv(path: str) -> bool:
    """Export all mappings to a CSV file with headers: ip,loc_id."""
    try:
        rows = []
        conn = _db_conn()
        if conn:
            try:
                rows = conn.execute("SELECT ip, loc_id FROM mappings").fetchall()
            finally:
                conn.close()
        else:
            rows = list(_json_load().items())
        with open(path, 'w', encoding='utf-8') as f:
            f.write('ip,loc_id\n')
            for ip, loc in rows:
                f.write(f"{ip},{loc}\n")
        return True
    except Exception:
        return False


def import_csv(path: str) -> bool:
    """Import mappings from a CSV file with headers: ip,loc_id."""
    try:
        rows = []
        with open(path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                if i == 0 and line.lower().startswith('ip,'):
                    continue
                parts = [p.strip() for p in line.split(',')]
                if len(parts) >= 2:
                    rows.append((parts[0], parts[1]))
        if not rows:
            return False
        with _LOCK:
            conn = _db_conn()
            if conn:
                try:
                    conn.execute("BEGIN")
                    for ip, loc in rows:
                        conn.execute("INSERT OR REPLACE INTO mappings (ip, loc_id) VALUES (?, ?)", (ip, loc))
                    conn.commit()
                finally:
                    conn.close()
            else:
                m = _json_load()
                for ip, loc in rows:
                    m[str(ip)] = str(loc)
                _json_save()
        return True
    except Exception:
        return False
