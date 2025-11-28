"""Core Health and Reset API endpoints"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Dict, Any
from datetime import datetime, timedelta
from pydantic import BaseModel
import logging
import asyncio

from app.database import get_db
from app.models import Tunnel, Node, CoreResetConfig
from app.hysteria2_client import Hysteria2Client

router = APIRouter()
logger = logging.getLogger(__name__)

CORES = ["backhaul", "rathole", "chisel", "frp"]


class CoreHealthResponse(BaseModel):
    core: str
    panel_status: str
    panel_healthy: bool
    panel_error_message: str | None = None
    nodes_status: Dict[str, Dict[str, Any]]


class ResetConfigResponse(BaseModel):
    core: str
    enabled: bool
    interval_minutes: int
    last_reset: datetime | None
    next_reset: datetime | None


class ResetConfigUpdate(BaseModel):
    enabled: bool | None = None
    interval_minutes: int | None = None


@router.get("/health", response_model=List[CoreHealthResponse])
async def get_core_health(request: Request, db: AsyncSession = Depends(get_db)):
    """Get health status for all cores"""
    health_data = []
    
    for core in CORES:
        panel_status = "unknown"
        panel_healthy = False
        nodes_status = {}
        
        result = await db.execute(select(Tunnel).where(Tunnel.core == core, Tunnel.status == "active"))
        active_tunnels = result.scalars().all()
        
        try:
            if core == "backhaul":
                manager = getattr(request.app.state, "backhaul_manager", None)
                if manager:
                    active_servers = manager.get_active_servers()
                    if len(active_tunnels) > 0:
                        panel_healthy = len(active_servers) > 0
                        panel_status = "healthy" if panel_healthy else "error"
                    else:
                        panel_healthy = True  # No tunnels means healthy (nothing to check)
                        panel_status = "healthy"
                else:
                    panel_healthy = len(active_tunnels) == 0
                    panel_status = "error" if len(active_tunnels) > 0 else "healthy"
            elif core == "rathole":
                manager = getattr(request.app.state, "rathole_server_manager", None)
                if manager:
                    if len(active_tunnels) > 0:
                        tunnel_ids = {t.id for t in active_tunnels}
                        all_healthy = True
                        error_message = None
                        for tunnel_id in tunnel_ids:
                            if not manager.is_running(tunnel_id):
                                all_healthy = False
                                error_message = f"Server for tunnel {tunnel_id[:8]}... not running"
                                break
                        panel_healthy = all_healthy
                        panel_status = "healthy" if panel_healthy else "error"
                        if not panel_healthy and error_message:
                            panel_status = f"error: {error_message}"
                    else:
                        panel_healthy = True  # No tunnels means healthy (nothing to check)
                        panel_status = "healthy"
                else:
                    panel_healthy = len(active_tunnels) == 0
                    panel_status = "error" if len(active_tunnels) > 0 else "healthy"
            elif core == "chisel":
                manager = getattr(request.app.state, "chisel_server_manager", None)
                if manager:
                    active_servers = manager.get_active_servers()
                    if len(active_tunnels) > 0:
                        panel_healthy = len(active_servers) > 0
                        panel_status = "healthy" if panel_healthy else "error"
                    else:
                        panel_healthy = True  # No tunnels means healthy (nothing to check)
                        panel_status = "healthy"
                else:
                    panel_healthy = len(active_tunnels) == 0
                    panel_status = "error" if len(active_tunnels) > 0 else "healthy"
            elif core == "frp":
                manager = getattr(request.app.state, "frp_server_manager", None)
                if manager:
                    active_servers = manager.get_active_servers()
                    if len(active_tunnels) > 0:
                        panel_healthy = len(active_servers) > 0
                        panel_status = "healthy" if panel_healthy else "error"
                    else:
                        panel_healthy = True  # No tunnels means healthy (nothing to check)
                        panel_status = "healthy"
                else:
                    panel_healthy = len(active_tunnels) == 0
                    panel_status = "error" if len(active_tunnels) > 0 else "healthy"
        except Exception as e:
            logger.error(f"Error checking {core} panel health: {e}")
            panel_status = "error"
            panel_healthy = False
        
        node_ids = set(t.node_id for t in active_tunnels if t.node_id)
        
        client = Hysteria2Client()
        for node_id in node_ids:
            node_result = await db.execute(select(Node).where(Node.id == node_id))
            node = node_result.scalar_one_or_none()
            if not node:
                continue
            
            node_status = {
                "healthy": False,
                "status": "unknown",
                "error_message": None
            }
            
            try:
                response = await client.get_tunnel_status(node_id, "")
                if response and response.get("status") == "ok":
                    node_status["healthy"] = True
                    node_status["status"] = "healthy"
                else:
                    error_msg = response.get("message", "Node disconnected") if response else "Node not responding"
                    node_status["status"] = "error"
                    node_status["error_message"] = error_msg
            except Exception as e:
                logger.error(f"Error checking {core} node {node_id} health: {e}")
                node_status["status"] = "error"
                node_status["error_message"] = str(e)
            
            nodes_status[node_id] = node_status
        
        # Extract error message from panel_status if it contains error details
        panel_error_message = None
        if panel_status.startswith("error:"):
            panel_error_message = panel_status.split("error:", 1)[1].strip()
            panel_status = "error"
        
        health_data.append(CoreHealthResponse(
            core=core,
            panel_status=panel_status,
            panel_healthy=panel_healthy,
            panel_error_message=panel_error_message,
            nodes_status=nodes_status
        ))
    
    return health_data


@router.get("/reset-config", response_model=List[ResetConfigResponse])
async def get_reset_configs(db: AsyncSession = Depends(get_db)):
    """Get reset timer configuration for all cores"""
    configs = []
    
    for core in CORES:
        result = await db.execute(select(CoreResetConfig).where(CoreResetConfig.core == core))
        config = result.scalar_one_or_none()
        
        if not config:
            config = CoreResetConfig(
                core=core,
                enabled=False,
                interval_minutes=10
            )
            db.add(config)
            await db.commit()
            await db.refresh(config)
        
        configs.append(ResetConfigResponse(
            core=config.core,
            enabled=config.enabled,
            interval_minutes=config.interval_minutes,
            last_reset=config.last_reset,
            next_reset=config.next_reset
        ))
    
    return configs


@router.put("/reset-config/{core}", response_model=ResetConfigResponse)
async def update_reset_config(
    core: str,
    config_update: ResetConfigUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update reset timer configuration for a core"""
    if core not in CORES:
        raise HTTPException(status_code=400, detail=f"Invalid core: {core}")
    
    result = await db.execute(select(CoreResetConfig).where(CoreResetConfig.core == core))
    config = result.scalar_one_or_none()
    
    if not config:
        config = CoreResetConfig(core=core, enabled=False, interval_minutes=10)
        db.add(config)
    
    if config_update.enabled is not None:
        config.enabled = config_update.enabled
    
    if config_update.interval_minutes is not None:
        if config_update.interval_minutes < 1:
            raise HTTPException(status_code=400, detail="Interval must be at least 1 minute")
        config.interval_minutes = config_update.interval_minutes
    
    if config.enabled and config.interval_minutes:
        now = datetime.utcnow()
        if config.last_reset:
            # Calculate next_reset from last_reset, but ensure it's not in the past
            calculated_next = config.last_reset + timedelta(minutes=config.interval_minutes)
            if calculated_next > now:
                # If calculated time is in the future, use it
                config.next_reset = calculated_next
            else:
                # If calculated time is in the past (e.g., old last_reset), reset from now
                config.next_reset = now + timedelta(minutes=config.interval_minutes)
        else:
            # No last_reset, start timer from now
            config.next_reset = now + timedelta(minutes=config.interval_minutes)
    else:
        config.next_reset = None
    
    config.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(config)
    
    return ResetConfigResponse(
        core=config.core,
        enabled=config.enabled,
        interval_minutes=config.interval_minutes,
        last_reset=config.last_reset,
        next_reset=config.next_reset
    )


