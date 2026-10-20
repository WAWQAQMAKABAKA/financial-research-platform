from fastapi import FastAPI

app = FastAPI(
    title="Financial Research Platform API",
    version="0.1.0",
)


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "research-api",
    }
