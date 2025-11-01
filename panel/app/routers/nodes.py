"""Nodes API endpoints"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from datetime import datetime
from pydantic import BaseModel

from app.database import get_db
from app.models import Node


router = APIRouter()


class NodeCreate(BaseModel):
    name: str
    fingerprint: str
    metadata: dict = {}  # Keep as metadata in API, maps to node_metadata in model


class NodeResponse(BaseModel):
    id: str
    name: str
    fingerprint: str
    status: str
    registered_at: datetime
    last_seen: datetime
    metadata: dict  # Maps to node_metadata in model
    
    class Config:
        from_attributes = True
    


@router.post("", response_model=NodeResponse)
async def create_node(node: NodeCreate, db: AsyncSession = Depends(get_db)):
    """Register a new node"""
    # Check if fingerprint exists
    result = await db.execute(select(Node).where(Node.fingerprint == node.fingerprint))
    existing = result.scalar_one_or_none()
    
    if existing:
        # Update last_seen and metadata
        existing.last_seen = datetime.utcnow()
        existing.status = "active"
        if node.metadata:
            existing.node_metadata.update(node.metadata)
        await db.commit()
        await db.refresh(existing)
        return NodeResponse(
            id=existing.id,
            name=existing.name,
            fingerprint=existing.fingerprint,
            status=existing.status,
            registered_at=existing.registered_at,
            last_seen=existing.last_seen,
            metadata=existing.node_metadata or {}
        )
    
    # Create new node
    db_node = Node(
        name=node.name,
        fingerprint=node.fingerprint,
        status="active",
        node_metadata=node.metadata or {}
    )
    db.add(db_node)
    await db.commit()
    await db.refresh(db_node)
    return NodeResponse(
        id=db_node.id,
        name=db_node.name,
        fingerprint=db_node.fingerprint,
        status=db_node.status,
        registered_at=db_node.registered_at,
        last_seen=db_node.last_seen,
        metadata=db_node.node_metadata or {}
    )


@router.get("", response_model=List[NodeResponse])
async def list_nodes(db: AsyncSession = Depends(get_db)):
    """List all nodes"""
    result = await db.execute(select(Node))
    nodes = result.scalars().all()
    return [
        NodeResponse(
            id=n.id,
            name=n.name,
            fingerprint=n.fingerprint,
            status=n.status,
            registered_at=n.registered_at,
            last_seen=n.last_seen,
            metadata=n.node_metadata or {}
        )
        for n in nodes
    ]


@router.get("/{node_id}", response_model=NodeResponse)
async def get_node(node_id: str, db: AsyncSession = Depends(get_db)):
    """Get node by ID"""
    result = await db.execute(select(Node).where(Node.id == node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return NodeResponse(
        id=node.id,
        name=node.name,
        fingerprint=node.fingerprint,
        status=node.status,
        registered_at=node.registered_at,
        last_seen=node.last_seen,
        metadata=node.node_metadata or {}
    )


@router.delete("/{node_id}")
async def delete_node(node_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a node"""
    result = await db.execute(select(Node).where(Node.id == node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    
    await db.delete(node)
    await db.commit()
    return {"status": "deleted"}

