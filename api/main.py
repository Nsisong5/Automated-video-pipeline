from fastapi import FastAPI
from api.routers.generation import router as generation_router

app = FastAPI()

app.include_router(generation_router)

@app.get("/health")
async def health():
    return {"status": "ok"}
