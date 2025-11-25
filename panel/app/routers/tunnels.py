"""Tunnels API endpoints"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from datetime import datetime
from pydantic import BaseModel
import logging
import time

from app.database import get_db
from app.models import Tunnel, Node
from app.hysteria2_client import Hysteria2Client


router = APIRouter()
logger = logging.getLogger(__name__)


def prepare_frp_spec_for_node(spec: dict, node: Node, request: Request) -> dict:
    """Prepare FRP spec for node by determining correct server_addr from node metadata"""
    spec_for_node = spec.copy()
    bind_port = spec_for_node.get("bind_port", 7000)
    token = spec_for_node.get("token")
    
    # Get panel address from node's metadata (set during node registration)
    panel_address = node.node_metadata.get("panel_address", "")
    panel_host = None
    
    logger.debug(f"FRP tunnel: node metadata panel_address={panel_address}, node_metadata keys={list(node.node_metadata.keys())}")
    
    if panel_address:
        # Parse panel_address (can be "host:port" or "http://host:port" or "https://host:port")
        if "://" in panel_address:
            panel_address = panel_address.split("://", 1)[1]
        if ":" in panel_address:
            panel_host = panel_address.split(":")[0]
        else:
            panel_host = panel_address
        logger.debug(f"FRP tunnel: parsed panel_host from panel_address: {panel_host}")
    
    # Fallback to spec panel_host if metadata doesn't have it
    if not panel_host or panel_host in ["localhost", "127.0.0.1", "::1", "0.0.0.0"]:
        panel_host = spec_for_node.get("panel_host")
        if panel_host:
            if "://" in panel_host:
                panel_host = panel_host.split("://", 1)[1]
            if ":" in panel_host:
                panel_host = panel_host.split(":")[0]
            logger.debug(f"FRP tunnel: using panel_host from spec: {panel_host}")
    
    # Try X-Forwarded-Host header
    if not panel_host or panel_host in ["localhost", "127.0.0.1", "::1", "0.0.0.0"]:
        forwarded_host = request.headers.get("X-Forwarded-Host")
        if forwarded_host:
            panel_host = forwarded_host.split(":")[0] if ":" in forwarded_host else forwarded_host
            logger.debug(f"FRP tunnel: using panel_host from X-Forwarded-Host: {panel_host}")
    
    # Try request hostname (but reject 0.0.0.0, None, and empty)
    if not panel_host or panel_host in ["localhost", "127.0.0.1", "::1", "0.0.0.0"]:
        request_host = request.url.hostname if request.url else None
        if request_host and request_host not in ["localhost", "127.0.0.1", "::1", "0.0.0.0", ""]:
            panel_host = request_host
            logger.debug(f"FRP tunnel: using panel_host from request.url.hostname: {panel_host}")
    
    # Try environment variable as last resort
    if not panel_host or panel_host in ["localhost", "127.0.0.1", "::1", "0.0.0.0"]:
        import os
        panel_public_ip = os.getenv("PANEL_PUBLIC_IP") or os.getenv("PANEL_IP")
        if panel_public_ip and panel_public_ip not in ["localhost", "127.0.0.1", "::1", "0.0.0.0", ""]:
            panel_host = panel_public_ip
            logger.debug(f"FRP tunnel: using panel_host from environment: {panel_host}")
    
    # If still no valid host, raise error with detailed information
    if not panel_host or panel_host in ["localhost", "127.0.0.1", "::1", "0.0.0.0", ""]:
        error_details = {
            "node_id": node.id,
            "node_name": node.name,
            "node_metadata_panel_address": panel_address,
            "node_metadata_keys": list(node.node_metadata.keys()),
            "request_hostname": request.url.hostname if request.url else None,
            "x_forwarded_host": request.headers.get("X-Forwarded-Host"),
            "env_panel_public_ip": os.getenv("PANEL_PUBLIC_IP"),
            "env_panel_ip": os.getenv("PANEL_IP"),
        }
        error_msg = f"Cannot determine panel address for FRP tunnel. Details: {error_details}. Please ensure node has correct PANEL_ADDRESS configured (node should register with panel_address in metadata) or set PANEL_PUBLIC_IP environment variable on panel."
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    from app.utils import is_valid_ipv6_address
    if is_valid_ipv6_address(panel_host):
        server_addr = f"[{panel_host}]"
    else:
        server_addr = panel_host
    
    spec_for_node["server_addr"] = server_addr
    spec_for_node["server_port"] = int(bind_port)
    if token:
        spec_for_node["token"] = token
    
    logger.info(f"FRP spec prepared: server_addr={server_addr}, server_port={bind_port}, token={'set' if token else 'none'}, panel_host={panel_host} (from node panel_address: {panel_address})")
    return spec_for_node


class TunnelCreate(BaseModel):
    name: str
    core: str
    type: str
    node_id: str | None = None
    spec: dict


class TunnelUpdate(BaseModel):
    name: str | None = None
    spec: dict | None = None


class TunnelResponse(BaseModel):
    id: str
    name: str
    core: str
    type: str
    node_id: str
    spec: dict
    status: str
    error_message: str | None = None
    revision: int
    used_mb: float = 0.0
    quota_mb: float = 0.0
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


@router.post("", response_model=TunnelResponse)
async def create_tunnel(tunnel: TunnelCreate, request: Request, db: AsyncSession = Depends(get_db)):
    """Create a new tunnel and auto-apply it"""
    from app.hysteria2_client import Hysteria2Client
    
    logger.info(f"Creating tunnel: name={tunnel.name}, type={tunnel.type}, core={tunnel.core}, node_id={tunnel.node_id}")
    
    node = None
    if tunnel.node_id:
        result = await db.execute(select(Node).where(Node.id == tunnel.node_id))
        node = result.scalar_one_or_none()
        if not node:
            raise HTTPException(status_code=404, detail="Node not found")
    elif tunnel.core in {"rathole", "backhaul", "chisel", "frp"}:
        raise HTTPException(status_code=400, detail=f"Node is required for {tunnel.core.title()} tunnels")
    
    db_tunnel = Tunnel(
        name=tunnel.name,
        core=tunnel.core,
        type=tunnel.type,
        node_id=tunnel.node_id or "",
        spec=tunnel.spec,
        status="pending"
    )
    db.add(db_tunnel)
    await db.commit()
    await db.refresh(db_tunnel)
    
    try:
        needs_gost_forwarding = db_tunnel.type in ["tcp", "udp", "ws", "grpc", "tcpmux"] and db_tunnel.core == "xray"
        needs_rathole_server = db_tunnel.core == "rathole"
        needs_backhaul_server = db_tunnel.core == "backhaul"
        needs_chisel_server = db_tunnel.core == "chisel"
        needs_frp_server = db_tunnel.core == "frp"
        needs_node_apply = db_tunnel.core in {"rathole", "backhaul", "chisel", "frp"}
        
        logger.info(
            "Tunnel %s: gost=%s, rathole=%s, backhaul=%s, chisel=%s, frp=%s",
            db_tunnel.id,
            needs_gost_forwarding,
            needs_rathole_server,
            needs_backhaul_server,
            needs_chisel_server,
            needs_frp_server,
        )
        
        backhaul_started = False
        rathole_started = False
        chisel_started = False
        frp_started = False
        
        if needs_backhaul_server:
            manager = getattr(request.app.state, "backhaul_manager", None)
            if not manager:
                db_tunnel.status = "error"
                db_tunnel.error_message = "Backhaul manager not initialized on panel"
                await db.commit()
                await db.refresh(db_tunnel)
                return db_tunnel
            try:
                logger.info("Starting Backhaul server for tunnel %s", db_tunnel.id)
                manager.start_server(db_tunnel.id, db_tunnel.spec or {})
                time.sleep(1.5)
                if not manager.is_running(db_tunnel.id):
                    raise RuntimeError("Backhaul process started but is not running")
                backhaul_started = True
                logger.info("Started Backhaul server for tunnel %s", db_tunnel.id)
            except Exception as exc:
                error_msg = f"Backhaul server error: {exc}"
                logger.error("Failed to start Backhaul server for tunnel %s: %s", db_tunnel.id, exc, exc_info=True)
                db_tunnel.status = "error"
                db_tunnel.error_message = error_msg
                await db.commit()
                await db.refresh(db_tunnel)
                return db_tunnel
        
        if needs_rathole_server:
            remote_addr = db_tunnel.spec.get("remote_addr")
            token = db_tunnel.spec.get("token")
            proxy_port = db_tunnel.spec.get("remote_port") or db_tunnel.spec.get("listen_port")
            use_ipv6 = db_tunnel.spec.get("use_ipv6", False)
            
            if remote_addr:
                from app.utils import parse_address_port
                _, rathole_port, _ = parse_address_port(remote_addr)
                try:
                    if rathole_port and int(rathole_port) == 8000:
                        db_tunnel.status = "error"
                        db_tunnel.error_message = "Rathole server cannot use port 8000 (panel API port). Use a different port like 23333."
                        await db.commit()
                        await db.refresh(db_tunnel)
                        return db_tunnel
                except (ValueError, TypeError):
                    pass
            
            if remote_addr and token and proxy_port and hasattr(request.app.state, 'rathole_server_manager'):
                try:
                    logger.info(f"Starting Rathole server for tunnel {db_tunnel.id}: remote_addr={remote_addr}, token={token}, proxy_port={proxy_port}, use_ipv6={use_ipv6}")
                    request.app.state.rathole_server_manager.start_server(
                        tunnel_id=db_tunnel.id,
                        remote_addr=remote_addr,
                        token=token,
                        proxy_port=int(proxy_port),
                        use_ipv6=bool(use_ipv6)
                    )
                    logger.info(f"Successfully started Rathole server for tunnel {db_tunnel.id}")
                    rathole_started = True
                except Exception as e:
                    error_msg = str(e)
                    logger.error(f"Failed to start Rathole server for tunnel {db_tunnel.id}: {error_msg}", exc_info=True)
                    db_tunnel.status = "error"
                    db_tunnel.error_message = f"Rathole server error: {error_msg}"
                    await db.commit()
                    await db.refresh(db_tunnel)
                    return db_tunnel
            else:
                missing = []
                if not remote_addr:
                    missing.append("remote_addr")
                if not token:
                    missing.append("token")
                if not proxy_port:
                    missing.append("proxy_port")
                if not hasattr(request.app.state, 'rathole_server_manager'):
                    missing.append("rathole_server_manager")
                logger.warning(f"Tunnel {db_tunnel.id}: Missing required fields for Rathole server: {missing}")
                if not remote_addr or not token or not proxy_port:
                    db_tunnel.status = "error"
                    db_tunnel.error_message = f"Missing required fields for Rathole: {missing}"
                    await db.commit()
                    await db.refresh(db_tunnel)
                    return db_tunnel
        
        if needs_chisel_server:
            listen_port = db_tunnel.spec.get("listen_port") or db_tunnel.spec.get("remote_port") or db_tunnel.spec.get("server_port")
            auth = db_tunnel.spec.get("auth")
            fingerprint = db_tunnel.spec.get("fingerprint")
            use_ipv6 = db_tunnel.spec.get("use_ipv6", False)
            
            if listen_port:
                from app.utils import parse_address_port
                try:
                    if int(listen_port) == 8000:
                        db_tunnel.status = "error"
                        db_tunnel.error_message = "Chisel server cannot use port 8000 (panel API port). Use a different port."
                        await db.commit()
                        await db.refresh(db_tunnel)
                        return db_tunnel
                except (ValueError, TypeError):
                    pass
            
            if listen_port and hasattr(request.app.state, 'chisel_server_manager'):
                try:
                    server_control_port = db_tunnel.spec.get("control_port")
                    if server_control_port:
                        server_control_port = int(server_control_port)
                    else:
                        server_control_port = int(listen_port) + 10000
                    logger.info(f"Starting Chisel server for tunnel {db_tunnel.id}: server_control_port={server_control_port}, reverse_port={listen_port}, auth={auth is not None}, fingerprint={fingerprint is not None}, use_ipv6={use_ipv6}")
                    request.app.state.chisel_server_manager.start_server(
                        tunnel_id=db_tunnel.id,
                        server_port=server_control_port,
                        auth=auth,
                        fingerprint=fingerprint,
                        use_ipv6=bool(use_ipv6)
                    )
                    time.sleep(1.0)
                    if not request.app.state.chisel_server_manager.is_running(db_tunnel.id):
                        raise RuntimeError("Chisel server process started but is not running")
                    chisel_started = True
                    logger.info(f"Successfully started Chisel server for tunnel {db_tunnel.id}")
                except Exception as e:
                    error_msg = str(e)
                    logger.error(f"Failed to start Chisel server for tunnel {db_tunnel.id}: {error_msg}", exc_info=True)
                    db_tunnel.status = "error"
                    db_tunnel.error_message = f"Chisel server error: {error_msg}"
                    await db.commit()
                    await db.refresh(db_tunnel)
                    return db_tunnel
            else:
                missing = []
                if not listen_port:
                    missing.append("listen_port")
                if not hasattr(request.app.state, 'chisel_server_manager'):
                    missing.append("chisel_server_manager")
                logger.warning(f"Tunnel {db_tunnel.id}: Missing required fields for Chisel server: {missing}")
                if not listen_port:
                    db_tunnel.status = "error"
                    db_tunnel.error_message = f"Missing required fields for Chisel: {missing}"
                    await db.commit()
                    await db.refresh(db_tunnel)
                    return db_tunnel
        
        if needs_frp_server:
            bind_port = db_tunnel.spec.get("bind_port", 7000)
            token = db_tunnel.spec.get("token")
            
            if bind_port:
                from app.utils import parse_address_port
                try:
                    if int(bind_port) == 8000:
                        db_tunnel.status = "error"
                        db_tunnel.error_message = "FRP server cannot use port 8000 (panel API port). Use a different port like 7000."
                        await db.commit()
                        await db.refresh(db_tunnel)
                        return db_tunnel
                except (ValueError, TypeError):
                    pass
            
            if bind_port and hasattr(request.app.state, 'frp_server_manager'):
                try:
                    logger.info(f"Starting FRP server for tunnel {db_tunnel.id}: bind_port={bind_port}, token={'set' if token else 'none'}")
                    request.app.state.frp_server_manager.start_server(
                        tunnel_id=db_tunnel.id,
                        bind_port=int(bind_port),
                        token=token
                    )
                    time.sleep(1.0)
                    if not request.app.state.frp_server_manager.is_running(db_tunnel.id):
                        raise RuntimeError("FRP server process started but is not running")
                    frp_started = True
                    logger.info(f"Successfully started FRP server for tunnel {db_tunnel.id}")
                except Exception as e:
                    error_msg = str(e)
                    logger.error(f"Failed to start FRP server for tunnel {db_tunnel.id}: {error_msg}", exc_info=True)
                    db_tunnel.status = "error"
                    db_tunnel.error_message = f"FRP server error: {error_msg}"
                    await db.commit()
                    await db.refresh(db_tunnel)
                    return db_tunnel
            else:
                missing = []
                if not bind_port:
                    missing.append("bind_port")
                if not hasattr(request.app.state, 'frp_server_manager'):
                    missing.append("frp_server_manager")
                logger.warning(f"Tunnel {db_tunnel.id}: Missing required fields for FRP server: {missing}")
                if not bind_port:
                    db_tunnel.status = "error"
                    db_tunnel.error_message = f"Missing required fields for FRP: {missing}"
                    await db.commit()
                    await db.refresh(db_tunnel)
                    return db_tunnel
        
        if needs_node_apply:
            if not node:
                raise HTTPException(status_code=400, detail=f"Node is required for {db_tunnel.core.title()} tunnels")
            
            client = Hysteria2Client()
            if not node.node_metadata.get("api_address"):
                node.node_metadata["api_address"] = f"http://{node.node_metadata.get('ip_address', node.fingerprint)}:{node.node_metadata.get('api_port', 8888)}"
                await db.commit()
            
            spec_for_node = db_tunnel.spec.copy() if db_tunnel.spec else {}
            
            if needs_chisel_server:
                listen_port = spec_for_node.get("listen_port") or spec_for_node.get("remote_port") or spec_for_node.get("server_port")
                use_ipv6 = spec_for_node.get("use_ipv6", False)
                if listen_port:
                    server_control_port = spec_for_node.get("control_port")
                    if server_control_port:
                        server_control_port = int(server_control_port)
                    else:
                        server_control_port = int(listen_port) + 10000
                    reverse_port = int(listen_port)
                    
                    panel_host = spec_for_node.get("panel_host")
                    
                    if not panel_host:
                        panel_address = node.node_metadata.get("panel_address", "")
                        if panel_address:
                            if "://" in panel_address:
                                panel_address = panel_address.split("://", 1)[1]
                            if ":" in panel_address:
                                panel_host = panel_address.split(":")[0]
                            else:
                                panel_host = panel_address
                    
                    if not panel_host or panel_host in ["localhost", "127.0.0.1", "::1"]:
                        panel_host = request.url.hostname
                        if not panel_host or panel_host in ["localhost", "127.0.0.1", "::1"]:
                            forwarded_host = request.headers.get("X-Forwarded-Host")
                            if forwarded_host:
                                panel_host = forwarded_host.split(":")[0] if ":" in forwarded_host else forwarded_host
                    
                    if not panel_host or panel_host in ["localhost", "127.0.0.1", "::1"]:
                        logger.warning(f"Chisel tunnel {db_tunnel.id}: Could not determine panel host, using request hostname: {request.url.hostname}. Node may not be able to connect if this is localhost.")
                        panel_host = request.url.hostname or "localhost"
                    
                    from app.utils import is_valid_ipv6_address
                    if is_valid_ipv6_address(panel_host):
                        server_url = f"http://[{panel_host}]:{server_control_port}"
                    else:
                        server_url = f"http://{panel_host}:{server_control_port}"
                    spec_for_node["server_url"] = server_url
                    spec_for_node["reverse_port"] = reverse_port
                    spec_for_node["remote_port"] = int(listen_port)
                    logger.info(f"Chisel tunnel {db_tunnel.id}: server_url={server_url}, server_control_port={server_control_port}, reverse_port={reverse_port}, use_ipv6={use_ipv6}, panel_host={panel_host}")
            
            if needs_frp_server:
                spec_for_node = prepare_frp_spec_for_node(spec_for_node, node, request)
            
            logger.info(f"Applying tunnel {db_tunnel.id} to node {node.id}")
            response = await client.send_to_node(
                node_id=node.id,
                endpoint="/api/agent/tunnels/apply",
                data={
                    "tunnel_id": db_tunnel.id,
                    "core": db_tunnel.core,
                    "type": db_tunnel.type,
                    "spec": spec_for_node
                }
            )
            
            if response.get("status") == "error":
                db_tunnel.status = "error"
                error_msg = response.get("message", "Unknown error from node")
                db_tunnel.error_message = f"Node error: {error_msg}"
                logger.error(f"Tunnel {db_tunnel.id}: {error_msg}")
                if needs_rathole_server and hasattr(request.app.state, 'rathole_server_manager'):
                    try:
                        request.app.state.rathole_server_manager.stop_server(db_tunnel.id)
                    except:
                        pass
                if needs_backhaul_server and hasattr(request.app.state, "backhaul_manager"):
                    try:
                        request.app.state.backhaul_manager.stop_server(db_tunnel.id)
                    except Exception:
                        pass
                if needs_chisel_server and hasattr(request.app.state, 'chisel_server_manager'):
                    try:
                        request.app.state.chisel_server_manager.stop_server(db_tunnel.id)
                    except Exception:
                        pass
                if needs_frp_server and hasattr(request.app.state, 'frp_server_manager'):
                    try:
                        request.app.state.frp_server_manager.stop_server(db_tunnel.id)
                    except Exception:
                        pass
                await db.commit()
                await db.refresh(db_tunnel)
                return db_tunnel
            
            if response.get("status") != "success":
                db_tunnel.status = "error"
                db_tunnel.error_message = "Failed to apply tunnel to node. Check node connection."
                logger.error(f"Tunnel {db_tunnel.id}: Failed to apply to node")
                if needs_rathole_server and hasattr(request.app.state, 'rathole_server_manager'):
                    try:
                        request.app.state.rathole_server_manager.stop_server(db_tunnel.id)
                    except:
                        pass
                if needs_backhaul_server and hasattr(request.app.state, "backhaul_manager"):
                    try:
                        request.app.state.backhaul_manager.stop_server(db_tunnel.id)
                    except Exception:
                        pass
                if needs_chisel_server and hasattr(request.app.state, 'chisel_server_manager'):
                    try:
                        request.app.state.chisel_server_manager.stop_server(db_tunnel.id)
                    except Exception:
                        pass
                if needs_frp_server and hasattr(request.app.state, 'frp_server_manager'):
                    try:
                        request.app.state.frp_server_manager.stop_server(db_tunnel.id)
                    except Exception:
                        pass
                await db.commit()
                await db.refresh(db_tunnel)
                return db_tunnel
        
        db_tunnel.status = "active"
        
        try:
            
            if needs_gost_forwarding:
                listen_port = db_tunnel.spec.get("listen_port")
                forward_to = db_tunnel.spec.get("forward_to")
                
                if not forward_to:
                    from app.utils import format_address_port
                    remote_ip = db_tunnel.spec.get("remote_ip", "127.0.0.1")
                    remote_port = db_tunnel.spec.get("remote_port", 8080)
                    forward_to = format_address_port(remote_ip, remote_port)
                
                panel_port = listen_port or db_tunnel.spec.get("remote_port")
                use_ipv6 = db_tunnel.spec.get("use_ipv6", False)
                
                if panel_port and forward_to and hasattr(request.app.state, 'gost_forwarder'):
                    try:
                        logger.info(f"Starting gost forwarding for tunnel {db_tunnel.id}: {db_tunnel.type}://:{panel_port} -> {forward_to}, use_ipv6={use_ipv6}")
                        request.app.state.gost_forwarder.start_forward(
                            tunnel_id=db_tunnel.id,
                            local_port=int(panel_port),
                            forward_to=forward_to,
                            tunnel_type=db_tunnel.type,
                            use_ipv6=bool(use_ipv6)
                        )
                        time.sleep(2)
                        if not request.app.state.gost_forwarder.is_forwarding(db_tunnel.id):
                            raise RuntimeError("Gost process started but is not running")
                        logger.info(f"Successfully started gost forwarding for tunnel {db_tunnel.id}")
                    except Exception as e:
                        error_msg = str(e)
                        logger.error(f"Failed to start gost forwarding for tunnel {db_tunnel.id}: {error_msg}", exc_info=True)
                        db_tunnel.status = "error"
                        db_tunnel.error_message = f"Gost forwarding error: {error_msg}"
                        await db.commit()
                        await db.refresh(db_tunnel)
                        return db_tunnel
                else:
                    missing = []
                    if not panel_port:
                        missing.append("panel_port")
                    if not forward_to:
                        missing.append("forward_to")
                    if not hasattr(request.app.state, 'gost_forwarder'):
                        missing.append("gost_forwarder")
                    logger.warning(f"Tunnel {db_tunnel.id}: Missing required fields: {missing}")
                    if not forward_to:
                        error_msg = "forward_to is required for gost tunnels"
                        db_tunnel.status = "error"
                        db_tunnel.error_message = error_msg
            
        except Exception as e:
            logger.error(f"Exception in forwarding setup for tunnel {db_tunnel.id}: {e}", exc_info=True)
        
        await db.commit()
        await db.refresh(db_tunnel)
    except Exception as e:
        logger.error(f"Exception in tunnel creation for {db_tunnel.id}: {e}", exc_info=True)
        error_msg = str(e)
        db_tunnel.status = "error"
        db_tunnel.error_message = f"Tunnel creation error: {error_msg}"
        try:
            if needs_rathole_server and hasattr(request.app.state, "rathole_server_manager"):
                request.app.state.rathole_server_manager.stop_server(db_tunnel.id)
        except Exception:
            pass
        try:
            if needs_backhaul_server and hasattr(request.app.state, "backhaul_manager"):
                request.app.state.backhaul_manager.stop_server(db_tunnel.id)
        except Exception:
            pass
        await db.commit()
        await db.refresh(db_tunnel)
    
    return db_tunnel


@router.get("", response_model=List[TunnelResponse])
async def list_tunnels(db: AsyncSession = Depends(get_db)):
    """List all tunnels"""
    result = await db.execute(select(Tunnel))
    tunnels = result.scalars().all()
    return tunnels


@router.get("/{tunnel_id}", response_model=TunnelResponse)
async def get_tunnel(tunnel_id: str, db: AsyncSession = Depends(get_db)):
    """Get tunnel by ID"""
    result = await db.execute(select(Tunnel).where(Tunnel.id == tunnel_id))
    tunnel = result.scalar_one_or_none()
    if not tunnel:
        raise HTTPException(status_code=404, detail="Tunnel not found")
    return tunnel


@router.put("/{tunnel_id}", response_model=TunnelResponse)
async def update_tunnel(
    tunnel_id: str,
    tunnel_update: TunnelUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Update a tunnel and re-apply if spec changed"""
    from app.hysteria2_client import Hysteria2Client
    
    result = await db.execute(select(Tunnel).where(Tunnel.id == tunnel_id))
    tunnel = result.scalar_one_or_none()
    if not tunnel:
        raise HTTPException(status_code=404, detail="Tunnel not found")
    
    spec_changed = tunnel_update.spec is not None and tunnel_update.spec != tunnel.spec
    
    if tunnel_update.name is not None:
        tunnel.name = tunnel_update.name
    if tunnel_update.spec is not None:
        tunnel.spec = tunnel_update.spec
    
    tunnel.revision += 1
    tunnel.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(tunnel)
    
    if spec_changed:
        try:
            needs_gost_forwarding = tunnel.type in ["tcp", "udp", "ws", "grpc", "tcpmux"] and tunnel.core == "xray"
            needs_rathole_server = tunnel.core == "rathole"
            needs_backhaul_server = tunnel.core == "backhaul"
            needs_chisel_server = tunnel.core == "chisel"
            needs_frp_server = tunnel.core == "frp"
            needs_node_apply = tunnel.core in {"rathole", "backhaul", "chisel", "frp"}
            
            if needs_gost_forwarding:
                listen_port = tunnel.spec.get("listen_port")
                forward_to = tunnel.spec.get("forward_to")
                
                if not forward_to:
                    from app.utils import format_address_port
                    remote_ip = tunnel.spec.get("remote_ip", "127.0.0.1")
                    remote_port = tunnel.spec.get("remote_port", 8080)
                    forward_to = format_address_port(remote_ip, remote_port)
                
                panel_port = listen_port or tunnel.spec.get("remote_port")
                use_ipv6 = tunnel.spec.get("use_ipv6", False)
                
                if panel_port and forward_to and hasattr(request.app.state, 'gost_forwarder'):
                    try:
                        request.app.state.gost_forwarder.stop_forward(tunnel.id)
                        time.sleep(0.5)
                        logger.info(f"Restarting gost forwarding for tunnel {tunnel.id}: {tunnel.type}://:{panel_port} -> {forward_to}, use_ipv6={use_ipv6}")
                        request.app.state.gost_forwarder.start_forward(
                            tunnel_id=tunnel.id,
                            local_port=int(panel_port),
                            forward_to=forward_to,
                            tunnel_type=tunnel.type,
                            use_ipv6=bool(use_ipv6)
                        )
                        tunnel.status = "active"
                        tunnel.error_message = None
                        logger.info(f"Successfully restarted gost forwarding for tunnel {tunnel.id}")
                    except Exception as e:
                        error_msg = str(e)
                        logger.error(f"Failed to restart gost forwarding for tunnel {tunnel.id}: {error_msg}", exc_info=True)
                        tunnel.status = "error"
                        tunnel.error_message = f"Gost forwarding error: {error_msg}"
                else:
                    if not forward_to:
                        tunnel.status = "error"
                        tunnel.error_message = "forward_to is required for gost tunnels"
            
            elif needs_rathole_server:
                if hasattr(request.app.state, 'rathole_server_manager'):
                    remote_addr = tunnel.spec.get("remote_addr")
                    token = tunnel.spec.get("token")
                    proxy_port = tunnel.spec.get("remote_port") or tunnel.spec.get("listen_port")
                    
                    if remote_addr and token and proxy_port:
                        try:
                            request.app.state.rathole_server_manager.stop_server(tunnel.id)
                            request.app.state.rathole_server_manager.start_server(
                                tunnel_id=tunnel.id,
                                remote_addr=remote_addr,
                                token=token,
                                proxy_port=int(proxy_port)
                            )
                            tunnel.status = "active"
                            tunnel.error_message = None
                        except Exception as e:
                            logger.error(f"Failed to restart Rathole server: {e}")
                            tunnel.status = "error"
                            tunnel.error_message = f"Rathole server error: {str(e)}"
            elif needs_backhaul_server:
                manager = getattr(request.app.state, "backhaul_manager", None)
                if manager:
                    try:
                        manager.stop_server(tunnel.id)
                    except Exception:
                        pass
                    try:
                        manager.start_server(tunnel.id, tunnel.spec or {})
                        time.sleep(1.0)
                        if not manager.is_running(tunnel.id):
                            raise RuntimeError("Backhaul process not running")
                        tunnel.status = "active"
                        tunnel.error_message = None
                    except Exception as exc:
                        logger.error("Failed to restart Backhaul server for tunnel %s: %s", tunnel.id, exc, exc_info=True)
                        tunnel.status = "error"
                        tunnel.error_message = f"Backhaul server error: {exc}"
            elif needs_chisel_server:
                if hasattr(request.app.state, 'chisel_server_manager'):
                    server_port = tunnel.spec.get("control_port") or (int(tunnel.spec.get("listen_port", 0)) + 10000)
                    auth = tunnel.spec.get("auth") or tunnel.spec.get("token")
                    fingerprint = tunnel.spec.get("fingerprint")
                    use_ipv6 = tunnel.spec.get("use_ipv6", False)
                    
                    if server_port and auth and fingerprint:
                        try:
                            request.app.state.chisel_server_manager.stop_server(tunnel.id)
                            request.app.state.chisel_server_manager.start_server(
                                tunnel_id=tunnel.id,
                                server_port=int(server_port),
                                auth=auth,
                                fingerprint=fingerprint,
                                use_ipv6=bool(use_ipv6)
                            )
                            tunnel.status = "active"
                            tunnel.error_message = None
                        except Exception as e:
                            logger.error(f"Failed to restart Chisel server: {e}")
                            tunnel.status = "error"
                            tunnel.error_message = f"Chisel server error: {str(e)}"
            elif needs_frp_server:
                if hasattr(request.app.state, 'frp_server_manager'):
                    bind_port = tunnel.spec.get("bind_port", 7000)
                    token = tunnel.spec.get("token")
                    
                    if bind_port:
                        try:
                            request.app.state.frp_server_manager.stop_server(tunnel.id)
                            request.app.state.frp_server_manager.start_server(
                                tunnel_id=tunnel.id,
                                bind_port=int(bind_port),
                                token=token
                            )
                            time.sleep(1.0)
                            if not request.app.state.frp_server_manager.is_running(tunnel.id):
                                raise RuntimeError("FRP server process not running")
                            tunnel.status = "active"
                            tunnel.error_message = None
                        except Exception as e:
                            logger.error(f"Failed to restart FRP server: {e}")
                            tunnel.status = "error"
                            tunnel.error_message = f"FRP server error: {str(e)}"
            
            if needs_node_apply and tunnel.node_id:
                result = await db.execute(select(Node).where(Node.id == tunnel.node_id))
                node = result.scalar_one_or_none()
                if node:
                    client = Hysteria2Client()
                    try:
                        # Prepare spec for node (recalculate FRP server_addr if needed)
                        spec_for_node = tunnel.spec.copy() if tunnel.spec else {}
                        if tunnel.core == "frp":
                            spec_for_node = prepare_frp_spec_for_node(spec_for_node, node, request)
                        
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
                        
                        if response.get("status") == "success":
                            tunnel.status = "active"
                            tunnel.error_message = None
                        else:
                            tunnel.status = "error"
                            tunnel.error_message = f"Node error: {response.get('message', 'Unknown error')}"
                            if needs_backhaul_server and hasattr(request.app.state, "backhaul_manager"):
                                try:
                                    request.app.state.backhaul_manager.stop_server(tunnel.id)
                                except Exception:
                                    pass
                    except Exception as e:
                        logger.error(f"Failed to re-apply tunnel to node: {e}")
                        tunnel.status = "error"
                        tunnel.error_message = f"Node error: {str(e)}"
                        if needs_backhaul_server and hasattr(request.app.state, "backhaul_manager"):
                            try:
                                request.app.state.backhaul_manager.stop_server(tunnel.id)
                            except Exception:
                                pass
            
            await db.commit()
            await db.refresh(tunnel)
        except Exception as e:
            logger.error(f"Failed to re-apply tunnel: {e}", exc_info=True)
            tunnel.status = "error"
            tunnel.error_message = f"Re-apply error: {str(e)}"
            await db.commit()
            await db.refresh(tunnel)
    
    return tunnel


