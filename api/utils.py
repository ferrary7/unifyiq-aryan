import pandas as pd
from typing import List, Dict, Any

def read_excel_records(path) -> List[Dict[str, Any]]:
    df = pd.read_excel(path)
    # Normalize column names to strings and convert NaN to None
    df.columns = [str(c) for c in df.columns]
    records = df.where(pd.notnull(df), None).to_dict(orient="records")
    return records

def paginate(records, limit: int = 100, offset: int = 0):
    limit = max(1, min(limit, 1000))
    offset = max(0, offset)
    total = len(records)
    items = records[offset: offset + limit]
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "count": len(items),
        "items": items
    }
