"""
Smite Panel - Central Controller
"""
import os
import asyncio
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
from app.routers import nodes, tunnels, panel, status, logs, auth
from app.hysteria2_server import Hysteria2Server
from app.gost_forwarder import gost_forwarder
from app.rathole_server import rathole_server_manager
from app.backhaul_manager import backhaul_manager
from app.chisel_server import chisel_server_manager
from app.hysteria2_client import Hysteria2Client
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    await init_db()
    
    h2_server = Hysteria2Server()
    await h2_server.start()
    app.state.h2_server = h2_server
    
    try:
        cert_path = Path(settings.hysteria2_cert_path)
        if not cert_path.is_absolute():
            cert_path = Path(os.getcwd()) / cert_path
        
        if not cert_path.exists() or cert_path.stat().st_size == 0:
            logger.info("Generating CA certificate on startup...")
            h2_server.cert_path = str(cert_path)
            h2_server.key_path = str(cert_path.parent / "ca.key")
            await h2_server._generate_certs()
            logger.info(f"CA certificate generated at {cert_path}")
    except Exception as e:
        logger.warning(f"Failed to generate CA certificate on startup: {e}")
    
    app.state.gost_forwarder = gost_forwarder
    
    app.state.rathole_server_manager = rathole_server_manager
    app.state.backhaul_manager = backhaul_manager
    app.state.chisel_server_manager = chisel_server_manager
    
    await _restore_forwards()
    
    await _restore_rathole_servers()
    await _restore_backhaul_servers()
    await _restore_chisel_servers()
    
    # Restore node-side tunnels after panel-side is restored
    await _restore_node_tunnels()
    
    yield
    
    if hasattr(app.state, 'h2_server'):
        await app.state.h2_server.stop()
    
    gost_forwarder.cleanup_all()
    
    rathole_server_manager.cleanup_all()
    backhaul_manager.cleanup_all()
    chisel_server_manager.cleanup_all()


async def _restore_forwards():
    """Restore forwarding for active tunnels on startup"""
    try:
        logger.info("Starting to restore forwarding for active tunnels...")
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Tunnel).where(Tunnel.status == "active"))
            tunnels = result.scalars().all()
            logger.info(f"Found {len(tunnels)} active tunnels to restore")
            
            for tunnel in tunnels:
                logger.info(f"Checking tunnel {tunnel.id}: type={tunnel.type}, core={tunnel.core}")
                needs_gost_forwarding = tunnel.type in ["tcp", "udp", "ws", "grpc", "tcpmux"] and tunnel.core == "xray"
                if not needs_gost_forwarding:
                    continue
                
                listen_port = tunnel.spec.get("listen_port")
                forward_to = tunnel.spec.get("forward_to")
                
                if not forward_to:
                    remote_ip = tunnel.spec.get("remote_ip", "127.0.0.1")
                    remote_port = tunnel.spec.get("remote_port", 8080)
                    forward_to = f"{remote_ip}:{remote_port}"
                
                panel_port = listen_port or tunnel.spec.get("remote_port")
                if not panel_port or not forward_to:
                    logger.warning(f"Tunnel {tunnel.id}: Missing panel_port or forward_to, skipping restore")
                    continue
                
                try:
                    use_ipv6 = tunnel.spec.get("use_ipv6", False)
                    logger.info(f"Restoring gost forwarding for tunnel {tunnel.id}: {tunnel.type}://:{panel_port} -> {forward_to}, use_ipv6={use_ipv6}")
                    gost_forwarder.start_forward(
                        tunnel_id=tunnel.id,
                        local_port=int(panel_port),
                        forward_to=forward_to,
                        tunnel_type=tunnel.type,
                        use_ipv6=bool(use_ipv6)
                    )
                    logger.info(f"Successfully restored gost forwarding for tunnel {tunnel.id}")
                except Exception as e:
                    logger.error(f"Failed to restore forwarding for tunnel {tunnel.id}: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Error restoring forwards: {e}")


