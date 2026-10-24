from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import health
from app.core.config import settings

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """
    Standardize all HTTP error responses into {"error": {"message": "..."}} format.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"message": str(exc.detail)}},
    )


# Include API routers
app.include_router(health.router, prefix=settings.API_V1_STR)