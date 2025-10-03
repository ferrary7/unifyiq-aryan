from fastapi import FastAPI
from api.salesforce.routes import router as salesforce_router
from api.jira.routes import router as jira_router
from mcp.routes import router as mcp_router
from mcp.insights import router as insights_router
from fastapi.middleware.cors import CORSMiddleware

tags_metadata = [
    {"name": "salesforce", "description": "Serve Salesforce account data"},
    {"name": "jira", "description": "Serve Jira issues data"},
    {"name": "mcp", "description": "Unification layer and data model"},
    {"name": "insights", "description": "Business insights over unified data"},
]

app = FastAPI(
    title="UnifyIQ",
    version="0.3.0",
    description="Unified data platform that blends Salesforce and Jira into one intelligent layer with insights.",
    contact={"name": "Aryan Sharma"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

@app.get("/", summary="Heartbeat")
def root():
    return {"message": "UnifyIQ API is live"}

@app.get("/health", summary="Health check")
def health():
    return {"status": "ok"}

app.include_router(salesforce_router)
app.include_router(jira_router)  
app.include_router(mcp_router)
app.include_router(insights_router)
