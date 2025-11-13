"""Core adapters for different tunnel types"""
from typing import Protocol, Dict, Any, Optional, List
import subprocess
import os
import psutil
import time
from pathlib import Path
import shutil
from .iptables_tracker import (
    add_tracking_rule,
    remove_tracking_rule,
    get_traffic_bytes,
    parse_address_port,
    add_tracking_rule_for_remote,
    remove_tracking_rule_for_remote,
    get_traffic_bytes_for_remote
)


class CoreAdapter(Protocol):
    """Protocol for core adapters"""
    name: str
    
    def apply(self, tunnel_id: str, spec: Dict[str, Any]) -> None:
        """Apply tunnel configuration"""
        ...
    
    def remove(self, tunnel_id: str) -> None:
        """Remove tunnel"""
        ...
    
    def status(self, tunnel_id: str) -> Dict[str, Any]:
        """Get tunnel status"""
        ...
    
    def get_usage_mb(self, tunnel_id: str) -> float:
        """Get usage in MB"""
        ...


class RatholeAdapter:
    """Rathole reverse tunnel adapter"""
    name = "rathole"
    
    def __init__(self):
        self.config_dir = Path("/etc/smite-node/rathole")
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.processes = {}
        self.usage_tracking = {}
        self.tunnel_ports = {}  # Track ports for iptables tracking
        self.iptables_baseline = {}  # Track baseline iptables counter when rule is added
    
    def apply(self, tunnel_id: str, spec: Dict[str, Any]):
        """Apply Rathole tunnel"""
        remote_addr = spec.get('remote_addr', '').strip()
        token = spec.get('token', '').strip()
        local_addr = spec.get('local_addr', '127.0.0.1:8080')
        
        if not remote_addr:
            raise ValueError("Rathole requires 'remote_addr' (panel address) in spec")
        if not token:
            raise ValueError("Rathole requires 'token' in spec")
        
        config = f"""[client]
remote_addr = "{remote_addr}"
default_token = "{token}"

[client.services.{tunnel_id}]
local_addr = "{local_addr}"
"""
        
        config_path = self.config_dir / f"{tunnel_id}.toml"
        with open(config_path, "w") as f:
            f.write(config)
        
        # Parse local_addr to get port for iptables tracking
        host, port, is_ipv6 = parse_address_port(local_addr)
        if port:
            self.tunnel_ports[tunnel_id] = (port, is_ipv6)
            # Add iptables tracking rule (only counts, doesn't block)
            try:
                add_tracking_rule(tunnel_id, port, is_ipv6)
                # Get baseline counter (should be 0 or very small right after rule creation)
                import time
                time.sleep(0.1)  # Small delay to ensure rule is active
                baseline_bytes = get_traffic_bytes(tunnel_id, port, is_ipv6)
                self.iptables_baseline[tunnel_id] = baseline_bytes
                import logging
                logging.getLogger(__name__).info(f"Added iptables tracking for tunnel {tunnel_id} on port {port} (IPv6={is_ipv6}), baseline: {baseline_bytes} bytes")
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Failed to add iptables tracking for tunnel {tunnel_id}: {e}", exc_info=True)
        
        try:
            proc = subprocess.Popen(
                ["/usr/local/bin/rathole", "-c", str(config_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            self.processes[tunnel_id] = proc
            time.sleep(0.5)
            if proc.poll() is not None:
                stderr = proc.stderr.read().decode() if proc.stderr else "Unknown error"
                raise RuntimeError(f"rathole failed to start: {stderr}")
        except FileNotFoundError:
            proc = subprocess.Popen(
                ["rathole", "-c", str(config_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            self.processes[tunnel_id] = proc
            time.sleep(0.5)
            if proc.poll() is not None:
                stderr = proc.stderr.read().decode() if proc.stderr else "Unknown error"
                raise RuntimeError(f"rathole failed to start: {stderr}")
    
    def remove(self, tunnel_id: str):
        """Remove Rathole tunnel"""
        config_path = self.config_dir / f"{tunnel_id}.toml"
        
        # Remove iptables tracking rule
        if tunnel_id in self.tunnel_ports:
            port, is_ipv6 = self.tunnel_ports[tunnel_id]
            try:
                remove_tracking_rule(tunnel_id, port, is_ipv6)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Failed to remove iptables tracking for tunnel {tunnel_id}: {e}")
            del self.tunnel_ports[tunnel_id]
            # Clean up baseline
            if tunnel_id in self.iptables_baseline:
                del self.iptables_baseline[tunnel_id]
        
        if tunnel_id in self.processes:
            proc = self.processes[tunnel_id]
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            except:
                pass
            del self.processes[tunnel_id]
        
        try:
            subprocess.run(["pkill", "-f", f"rathole.*{tunnel_id}"], check=False, timeout=3)
        except:
            pass
            
        if config_path.exists():
            config_path.unlink()
    
    def status(self, tunnel_id: str) -> Dict[str, Any]:
        """Get status"""
        config_path = self.config_dir / f"{tunnel_id}.toml"
        is_running = False
        
        if tunnel_id in self.processes:
            proc = self.processes[tunnel_id]
            is_running = proc.poll() is None
        
        return {
            "active": config_path.exists() and is_running,
            "type": "rathole",
            "config_exists": config_path.exists(),
            "process_running": is_running
        }
    
    def get_usage_mb(self, tunnel_id: str) -> float:
        """Get usage in MB - tracks cumulative network I/O from process and iptables"""
        import logging
        logger = logging.getLogger(__name__)
        total_bytes = 0.0
        
        # Method 1: Track from iptables counters (most accurate, works even with external proxies)
        if tunnel_id in self.tunnel_ports:
            port, is_ipv6 = self.tunnel_ports[tunnel_id]
            try:
                current_iptables_bytes = get_traffic_bytes(tunnel_id, port, is_ipv6)
                # Get baseline (counter when rule was first added)
                baseline = self.iptables_baseline.get(tunnel_id, 0)
                # Calculate actual usage as difference from baseline
                iptables_bytes = max(0, current_iptables_bytes - baseline)
                if iptables_bytes > 0:
                    logger.debug(f"Tunnel {tunnel_id}: iptables current={current_iptables_bytes}, baseline={baseline}, usage={iptables_bytes} bytes")
                total_bytes = max(total_bytes, iptables_bytes)
            except Exception as e:
                logger.warning(f"Failed to get iptables bytes for tunnel {tunnel_id}: {e}")
        
        # Method 2: Track from process I/O (fallback if iptables not available)
        if tunnel_id in self.processes:
            proc = self.processes[tunnel_id]
            try:
                proc_info = psutil.Process(proc.pid)
                try:
                    io_counters = proc_info.io_counters()
                    process_bytes = io_counters.read_bytes + io_counters.write_bytes
                    total_bytes = max(total_bytes, process_bytes)
                except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError, OSError):
                    pass
            except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError, OSError):
                pass
        
        if tunnel_id not in self.usage_tracking:
            self.usage_tracking[tunnel_id] = 0.0
        
        if total_bytes > 0:
            current_mb = total_bytes / (1024 * 1024)
            # Only update if we got a higher value (iptables counters are cumulative)
            if current_mb > self.usage_tracking[tunnel_id]:
                self.usage_tracking[tunnel_id] = current_mb
        
        return self.usage_tracking.get(tunnel_id, 0.0)


class BackhaulAdapter:
    """Backhaul reverse tunnel adapter"""
    name = "backhaul"

    CLIENT_OPTION_KEYS = [
        "connection_pool",
        "retry_interval",
        "nodelay",
        "keepalive_period",
        "log_level",
        "pprof",
        "mux_session",
        "mux_version",
        "mux_framesize",
        "mux_recievebuffer",
        "mux_streambuffer",
        "sniffer",
        "web_port",
        "sniffer_log",
        "dial_timeout",
        "aggressive_pool",
        "edge_ip",
        "skip_optz",
        "mss",
        "so_rcvbuf",
        "so_sndbuf",
        "accept_udp",
    ]

    def __init__(
        self,
        config_dir: Optional[Path] = None,
        binary_path: Optional[Path] = None,
    ):
        resolved_config = config_dir or Path(
            os.environ.get("SMITE_BACKHAUL_CLIENT_DIR", "/etc/smite-node/backhaul")
        )
        self.config_dir = Path(resolved_config)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.processes: Dict[str, subprocess.Popen] = {}
        self.usage_tracking: Dict[str, float] = {}
        self.log_handles: Dict[str, Any] = {}
        self.tunnel_ports: Dict[str, tuple] = {}  # Track ports for iptables tracking
        self.iptables_baseline: Dict[str, int] = {}  # Track baseline iptables counter when rule is added
        default_binary = binary_path or Path(
            os.environ.get("BACKHAUL_CLIENT_BINARY", "/usr/local/bin/backhaul")
        )
        self.binary_candidates = [
            Path(default_binary),
            Path("backhaul"),
        ]

    def apply(self, tunnel_id: str, spec: Dict[str, Any]):
        remote_addr = spec.get("remote_addr") or spec.get("control_addr") or spec.get("bind_addr")
        if not remote_addr:
            raise ValueError("Backhaul requires 'remote_addr' in spec")

        transport = (spec.get("transport") or spec.get("type") or "tcp").lower()
        if transport not in {"tcp", "udp", "ws", "wsmux", "tcpmux"}:
            raise ValueError(f"Unsupported Backhaul transport '{transport}'")
        client_options = dict(spec.get("client_options") or {})

        config_dict: Dict[str, Any] = {
            "remote_addr": remote_addr,
            "transport": transport,
        }

        token = spec.get("token") or client_options.get("token")
        if token:
            config_dict["token"] = token

        for key in self.CLIENT_OPTION_KEYS:
            value = client_options.get(key)
            if value is None or value == "":
                value = spec.get(key)
            if value is None or value == "":
                continue
            config_dict[key] = value

        if "connection_pool" not in config_dict:
            config_dict["connection_pool"] = 4
        if "retry_interval" not in config_dict:
            config_dict["retry_interval"] = 3
        if "dial_timeout" not in config_dict:
            config_dict["dial_timeout"] = 10

        if spec.get("accept_udp") and transport in {"tcp", "tcpmux"}:
            config_dict["accept_udp"] = True

        config_path = self.config_dir / f"{tunnel_id}.toml"
        config_path.write_text(self._render_toml({"client": config_dict}), encoding="utf-8")

        binary_path = self._resolve_binary_path()

        log_path = self.config_dir / f"backhaul_{tunnel_id}.log"
        log_fh = log_path.open("w", buffering=1)
        log_fh.write(f"Starting Backhaul client for tunnel {tunnel_id}\n")
        log_fh.write(self._render_toml({"client": config_dict}))
        log_fh.flush()

        try:
            proc = subprocess.Popen(
                [str(binary_path), "-c", str(config_path)],
                stdout=log_fh,
                stderr=subprocess.STDOUT,
            )
        except Exception:
            log_fh.close()
            raise

        time.sleep(0.5)
        if proc.poll() is not None:
            error_output = ""
            try:
                error_output = log_path.read_text(encoding="utf-8")[-1000:]
            except Exception:
                pass
            log_fh.close()
            raise RuntimeError(f"backhaul failed to start: {error_output}")

        self.processes[tunnel_id] = proc
        self.log_handles[tunnel_id] = log_fh
        self.usage_tracking.setdefault(tunnel_id, 0.0)
        
        # Store remote address for iptables tracking (Backhaul is client, track by remote address)
        if remote_addr:
            # Parse remote_addr to extract host and port
            host, port, is_ipv6 = parse_address_port(remote_addr)
            if host and port:
                self.tunnel_ports[tunnel_id] = (host, port, is_ipv6, True)  # True = track by remote address
                # Add iptables tracking rule for outbound connections to remote address
                try:
                    add_tracking_rule_for_remote(tunnel_id, host, port, is_ipv6)
                    # Get baseline counter (should be 0 or very small right after rule creation)
                    import time
                    time.sleep(0.1)  # Small delay to ensure rule is active
                    baseline_bytes = get_traffic_bytes_for_remote(tunnel_id, host, port, is_ipv6)
                    self.iptables_baseline[tunnel_id] = baseline_bytes
                    import logging
                    logging.getLogger(__name__).info(f"Added iptables tracking for Backhaul tunnel {tunnel_id} to {host}:{port} (IPv6={is_ipv6}), baseline: {baseline_bytes} bytes")
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).error(f"Failed to add iptables tracking for Backhaul tunnel {tunnel_id}: {e}", exc_info=True)

    def remove(self, tunnel_id: str):
        config_path = self.config_dir / f"{tunnel_id}.toml"
        
        # Remove iptables tracking rule for remote address
        if tunnel_id in self.tunnel_ports:
            port_info = self.tunnel_ports[tunnel_id]
            if len(port_info) == 4 and port_info[3]:  # Track by remote address
                host, port, is_ipv6, _ = port_info
                try:
                    remove_tracking_rule_for_remote(tunnel_id, host, port, is_ipv6)
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(f"Failed to remove iptables tracking for tunnel {tunnel_id}: {e}")
            del self.tunnel_ports[tunnel_id]
            # Clean up baseline
            if tunnel_id in self.iptables_baseline:
                del self.iptables_baseline[tunnel_id]
        
        if tunnel_id in self.processes:
            proc = self.processes[tunnel_id]
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            except Exception:
                pass
            del self.processes[tunnel_id]
        if tunnel_id in self.log_handles:
            try:
                self.log_handles[tunnel_id].close()
            except Exception:
                pass
            del self.log_handles[tunnel_id]

        if config_path.exists():
            try:
                config_path.unlink()
            except Exception:
                pass

    def status(self, tunnel_id: str) -> Dict[str, Any]:
        config_path = self.config_dir / f"{tunnel_id}.toml"
        proc = self.processes.get(tunnel_id)
        is_running = proc is not None and proc.poll() is None
        return {
            "active": config_path.exists() and is_running,
            "type": "backhaul",
            "config_exists": config_path.exists(),
            "process_running": is_running,
        }

    def get_usage_mb(self, tunnel_id: str) -> float:
        """Get usage in MB - tracks from process I/O and iptables (by remote address)"""
        import logging
        logger = logging.getLogger(__name__)
        total_bytes = 0.0
        
        # Method 1: Track from iptables counters (by remote address)
        if tunnel_id in self.tunnel_ports:
            port_info = self.tunnel_ports[tunnel_id]
            if len(port_info) == 4 and port_info[3]:  # Track by remote address
                host, port, is_ipv6, _ = port_info
                try:
                    current_iptables_bytes = get_traffic_bytes_for_remote(tunnel_id, host, port, is_ipv6)
                    # Get baseline (counter when rule was first added)
                    baseline = self.iptables_baseline.get(tunnel_id, 0)
                    # Calculate actual usage as difference from baseline
                    iptables_bytes = max(0, current_iptables_bytes - baseline)
                    if iptables_bytes > 0:
                        logger.debug(f"Backhaul tunnel {tunnel_id}: iptables current={current_iptables_bytes}, baseline={baseline}, usage={iptables_bytes} bytes")
                    total_bytes = max(total_bytes, iptables_bytes)
                except Exception as e:
                    logger.warning(f"Failed to get iptables bytes for Backhaul tunnel {tunnel_id}: {e}")
        
        # Method 2: Track from process I/O (fallback)
        if tunnel_id in self.processes:
            proc = self.processes[tunnel_id]
            try:
                proc_info = psutil.Process(proc.pid)
                io_counters = proc_info.io_counters()
                process_bytes = io_counters.read_bytes + io_counters.write_bytes
                total_bytes = max(total_bytes, process_bytes)
            except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError, OSError):
                pass
        
        if tunnel_id not in self.usage_tracking:
            self.usage_tracking[tunnel_id] = 0.0
        
        if total_bytes > 0:
            current_mb = total_bytes / (1024 * 1024)
            if current_mb > self.usage_tracking[tunnel_id]:
                self.usage_tracking[tunnel_id] = current_mb
        
        return self.usage_tracking.get(tunnel_id, 0.0)

    def _render_toml(self, data: Dict[str, Dict[str, Any]]) -> str:
        def format_value(value: Any) -> str:
            if isinstance(value, bool):
                return "true" if value else "false"
            if isinstance(value, (int, float)):
                return str(value)
            if isinstance(value, list):
                if not value:
                    return "[]"
                rendered = ",\n  ".join(f"\"{str(item)}\"" for item in value)
                return "[\n  " + rendered + "\n]"
            value_str = str(value).replace("\\", "\\\\").replace('"', '\\"')
            return f"\"{value_str}\""

        lines: List[str] = []
        for section, values in data.items():
            lines.append(f"[{section}]")
            for key, val in values.items():
                if val is None:
                    continue
                lines.append(f"{key} = {format_value(val)}")
            lines.append("")
        return "\n".join(lines).strip() + "\n"

    def _resolve_binary_path(self) -> Path:
        for candidate in self.binary_candidates:
            if candidate.exists():
                return candidate

        resolved = shutil.which("backhaul")
        if resolved:
            return Path(resolved)

        raise FileNotFoundError(
            "Backhaul binary not found. Expected at BACKHAUL_CLIENT_BINARY, '/usr/local/bin/backhaul', or in PATH."
        )


class AdapterManager:
    """Manager for core adapters"""
    
    def __init__(self):
        self.adapters: Dict[str, CoreAdapter] = {
            "rathole": RatholeAdapter(),
            "backhaul": BackhaulAdapter(),
        }
        self.active_tunnels: Dict[str, CoreAdapter] = {}
        self.usage_tracking: Dict[str, float] = {}
    
    def get_adapter(self, tunnel_core: str) -> Optional[CoreAdapter]:
        """Get adapter for tunnel core"""
        return self.adapters.get(tunnel_core)
    
    async def apply_tunnel(self, tunnel_id: str, tunnel_core: str, spec: Dict[str, Any]):
        """Apply tunnel using appropriate adapter"""
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Applying tunnel {tunnel_id}: core={tunnel_core}")
        
        adapter = self.get_adapter(tunnel_core)
        if not adapter:
            error_msg = f"Unknown tunnel core: {tunnel_core}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        logger.info(f"Using adapter: {adapter.name}")
        adapter.apply(tunnel_id, spec)
        self.active_tunnels[tunnel_id] = adapter
        if tunnel_id not in self.usage_tracking:
            self.usage_tracking[tunnel_id] = 0.0
        logger.info(f"Tunnel {tunnel_id} applied successfully")
    
    async def remove_tunnel(self, tunnel_id: str):
        """Remove tunnel"""
        if tunnel_id in self.active_tunnels:
            adapter = self.active_tunnels[tunnel_id]
            adapter.remove(tunnel_id)
            del self.active_tunnels[tunnel_id]
        if tunnel_id in self.usage_tracking:
            del self.usage_tracking[tunnel_id]
    
    async def get_tunnel_status(self, tunnel_id: str) -> Dict[str, Any]:
        """Get tunnel status"""
        if tunnel_id in self.active_tunnels:
            adapter = self.active_tunnels[tunnel_id]
            return adapter.status(tunnel_id)
        return {"active": False}
    
    async def cleanup(self):
        """Cleanup all tunnels"""
        for tunnel_id in list(self.active_tunnels.keys()):
            await self.remove_tunnel(tunnel_id)

