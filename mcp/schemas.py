from typing import List, Optional, Literal
from pydantic import BaseModel, Field

Priority = Literal["P1", "P2", "P3"]

class LinkedIssue(BaseModel):
    IssueID: str
    Summary: str
    Priority: Priority
    Status: str
    CreatedDate: Optional[str] = None
    ResolvedDate: Optional[str] = None
    EpicLink: Optional[str] = None

class UnifiedAccount(BaseModel):
    AccountID: str
    AccountName: str
    ARR: Optional[int] = None
    RenewalDate: Optional[str] = None
    Stage: Optional[str] = None
    Region: Optional[str] = None
    Industry: Optional[str] = None
    OpenIssues: int = 0
    OpenP1Issues: int = 0
    OpenP2Issues: int = 0
    OpenP3Issues: int = 0
    LastIssueDate: Optional[str] = None
    LinkedIssues: List[LinkedIssue] = []

class PaginationMeta(BaseModel):
    total: int
    limit: int
    offset: int
    count: int

class AccountsResponse(BaseModel):
    total: int
    limit: int
    offset: int
    count: int
    items: List[UnifiedAccount]
    meta: dict

class TopRevenueItem(BaseModel):
    AccountID: str
    AccountName: str
    ARR: Optional[int] = None
    RenewalDate: Optional[str] = None
    Region: Optional[str] = None
    Stage: Optional[str] = None
    OpenP1Issues: Optional[int] = None
    OpenP2Issues: Optional[int] = None
    OpenP3Issues: Optional[int] = None

class TopRevenueResponse(BaseModel):
    priority: str
    count: int
    items: List[TopRevenueItem]

class RenewalsItem(BaseModel):
    AccountID: str
    AccountName: str
    ARR: Optional[int] = None
    RenewalDate: Optional[str] = None
    Region: Optional[str] = None
    Stage: Optional[str] = None
    OpenIssues: int
    OpenP1Issues: Optional[int] = None
    OpenP2Issues: Optional[int] = None
    OpenP3Issues: Optional[int] = None

class RenewalsResponse(BaseModel):
    priority: str
    as_of: str
    window_days: int
    count: int
    items: List[RenewalsItem]

class CriticalItem(BaseModel):
    AccountID: str
    AccountName: str
    ARR: Optional[int] = None
    OpenIssues: int
    LastIssueDate: Optional[str] = None
    Region: Optional[str] = None
    OpenP1Issues: Optional[int] = None
    OpenP2Issues: Optional[int] = None
    OpenP3Issues: Optional[int] = None

class CriticalResponse(BaseModel):
    priority: str
    threshold: int
    count: int
    items: List[CriticalItem]

class SummaryBucket(BaseModel):
    accounts_with_open: int
    total_open: int
    median_arr_impacted: float

class SummaryResponse(BaseModel):
    total_accounts: int
    p1: SummaryBucket
    p2: SummaryBucket
    p3: SummaryBucket
