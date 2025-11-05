"""Database models"""
from sqlalchemy import Column, String, Integer, DateTime, Float, JSON, Boolean, Text
from sqlalchemy.dialects.sqlite import DATETIME as SQLiteDATETIME
from datetime import datetime
from app.database import Base
import uuid


def generate_uuid():
    return str(uuid.uuid4())


class Node(Base):
    __tablename__ = "nodes"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False)
    fingerprint = Column(String, unique=True, nullable=False)
    status = Column(String, default="pending")  # pending, active, offline
    registered_at = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)
    node_metadata = Column("metadata", JSON, default=dict)  # Use "metadata" as column name in DB, but node_metadata as attribute
    

class Tunnel(Base):
    __tablename__ = "tunnels"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False)
    core = Column(String, nullable=False)  # xray, rathole
    type = Column(String, nullable=False)  # tcp, udp, ws, grpc, tcpmux, rathole
    node_id = Column(String, nullable=False)
    spec = Column(JSON, nullable=False)
    quota_mb = Column(Float, default=0)
    used_mb = Column(Float, default=0)
    expires_at = Column(DateTime, nullable=True)
    status = Column(String, default="pending")  # pending, active, error, expired
    error_message = Column(Text, nullable=True)  # Store error details
    revision = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Admin(Base):
    __tablename__ = "admins"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Usage(Base):
    __tablename__ = "usage"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    tunnel_id = Column(String, nullable=False)
    node_id = Column(String, nullable=False)
    bytes_used = Column(Integer, default=0)
    timestamp = Column(DateTime, default=datetime.utcnow)

