import json
import time
from typing import Dict, Any
from .config import LINKS_FILE

def load_links() -> Dict[str, Any]:
    try:
        return json.loads(LINKS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save_links(d: Dict[str, Any]) -> None:
    LINKS_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

def upsert_link(user_id: int, name: str, tag: str, region: str) -> None:
    d = load_links()
    d[str(user_id)] = {"name": name, "tag": tag, "region": region, "ts": int(time.time())}
    save_links(d)

def pop_link(user_id: int) -> dict | None:
    d = load_links()
    v = d.pop(str(user_id), None)
    save_links(d)
    return v

def get_link(user_id: int) -> dict | None:
    return load_links().get(str(user_id))
