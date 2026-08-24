import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.database import connect_to_mongo, close_mongo_connection, is_db_connected
from app.routes.cases import router as cases_router

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fraudlens.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up FraudLens FastAPI Backend...")
    try:
        await connect_to_mongo()
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB on startup: {str(e)}")
    yield
    logger.info("Shutting down FraudLens FastAPI Backend...")
    await close_mongo_connection()


app = FastAPI(
    title="FraudLens API",
    description="AI-powered financial fraud investigation system backend API",
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": exc.detail if isinstance(exc.detail, str) else str(exc.detail),
            "data": None
        }
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    error_messages = []
    for err in errors:
        loc = " -> ".join([str(x) for x in err.get("loc", []) if x != "body"])
        msg = err.get("msg", "Invalid input")
        error_messages.append(f"{loc}: {msg}" if loc else msg)

    detail_str = "; ".join(error_messages) if error_messages else "Validation Error"
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "message": f"Validation error: {detail_str}",
            "data": None
        }
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "message": f"Internal server error: {str(exc)}",
            "data": None
        }
    )


@app.get("/health", tags=["Health"])
async def health_check():
    db_connected = await is_db_connected()
    db_status = "connected" if db_connected else "disconnected"

    return {
        "success": db_connected,
        "service": "FraudLens API",
        "database": db_status
    }


app.include_router(cases_router)
