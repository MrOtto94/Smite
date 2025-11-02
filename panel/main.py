"""
Smite Panel - Central Controller
"""
import os
from contextlib import asynccontextmanager
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models import Tunnel, Node

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db
from app.routers import nodes, tunnels, panel, usage, status, logs
from app.hysteria2_server import Hysteria2Server
from app.port_forwarder import port_forwarder
import logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    # Initialize database
    await init_db()
    
    # Start Hysteria2 server if enabled (cert generation)
    h2_server = Hysteria2Server()
    await h2_server.start()
    app.state.h2_server = h2_server
    
    # Initialize port forwarder
    app.state.port_forwarder = port_forwarder
    
    # Restore active tunnels' port forwarding on startup
    await _restore_port_forwards()
    
    yield
    
    # Shutdown
    if hasattr(app.state, 'h2_server'):
        await app.state.h2_server.stop()
    
    # Stop all port forwarding
    await port_forwarder.cleanup_all()


async def _restore_port_forwards():
    """Restore port forwarding for active tunnels on startup"""
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Tunnel).where(Tunnel.status == "active"))
            tunnels = result.scalars().all()
            
            for tunnel in tunnels:
                remote_port = tunnel.spec.get("remote_port") or tunnel.spec.get("listen_port")
                if not remote_port:
                    continue
                
                # Get node
                node_result = await db.execute(select(Node).where(Node.id == tunnel.node_id))
                node = node_result.scalar_one_or_none()
                if not node:
                    continue
                
                # Get node address
                node_address = node.node_metadata.get("ip_address") if node.node_metadata else None
                if not node_address:
                    continue
                
                # Start forwarding
                await port_forwarder.start_forward(
                    local_port=int(remote_port),
                    node_address=node_address,
                    remote_port=int(remote_port)
                )
    except Exception as e:
        logger.error(f"Error restoring port forwards: {e}")


app = FastAPI(
    title="Smite Panel",
    description="Tunneling Control Panel",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(panel.router, prefix="/api/panel", tags=["panel"])
app.include_router(nodes.router, prefix="/api/nodes", tags=["nodes"])
app.include_router(tunnels.router, prefix="/api/tunnels", tags=["tunnels"])
app.include_router(usage.router, prefix="/api/usage", tags=["usage"])
app.include_router(status.router, prefix="/api/status", tags=["status"])
app.include_router(logs.router, prefix="/api/logs", tags=["logs"])

# Serve frontend static files if available
static_dir = os.path.join(os.path.dirname(__file__), "static")
static_path = Path(static_dir)

if static_path.exists() and (static_path / "index.html").exists():
    # Mount static files
    app.mount("/static", StaticFiles(directory=static_path), name="static-assets")
    
    # Serve index.html for all non-API routes (SPA routing)
    from fastapi.responses import FileResponse
    
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Serve frontend for all non-API routes"""
        # Don't interfere with API routes
        if full_path.startswith("api/") or full_path.startswith("docs") or full_path.startswith("redoc") or full_path.startswith("openapi.json"):
            raise HTTPException(status_code=404)
        
        # Check if it's a static file request
        file_path = static_path / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        
        # Otherwise serve index.html for SPA routing
        index_path = static_path / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        raise HTTPException(status_code=404)

@app.get("/")
async def root():
    """Root redirect"""
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    index_path = Path(static_dir) / "index.html"
    if index_path.exists():
        from fastapi.responses import FileResponse
        return FileResponse(index_path)
    return {"message": "Smite Panel API", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
