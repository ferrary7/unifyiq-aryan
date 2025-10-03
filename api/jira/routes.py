from fastapi import APIRouter, Query, HTTPException
from api.config import JIRA_XLSX
from api.utils import read_excel_records, paginate

router = APIRouter(prefix="/jira", tags=["jira"])

@router.get("/health")
def health():
    try:
        rows = read_excel_records(JIRA_XLSX)
        return {"status": "ok", "records": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("")
def get_jira(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    rows = read_excel_records(JIRA_XLSX)
    return paginate(rows, limit=limit, offset=offset)
