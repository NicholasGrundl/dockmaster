from typing import Annotated

from fastapi import FastAPI
from fastapi import Depends

from .logger_config import setup_uvicorn_logger

dev_logger = setup_uvicorn_logger(log_level="DEBUG")

app = FastAPI()

@app.get("/api/public")
def public():
    """No access token required to access this route"""

    result = {
        "status": "success",
        "msg": ("PUBLIC endpoint test")
    }
    return result

@app.get("/api/private")
def private():
    """A valid Authorization Bearer token is required to access this route"""

    
    result = {
        "status": "success",
        "msg": ("PRIVATE endpoint test")
    }
    return result