async def _restore_rathole_servers():
    """Restore Rathole servers for active tunnels on startup"""
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Tunnel).where(Tunnel.status == "active"))
            tunnels = result.scalars().all()
            
            for tunnel in tunnels:
                if tunnel.core != "rathole":
                    continue
                
                remote_addr = tunnel.spec.get("remote_addr")
                token = tunnel.spec.get("token")
                proxy_port = tunnel.spec.get("remote_port") or tunnel.spec.get("listen_port")
                
                if not remote_addr or not token or not proxy_port:
                    continue
                
                use_ipv6 = tunnel.spec.get("use_ipv6", False)
                rathole_server_manager.start_server(
                    tunnel_id=tunnel.id,
                    remote_addr=remote_addr,
                    token=token,
                    proxy_port=int(proxy_port),
                    use_ipv6=bool(use_ipv6)
                )
    except Exception as e:
        logger.error(f"Error restoring Rathole servers: {e}")


async def _restore_backhaul_servers():
    """Restore Backhaul servers for active tunnels on startup"""
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Tunnel).where(Tunnel.status == "active"))
            tunnels = result.scalars().all()

            for tunnel in tunnels:
                if tunnel.core != "backhaul":
                    continue

                try:
                    backhaul_manager.start_server(tunnel.id, tunnel.spec or {})
                except Exception as exc:
                    logger.error(
                        "Failed to restore Backhaul server for tunnel %s: %s",
                        tunnel.id,
                        exc,
                    )
    except Exception as exc:
        logger.error("Error restoring Backhaul servers: %s", exc)


async def _restore_chisel_servers():
    """Restore Chisel servers for active tunnels on startup"""
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Tunnel).where(Tunnel.status == "active"))
            tunnels = result.scalars().all()
            
            for tunnel in tunnels:
                if tunnel.core != "chisel":
                    continue
                
                listen_port = tunnel.spec.get("listen_port") or tunnel.spec.get("remote_port") or tunnel.spec.get("server_port")
                auth = tunnel.spec.get("auth")
                fingerprint = tunnel.spec.get("fingerprint")
                
                if not listen_port:
                    continue
                
                try:
                    use_ipv6 = tunnel.spec.get("use_ipv6", False)
                    chisel_server_manager.start_server(
                        tunnel_id=tunnel.id,
                        server_port=int(listen_port),
                        auth=auth,
                        fingerprint=fingerprint,
                        use_ipv6=bool(use_ipv6)
                    )
                except Exception as exc:
                    logger.error(
                        "Failed to restore Chisel server for tunnel %s: %s",
                        tunnel.id,
                        exc,
                    )
    except Exception as exc:
        logger.error("Error restoring Chisel servers: %s", exc)