@router.post("/{tunnel_id}/apply")
async def apply_tunnel(tunnel_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Apply tunnel configuration to node"""
    result = await db.execute(select(Tunnel).where(Tunnel.id == tunnel_id))
    tunnel = result.scalar_one_or_none()
    if not tunnel:
        raise HTTPException(status_code=404, detail="Tunnel not found")
    
    result = await db.execute(select(Node).where(Node.id == tunnel.node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    
    client = Hysteria2Client()
    try:
        if not node.node_metadata.get("api_address"):
            node.node_metadata["api_address"] = f"http://{node.fingerprint}:8888"
            await db.commit()
        
        # Prepare spec for node (recalculate FRP server_addr if needed)
        spec_for_node = tunnel.spec.copy() if tunnel.spec else {}
        if tunnel.core == "frp":
            spec_for_node = prepare_frp_spec_for_node(spec_for_node, node, request)
        
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
        
        if response.get("status") == "success":
            tunnel.status = "active"
            await db.commit()
            return {"status": "applied", "message": "Tunnel applied successfully"}
        else:
            error_msg = response.get("message", "Failed to apply tunnel")
            tunnel.status = "error"
            await db.commit()
            raise HTTPException(status_code=500, detail=error_msg)
    except HTTPException:
        raise
    except Exception as e:
        tunnel.status = "error"
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Failed to apply tunnel: {str(e)}")


@router.delete("/{tunnel_id}")
async def delete_tunnel(tunnel_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Delete a tunnel"""
    result = await db.execute(select(Tunnel).where(Tunnel.id == tunnel_id))
    tunnel = result.scalar_one_or_none()
    if not tunnel:
        raise HTTPException(status_code=404, detail="Tunnel not found")
    
    needs_gost_forwarding = tunnel.type in ["tcp", "udp", "ws", "grpc"] and tunnel.core == "xray"
    needs_rathole_server = tunnel.core == "rathole"
    needs_backhaul_server = tunnel.core == "backhaul"
    needs_chisel_server = tunnel.core == "chisel"
    needs_frp_server = tunnel.core == "frp"
    
    if needs_gost_forwarding:
        if hasattr(request.app.state, 'gost_forwarder'):
            try:
                request.app.state.gost_forwarder.stop_forward(tunnel.id)
            except Exception as e:
                import logging
                logging.error(f"Failed to stop gost forwarding: {e}")
    
    elif needs_rathole_server:
        if hasattr(request.app.state, 'rathole_server_manager'):
            try:
                request.app.state.rathole_server_manager.stop_server(tunnel.id)
            except Exception as e:
                import logging
                logging.error(f"Failed to stop Rathole server: {e}")
    elif needs_backhaul_server:
        if hasattr(request.app.state, "backhaul_manager"):
            try:
                request.app.state.backhaul_manager.stop_server(tunnel.id)
            except Exception as e:
                import logging
                logging.error(f"Failed to stop Backhaul server: {e}")
    elif needs_chisel_server:
        if hasattr(request.app.state, 'chisel_server_manager'):
            try:
                request.app.state.chisel_server_manager.stop_server(tunnel.id)
            except Exception as e:
                import logging
                logging.error(f"Failed to stop Chisel server: {e}")
    elif needs_frp_server:
        if hasattr(request.app.state, 'frp_server_manager'):
            try:
                request.app.state.frp_server_manager.stop_server(tunnel.id)
            except Exception as e:
                import logging
                logging.error(f"Failed to stop FRP server: {e}")
    
    if tunnel.status == "active":
        result = await db.execute(select(Node).where(Node.id == tunnel.node_id))
        node = result.scalar_one_or_none()
        if node:
            client = Hysteria2Client()
            try:
                await client.send_to_node(
                    node_id=node.id,
                    endpoint="/api/agent/tunnels/remove",
                    data={"tunnel_id": tunnel.id}
                )
            except:
                pass
    
    await db.delete(tunnel)
    await db.commit()
    return {"status": "deleted"}


