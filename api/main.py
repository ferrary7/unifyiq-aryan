from fastapi import FastAPI
from api.salesforce.routes import router as salesforce_router
from api.jira.routes import router as jira_router

app = FastAPI(title="UnifyIQ", version="0.2.0")

@app.get("/")
def root():
    return {"message": "UnifyIQ API is live"}

@app.get("/health")
def health():
    return {"status": "ok"}

app.include_router(salesforce_router)
app.include_router(jira_router)