async def _restore_node_tunnels():
    """Restore node-side tunnels for active tunnels after panel restart"""
    try:
        logger.info("Starting to restore node-side tunnels...")
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Tunnel).where(Tunnel.status == "active"))
            tunnels = result.scalars().all()
            
            # Filter tunnels that need node-side restoration
            node_tunnels = [t for t in tunnels if t.core in ["rathole", "backhaul", "chisel"] and t.node_id]
            
            if not node_tunnels:
                logger.info("No node-side tunnels to restore")
                return
            
            logger.info(f"Found {len(node_tunnels)} active node-side tunnels to restore")
            
            client = Hysteria2Client()
            
            for tunnel in node_tunnels:
                try:
                    result = await db.execute(select(Node).where(Node.id == tunnel.node_id))
                    node = result.scalar_one_or_none()
                    if not node:
                        logger.warning(f"Tunnel {tunnel.id}: Node {tunnel.node_id} not found, skipping")
                        continue
                    
                    # Prepare spec for node
                    spec_for_node = tunnel.spec.copy() if tunnel.spec else {}
                    
                    # For Chisel, construct server_url
                    if tunnel.core == "chisel":
                        listen_port = spec_for_node.get("listen_port") or spec_for_node.get("remote_port") or spec_for_node.get("server_port")
                        use_ipv6 = spec_for_node.get("use_ipv6", False)
                        if listen_port:
                            # Get panel host - prioritize spec.panel_host (set by frontend)
                            panel_host = spec_for_node.get("panel_host")
                            
                            # If not in spec, try node's panel_address from metadata
                            if not panel_host:
                                panel_address = node.node_metadata.get("panel_address", "")
                                if panel_address:
                                    # Extract host from panel_address
                                    if "://" in panel_address:
                                        panel_address = panel_address.split("://", 1)[1]
                                    if ":" in panel_address:
                                        panel_host = panel_address.split(":")[0]
                                    else:
                                        panel_host = panel_address
                            
                            # Fallback: use panel_domain from settings
                            if not panel_host or panel_host in ["localhost", "127.0.0.1", "::1"]:
                                if settings.panel_domain:
                                    panel_host = settings.panel_domain
                            
                            # Final fallback: use node's fingerprint (if it's an IP)
                            if not panel_host or panel_host in ["localhost", "127.0.0.1", "::1"]:
                                # Try to use node's IP from metadata
                                node_ip = node.node_metadata.get("ip_address") or node.fingerprint
                                if node_ip and node_ip not in ["localhost", "127.0.0.1", "::1"]:
                                    panel_host = node_ip
                                else:
                                    logger.warning(f"Chisel tunnel {tunnel.id}: Could not determine panel host, using localhost. Node may not be able to connect.")
                                    panel_host = "localhost"
                            
                            # Format host for IPv6 (needs brackets)
                            from app.utils import format_address_port
                            if use_ipv6:
                                formatted_host = format_address_port(panel_host, None)
                                if "[" in formatted_host:
                                    server_url = f"http://{formatted_host}:{listen_port}"
                                else:
                                    server_url = f"http://[::1]:{listen_port}"
                            else:
                                server_url = f"http://{panel_host}:{listen_port}"
                            
                            spec_for_node["server_url"] = server_url
                            spec_for_node["remote_port"] = int(listen_port)
                            logger.info(f"Chisel tunnel {tunnel.id}: server_url={server_url}, listen_port={listen_port}, use_ipv6={use_ipv6}, panel_host={panel_host}")
                    
                    # Ensure node has api_address
                    if not node.node_metadata.get("api_address"):
                        node.node_metadata["api_address"] = f"http://{node.node_metadata.get('ip_address', node.fingerprint)}:{node.node_metadata.get('api_port', 8888)}"
                        await db.commit()
                    
                    # Apply tunnel to node
                    logger.info(f"Restoring tunnel {tunnel.id} on node {node.id}")
                    response = await client.send_to_node(
                        node_id=node.id,
                        endpoint="/api/agent/tunnels/apply",
                        data={
                            "tunnel_id": tunnel.id,
                            "core": tunnel.core,
                            "type": tunnel.type,
                            "spec": spec_for_node
                        }
                    )
                    
                    if response.get("status") == "error":
                        error_msg = response.get("message", "Unknown error from node")
                        logger.error(f"Failed to restore tunnel {tunnel.id} on node {node.id}: {error_msg}")
                    else:
                        logger.info(f"Successfully restored tunnel {tunnel.id} on node {node.id}")
                        
                except Exception as e:
                    logger.error(f"Failed to restore tunnel {tunnel.id} on node: {e}", exc_info=True)
                    
    except Exception as e:
        logger.error(f"Error restoring node tunnels: {e}", exc_info=True)


app = FastAPI(
    title="Smite Panel",
    description="Tunneling Control Panel",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(panel.router, prefix="/api/panel", tags=["panel"])
app.include_router(nodes.router, prefix="/api/nodes", tags=["nodes"])
app.include_router(tunnels.router, prefix="/api/tunnels", tags=["tunnels"])
app.include_router(status.router, prefix="/api/status", tags=["status"])
app.include_router(logs.router, prefix="/api/logs", tags=["logs"])

static_dir = os.path.join(os.path.dirname(__file__), "static")
static_path = Path(static_dir)

if static_path.exists() and (static_path / "index.html").exists():
    app.mount("/static", StaticFiles(directory=static_path), name="static-assets")
    
    from fastapi.responses import FileResponse
    
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Serve frontend for all non-API routes"""
        if full_path.startswith("api/") or full_path.startswith("docs") or full_path.startswith("redoc") or full_path.startswith("openapi.json"):
            raise HTTPException(status_code=404)
        
        file_path = static_path / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        
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
    
    if settings.https_enabled:
        import ssl
        cert_path = Path(settings.https_cert_path).resolve()
        key_path = Path(settings.https_key_path).resolve()
        
        if not cert_path.exists() or not key_path.exists():
            logger.warning(f"HTTPS enabled but certificate files not found. Using HTTP.")
            uvicorn.run(app, host=settings.panel_host, port=settings.panel_port)
        else:
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_context.load_cert_chain(str(cert_path), str(key_path))
            uvicorn.run(
                app,
                host=settings.panel_host,
                port=settings.panel_port,
                ssl_keyfile=str(key_path),
                ssl_certfile=str(cert_path)
            )
    else:
        uvicorn.run(app, host=settings.panel_host, port=settings.panel_port)