@router.post("/reset/{core}")
async def manual_reset_core(core: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Manually reset a core (restart servers and clients)"""
    if core not in CORES:
        raise HTTPException(status_code=400, detail=f"Invalid core: {core}")
    
    try:
        result = await db.execute(select(CoreResetConfig).where(CoreResetConfig.core == core))
        config = result.scalar_one_or_none()
        
        reset_time = datetime.utcnow()
        
        if not config:
            config = CoreResetConfig(core=core, enabled=False, interval_minutes=10)
            db.add(config)
        
        config.last_reset = reset_time
        if config.enabled and config.interval_minutes:
            config.next_reset = reset_time + timedelta(minutes=config.interval_minutes)
        await db.commit()
        await db.refresh(config)
        
        await _reset_core(core, request, db)
        
        return {
            "status": "success",
            "message": f"{core} reset successfully",
            "last_reset": config.last_reset.isoformat() if config.last_reset else None
        }
    except Exception as e:
        logger.error(f"Error resetting {core}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def _reset_core(core: str, app_or_request, db: AsyncSession):
    """Internal function to reset a core"""
    if hasattr(app_or_request, 'app'):
        app = app_or_request.app
    else:
        app = app_or_request
    
    result = await db.execute(select(Tunnel).where(Tunnel.core == core, Tunnel.status == "active"))
    active_tunnels = result.scalars().all()
    
    if core == "backhaul":
        manager = getattr(app.state, "backhaul_manager", None)
        if manager:
            for tunnel in active_tunnels:
                try:
                    manager.stop_server(tunnel.id)
                    await asyncio.sleep(0.5)
                    manager.start_server(tunnel.id, tunnel.spec or {})
                except Exception as e:
                    logger.error(f"Error restarting backhaul server for tunnel {tunnel.id}: {e}")
    elif core == "rathole":
        manager = getattr(app.state, "rathole_server_manager", None)
        if manager:
            for tunnel in active_tunnels:
                try:
                    remote_addr = tunnel.spec.get("remote_addr")
                    token = tunnel.spec.get("token")
                    proxy_port = tunnel.spec.get("remote_port") or tunnel.spec.get("listen_port")
                    if remote_addr and token and proxy_port:
                        manager.stop_server(tunnel.id)
                        await asyncio.sleep(0.5)
                        manager.start_server(
                            tunnel_id=tunnel.id,
                            remote_addr=remote_addr,
                            token=token,
                            proxy_port=int(proxy_port)
                        )
                except Exception as e:
                    logger.error(f"Error restarting rathole server for tunnel {tunnel.id}: {e}")
    elif core == "chisel":
        manager = getattr(app.state, "chisel_server_manager", None)
        if manager:
            for tunnel in active_tunnels:
                try:
                    listen_port = tunnel.spec.get("listen_port") or tunnel.spec.get("remote_port")
                    server_port = tunnel.spec.get("control_port")
                    if not server_port and listen_port:
                        server_port = int(listen_port) + 10000
                    elif not server_port:
                        logger.warning(f"Chisel tunnel {tunnel.id}: Missing listen_port and control_port, skipping reset")
                        continue
                    auth = tunnel.spec.get("auth")
                    fingerprint = tunnel.spec.get("fingerprint")
                    use_ipv6 = tunnel.spec.get("use_ipv6", False)
                    if server_port:
                        manager.stop_server(tunnel.id)
                        await asyncio.sleep(0.5)
                        manager.start_server(
                            tunnel_id=tunnel.id,
                            server_port=int(server_port),
                            auth=auth,
                            fingerprint=fingerprint,
                            use_ipv6=bool(use_ipv6)
                        )
                except Exception as e:
                    logger.error(f"Error restarting chisel server for tunnel {tunnel.id}: {e}")
    elif core == "frp":
        manager = getattr(app.state, "frp_server_manager", None)
        if manager:
            for tunnel in active_tunnels:
                try:
                    bind_port = tunnel.spec.get("bind_port", 7000)
                    token = tunnel.spec.get("token")
                    if bind_port:
                        manager.stop_server(tunnel.id)
                        await asyncio.sleep(0.5)
                        manager.start_server(
                            tunnel_id=tunnel.id,
                            bind_port=int(bind_port),
                            token=token
                        )
                except Exception as e:
                    logger.error(f"Error restarting FRP server for tunnel {tunnel.id}: {e}")
    
    node_ids = set(t.node_id for t in active_tunnels if t.node_id)
    client = Hysteria2Client()
    
    for node_id in node_ids:
        node_result = await db.execute(select(Node).where(Node.id == node_id))
        node = node_result.scalar_one_or_none()
        if not node:
            continue
        
        node_tunnels = [t for t in active_tunnels if t.node_id == node_id]
        
        for tunnel in node_tunnels:
            try:
                spec_for_node = tunnel.spec.copy()
                
                if core == "backhaul":
                    pass
                elif core == "rathole":
                    remote_addr = tunnel.spec.get("remote_addr", "").split(":")[0] if ":" in tunnel.spec.get("remote_addr", "") else tunnel.spec.get("remote_addr", "")
                    remote_port = tunnel.spec.get("remote_port") or tunnel.spec.get("listen_port")
                    token = tunnel.spec.get("token")
                    local_addr = tunnel.spec.get("local_addr", "127.0.0.1")
                    local_port = tunnel.spec.get("local_port")
                    
                    spec_for_node = {
                        "remote_addr": f"{remote_addr}:{remote_port}",
                        "token": token,
                        "local_addr": local_addr,
                        "local_port": local_port
                    }
                elif core == "chisel":
                    listen_port = tunnel.spec.get("listen_port") or tunnel.spec.get("remote_port") or tunnel.spec.get("server_port")
                    use_ipv6 = tunnel.spec.get("use_ipv6", False)
                    if listen_port:
                        server_control_port = tunnel.spec.get("control_port")
                        if server_control_port:
                            server_control_port = int(server_control_port)
                        else:
                            server_control_port = int(listen_port) + 10000
                        reverse_port = int(listen_port)
                        
                        panel_host = tunnel.spec.get("panel_host")
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
                            import os
                            panel_public_ip = os.getenv("PANEL_PUBLIC_IP") or os.getenv("PANEL_IP")
                            if panel_public_ip and panel_public_ip not in ["localhost", "127.0.0.1", "::1", "0.0.0.0", ""]:
                                panel_host = panel_public_ip
                            else:
                                panel_host = "127.0.0.1"
                        
                        from app.utils import is_valid_ipv6_address
                        if is_valid_ipv6_address(panel_host):
                            server_url = f"http://[{panel_host}]:{server_control_port}"
                        else:
                            server_url = f"http://{panel_host}:{server_control_port}"
                        
                        auth = tunnel.spec.get("auth")
                        fingerprint = tunnel.spec.get("fingerprint")
                        local_addr = tunnel.spec.get("local_addr", "127.0.0.1")
                        local_port = tunnel.spec.get("local_port")
                        reverse_spec = tunnel.spec.get("reverse_spec", f"R:{reverse_port}:{local_addr}:{local_port}")
                        
                        spec_for_node = {
                            "server_url": server_url,
                            "reverse_port": reverse_port,
                            "remote_port": reverse_port,  # Also include as remote_port for compatibility
                            "reverse_spec": reverse_spec,
                            "auth": auth,
                            "fingerprint": fingerprint,
                            "use_ipv6": use_ipv6,
                            "local_addr": local_addr
                        }
                    else:
                        logger.warning(f"Chisel tunnel {tunnel.id}: Missing listen_port, skipping reset")
                        continue
                elif core == "frp":
                    from app.routers.tunnels import prepare_frp_spec_for_node
                    from fastapi import Request
                    spec_for_node = tunnel.spec.copy()
                    panel_address = node.node_metadata.get("panel_address", "")
                    if panel_address:
                        if "://" in panel_address:
                            panel_address = panel_address.split("://", 1)[1]
                        if ":" in panel_address:
                            panel_host = panel_address.split(":")[0]
                        else:
                            panel_host = panel_address
                        
                        from app.utils import is_valid_ipv6_address
                        if is_valid_ipv6_address(panel_host):
                            server_addr = f"[{panel_host}]"
                        else:
                            server_addr = panel_host
                        
                        bind_port = spec_for_node.get("bind_port", 7000)
                        spec_for_node["server_addr"] = server_addr
                        spec_for_node["server_port"] = int(bind_port)
                    else:
                        import os
                        panel_public_ip = os.getenv("PANEL_PUBLIC_IP") or os.getenv("PANEL_IP")
                        if panel_public_ip and panel_public_ip not in ["localhost", "127.0.0.1", "::1", "0.0.0.0", ""]:
                            spec_for_node["server_addr"] = panel_public_ip
                        else:
                            logger.error(f"FRP tunnel {tunnel.id}: Cannot determine panel address for reset")
                            continue
                
                response = await client.apply_tunnel(
                    node_id,
                    {
                        "tunnel_id": tunnel.id,
                        "core": core,
                        "type": tunnel.type,
                        "spec": spec_for_node
                    }
                )
                
                if response.get("status") == "error":
                    error_msg = response.get("message", "Unknown error")
                    logger.error(f"Error restarting {core} client for tunnel {tunnel.id} on node {node_id}: {error_msg}")
                    raise Exception(f"Failed to apply tunnel: {error_msg}")
                
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Error restarting {core} client for tunnel {tunnel.id} on node {node_id}: {e}")
                raise

