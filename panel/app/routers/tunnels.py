"""Tunnels API endpoints"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from datetime import datetime
from pydantic import BaseModel

from app.database import get_db
from app.models import Tunnel, Node
from app.hysteria2_client import Hysteria2Client


router = APIRouter()


class TunnelCreate(BaseModel):
    name: str
    core: str
    type: str
    node_id: str
    spec: dict
    quota_mb: float = 0
    expires_at: datetime | None = None


class TunnelUpdate(BaseModel):
    name: str | None = None
    spec: dict | None = None
    quota_mb: float | None = None
    expires_at: datetime | None = None


class TunnelResponse(BaseModel):
    id: str
    name: str
    core: str
    type: str
    node_id: str
    spec: dict
    quota_mb: float
    used_mb: float
    expires_at: datetime | None
    status: str
    revision: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


@router.post("", response_model=TunnelResponse)
async def create_tunnel(tunnel: TunnelCreate, request: Request, db: AsyncSession = Depends(get_db)):
    """Create a new tunnel and auto-apply it"""
    from app.hysteria2_client import Hysteria2Client
    
    # Verify node exists
    result = await db.execute(select(Node).where(Node.id == tunnel.node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    
    # Create tunnel
    db_tunnel = Tunnel(
        name=tunnel.name,
        core=tunnel.core,
        type=tunnel.type,
        node_id=tunnel.node_id,
        spec=tunnel.spec,
        quota_mb=tunnel.quota_mb,
        expires_at=tunnel.expires_at,
        status="pending"
    )
    db.add(db_tunnel)
    await db.commit()
    await db.refresh(db_tunnel)
    
    # Auto-apply tunnel immediately
    try:
        client = Hysteria2Client()
        # Update node metadata with API address if not set
        if not node.node_metadata.get("api_address"):
            node.node_metadata["api_address"] = f"http://{node.node_metadata.get('ip_address', node.fingerprint)}:{node.node_metadata.get('api_port', 8888)}"
            await db.commit()
        
        response = await client.send_to_node(
            node_id=node.id,
            endpoint="/api/agent/tunnels/apply",
            data={
                "tunnel_id": db_tunnel.id,
                "core": db_tunnel.core,
                "type": db_tunnel.type,
                "spec": db_tunnel.spec
            }
        )
        
        if response.get("status") == "success":
            db_tunnel.status = "active"
            
            # Start port forwarding on panel
            remote_port = db_tunnel.spec.get("remote_port") or db_tunnel.spec.get("listen_port")
            if remote_port and hasattr(request.app.state, 'port_forwarder'):
                node_address = node.node_metadata.get("ip_address") if node.node_metadata else None
                if node_address:
                    try:
                        await request.app.state.port_forwarder.start_forward(
                            local_port=int(remote_port),
                            node_address=node_address,
                            remote_port=int(remote_port)
                        )
                    except Exception as e:
                        # Log but don't fail tunnel creation
                        import logging
                        logging.error(f"Failed to start port forwarding: {e}")
        else:
            db_tunnel.status = "error"
        await db.commit()
        await db.refresh(db_tunnel)
    except Exception as e:
        # Don't fail tunnel creation if apply fails, just mark as error
        db_tunnel.status = "error"
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
    db: AsyncSession = Depends(get_db)
):
    """Update a tunnel"""
    result = await db.execute(select(Tunnel).where(Tunnel.id == tunnel_id))
    tunnel = result.scalar_one_or_none()
    if not tunnel:
        raise HTTPException(status_code=404, detail="Tunnel not found")
    
    # Update fields
    if tunnel_update.name is not None:
        tunnel.name = tunnel_update.name
    if tunnel_update.spec is not None:
        tunnel.spec = tunnel_update.spec
    if tunnel_update.quota_mb is not None:
        tunnel.quota_mb = tunnel_update.quota_mb
    if tunnel_update.expires_at is not None:
        tunnel.expires_at = tunnel_update.expires_at
    
    tunnel.revision += 1
    tunnel.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(tunnel)
    return tunnel


@router.post("/{tunnel_id}/apply")
async def apply_tunnel(tunnel_id: str, db: AsyncSession = Depends(get_db)):
    """Apply tunnel configuration to node"""
    result = await db.execute(select(Tunnel).where(Tunnel.id == tunnel_id))
    tunnel = result.scalar_one_or_none()
    if not tunnel:
        raise HTTPException(status_code=404, detail="Tunnel not found")
    
    # Get node
    result = await db.execute(select(Node).where(Node.id == tunnel.node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    
    # Send to node via HTTPS
    client = Hysteria2Client()
    try:
        # Update node metadata with API address if not set
        if not node.node_metadata.get("api_address"):
            node.node_metadata["api_address"] = f"http://{node.fingerprint}:8888"  # Fallback
            await db.commit()
        
        response = await client.send_to_node(
            node_id=node.id,
            endpoint="/api/agent/tunnels/apply",
            data={
                "tunnel_id": tunnel.id,
                "core": tunnel.core,
                "type": tunnel.type,
                "spec": tunnel.spec
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
    
    # Stop port forwarding on panel
    remote_port = tunnel.spec.get("remote_port") or tunnel.spec.get("listen_port")
    if remote_port and hasattr(request.app.state, 'port_forwarder'):
        try:
            await request.app.state.port_forwarder.stop_forward(int(remote_port))
        except Exception as e:
            import logging
            logging.error(f"Failed to stop port forwarding: {e}")
    
    # Remove from node if active
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
                pass  # Continue deletion even if node is unreachable
    
    await db.delete(tunnel)
    await db.commit()
    return {"status": "deleted"}

