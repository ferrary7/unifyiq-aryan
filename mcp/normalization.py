from datetime import datetime
from typing import Optional

PRIORITY_MAP = {
    "critical": "P1",
    "blocker": "P1",
    "high": "P1",
    "medium": "P2",
    "low": "P3",
}

STATUS_MAP = {
    "open": "Open",
    "in progress": "In Progress",
    "backlog": "Open",
    "todo": "Open",
    "done": "Closed",
    "closed": "Closed",
    "resolved": "Closed",
}

def to_iso_date(value: Optional[str]) -> Optional[str]:
    if not value or not str(value).strip():
        return None
    s = str(value).strip()
    fmts = ["%Y-%m-%d","%d-%m-%Y","%d/%m/%Y","%Y/%m/%d","%m/%d/%Y","%m-%d-%Y"]
    for f in fmts:
        try:
            return datetime.strptime(s, f).date().isoformat()
        except Exception:
            continue
    try:
        parts = s.replace("/", "-").split("-")
        if len(parts) == 3 and len(parts[0]) == 4:
            return f"{parts[0]}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"
    except Exception:
        pass
    return None

def norm_priority(p: Optional[str]) -> str:
    if not p:
        return "P3"
    return PRIORITY_MAP.get(str(p).lower().strip(), "P3")

def norm_status(s: Optional[str]) -> str:
    if not s:
        return "Open"
    return STATUS_MAP.get(str(s).lower().strip(), "Open")
