from fastapi import FastAPI
from api.routers.generation import router as generation_router
from api.logging_config import setup_logging

setup_logging()
app = FastAPI()

app.include_router(generation_router)

@app.get("/health")
async def health():
    return {"status": "ok"}
