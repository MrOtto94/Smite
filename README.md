# Smite - Tunneling Control Panel

<div align="center">
  <img src="assets/SmiteD.png" alt="Smite Logo" width="200"/>
</div>

A modern, Docker-first tunneling control panel for managing tunnels (TCP, UDP, WS, gRPC, TCPMux, Rathole).

## Panel Installation

### Quick Install

```bash
sudo bash -c "$(curl -sL https://raw.githubusercontent.com/zZedix/Smite/master/scripts/install.sh)"
```

### Manual Install

1. Clone the repository:
```bash
git clone https://github.com/zZedix/Smite.git
cd Smite
```

2. Copy environment file and configure:
```bash
cp .env.example .env
# Edit .env with your settings
```

3. Install CLI tools:
```bash
sudo bash cli/install_cli.sh
```

4. Start services:
```bash
docker compose up -d
```

5. Create admin user:
```bash
smite admin create
```

6. Access the web interface at `http://localhost:8000`

## Node Installation

### Quick Install

```bash
sudo bash -c "$(curl -sL https://raw.githubusercontent.com/zZedix/Smite/master/scripts/smite-node.sh)"
```

The installer will prompt for:
- Panel CA certificate path
- Panel address (host:port)
- Node API port (default: 8888)
- Node name (default: node-1)

### Manual Install

1. Navigate to node directory:
```bash
cd node
```

2. Copy Panel CA certificate:
```bash
mkdir -p certs
cp /path/to/panel/ca.crt certs/ca.crt
```

3. Create `.env` file:
```bash
cat > .env << EOF
NODE_API_PORT=8888
NODE_NAME=node-1
PANEL_CA_PATH=/etc/smite-node/certs/ca.crt
PANEL_ADDRESS=panel.example.com:443
EOF
```

4. Start node:
```bash
docker compose up -d
```

## CLI Tools

### Panel CLI (`smite`)
```bash
smite admin create      # Create admin user
smite status            # Show system status
smite update            # Update and restart
smite logs              # View logs
```

### Node CLI (`smite-node`)
```bash
smite-node status       # Show node status
smite-node update       # Update node
smite-node logs         # View logs
```

## License

MIT

---

<div align="center">
  Made with ❤️ by <a href="https://github.com/zZedix">zZedix</a> | v0.1.0
</div>
