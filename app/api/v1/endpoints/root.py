import socket

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def read_root():
    """Health check and container information endpoint."""
    return {
        "status": "online",
        "container_id": socket.gethostname(),
        "message": "Hello from inside the Docker container",
    }
