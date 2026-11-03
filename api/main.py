import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from api.routers.generation import router as generation_router
from api.routers.production import router as production_router
from api.logging_config import setup_logging
from infrastructure.compute.kaggle.notebook_control import KaggleCommandError, KaggleErrorCategory

setup_logging()
logger = logging.getLogger(__name__)
app = FastAPI()

app.include_router(generation_router)
app.include_router(production_router)

@app.exception_handler(KaggleCommandError)
async def kaggle_command_error_handler(request: Request, exc: KaggleCommandError):
    logger.error(f"Kaggle command error: {exc} (stderr: {exc.stderr})")
    if exc.category == KaggleErrorCategory.AUTH_OR_PERMISSION:
        return JSONResponse(status_code=502, content={"detail": "External compute provider authentication or permission failure."})
    elif exc.category in (KaggleErrorCategory.NETWORK_UNREACHABLE, KaggleErrorCategory.TRANSIENT_API):
        return JSONResponse(status_code=503, content={"detail": "External compute provider network or transient API error."})
    else:
        return JSONResponse(status_code=502, content={"detail": "External compute provider error."})

@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    logger.warning(f"Validation/Value error: {exc}")
    msg = str(exc)
    if "not found" in msg.lower():
        return JSONResponse(status_code=404, content={"detail": msg})
    return JSONResponse(status_code=400, content={"detail": msg})

@app.get("/health")
async def health():
    return {"status": "ok"}
