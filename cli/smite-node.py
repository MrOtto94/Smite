#!/usr/bin/env python3
"""
Smite Node CLI
"""
import os
import sys
import subprocess
import argparse
from pathlib import Path


def get_compose_file():
    """Get docker-compose file path"""
    possible_roots = [
        Path("/opt/smite-node"),
        Path.cwd(),
        Path(__file__).parent.parent / "node",
    ]
    
    for node_dir in possible_roots:
        compose_file = node_dir / "docker-compose.yml"
        if compose_file.exists():
            return compose_file
    
    # Return default path if not found
    return Path("/opt/smite-node") / "docker-compose.yml"


def get_env_file():
    """Get .env file path"""
    possible_roots = [
        Path("/opt/smite-node"),
        Path.cwd(),
        Path(__file__).parent.parent / "node",
    ]
    
    for node_dir in possible_roots:
        env_file = node_dir / ".env"
        if env_file.exists():
            return env_file
    
    # Return default path if not found
    return Path("/opt/smite-node") / ".env"


def run_docker_compose(args, capture_output=False):
    """Run docker compose command"""
    compose_file = get_compose_file()
    if not compose_file.exists():
        print(f"Error: docker-compose.yml not found at {compose_file}")
        print(f"\nPlease ensure you're in the node directory or docker-compose.yml exists at:")
        print(f"  - /opt/smite-node/docker-compose.yml")
        print(f"  - {Path.cwd()}/docker-compose.yml")
        sys.exit(1)
    
    # Change to the directory containing docker-compose.yml so relative paths work
    compose_dir = compose_file.parent
    original_cwd = Path.cwd()
    
    try:
        os.chdir(compose_dir)
        cmd = ["docker", "compose", "-f", str(compose_file)] + args
        result = subprocess.run(cmd, capture_output=capture_output, text=True, cwd=str(compose_dir))
        return result
    finally:
        os.chdir(original_cwd)


def cmd_status(args):
    """Show node status"""
    print("Node Status:")
    print("-" * 50)
    
    result = subprocess.run(["docker", "ps", "--filter", "name=smite-node", "--format", "{{.Status}}"], 
                          capture_output=True, text=True)
    if result.stdout.strip():
        print(f"Docker: {result.stdout.strip()}")
    else:
        print("Docker: Not running")
    
    try:
        try:
            import requests
        except ImportError:
            print("API: requests library not installed")
            return
            
        env_file = get_env_file()
        port = 8888
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("NODE_API_PORT="):
                    port = int(line.split("=")[1])
        
        response = requests.get(f"http://localhost:{port}/api/agent/status", timeout=2)
        if response.status_code == 200:
            data = response.json()
            print(f"API: Running")
            print(f"Active Tunnels: {data.get('active_tunnels', 0)}")
        else:
            print("API: Not responding")
    except Exception as e:
        print(f"API: Not accessible ({e})")


def cmd_update(args):
    """Update node"""
    print("Updating node...")
    run_docker_compose(["pull"])
    run_docker_compose(["up", "-d", "--force-recreate"])


def cmd_edit(args):
    """Edit docker-compose.yml"""
    compose_file = get_compose_file()
    editor = os.environ.get("EDITOR", "nano")
    subprocess.run([editor, str(compose_file)])


def cmd_edit_env(args):
    """Edit .env file"""
    env_file = get_env_file()
    if not env_file.exists():
        print(f".env file not found. Creating...")
        env_file.parent.mkdir(parents=True, exist_ok=True)
        env_file.write_text("")
    
    editor = os.environ.get("EDITOR", "nano")
    subprocess.run([editor, str(env_file)])


def cmd_logs(args):
    """Stream logs"""
    follow = ["--follow"] if args.follow else []
    run_docker_compose(["logs"] + follow + ["smite-node"])


def main():
    parser = argparse.ArgumentParser(description="Smite Node CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    subparsers.add_parser("status", help="Show node status")
    
    subparsers.add_parser("update", help="Update node")
    
    subparsers.add_parser("edit", help="Edit docker-compose.yml")
    
    subparsers.add_parser("edit-env", help="Edit .env file")
    
    logs_parser = subparsers.add_parser("logs", help="View logs")
    logs_parser.add_argument("-f", "--follow", action="store_true", help="Follow logs")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    if args.command == "status":
        cmd_status(args)
    elif args.command == "update":
        cmd_update(args)
    elif args.command == "edit":
        cmd_edit(args)
    elif args.command == "edit-env":
        cmd_edit_env(args)
    elif args.command == "logs":
        cmd_logs(args)


if __name__ == "__main__":
    main()

