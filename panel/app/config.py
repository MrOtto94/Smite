"""Application configuration"""
from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    panel_port: int = 8000
    panel_host: str = "0.0.0.0"
    panel_domain: str = ""
    panel_address: str = ""  # Optional full address host:port or URL for node helpers
    https_enabled: bool = False
    https_cert_path: str = "./certs/server.crt"
    https_key_path: str = "./certs/server.key"
    docs_enabled: bool = True
    
    db_type: Literal["sqlite"] = "sqlite"
    db_path: str = "./data/smite.db"
    db_host: str = "localhost"
    db_port: int = 3306
    db_name: str = "smite"
    db_user: str = "smite"
    db_password: str = "changeme"
    
    hysteria2_port: int = 4443
    hysteria2_cert_path: str = "./certs/ca.crt"
    hysteria2_key_path: str = "./certs/ca.key"
    # Separate CA cert for foreign servers
    hysteria2_server_cert_path: str = "./certs/ca-server.crt"
    hysteria2_server_key_path: str = "./certs/ca-server.key"
    
    secret_key: str = "changeme-secret-key-change-in-production"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
