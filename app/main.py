from fastapi import FastAPI

app = FastAPI(
    title="MinIO Multi-Tenant Analytics",
    description="Analytics API for multi-location MinIO environments.",
    version="0.1.0",
)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
