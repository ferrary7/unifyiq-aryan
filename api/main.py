from fastapi import FastAPI

app = FastAPI(title="UnifyIQ")

@app.get("/")
def root():
    return {"message": "UnifyIQ API is live"}

@app.get("/health")
def health():
    return {"status": "ok"}
