from fastapi import FastAPI
from api.salesforce.routes import router as salesforce_router
from api.jira.routes import router as jira_router
from mcp.routes import router as mcp_router  
from mcp.insights import router as insights_router

app = FastAPI(title="UnifyIQ", version="0.3.0")

@app.get("/")
def root():
    return {"message": "UnifyIQ API is live"}

@app.get("/health")
def health():
    return {"status": "ok"}

app.include_router(salesforce_router)
app.include_router(jira_router)
app.include_router(mcp_router)
app.include_router(insights_router)