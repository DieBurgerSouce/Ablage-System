# Systemd Services - Ablage-System OCR

Production systemd service configuration for automated service management.

## 🚀 Quick Start

```bash
# Run installation script as root
cd infrastructure/systemd
sudo ./install-services.sh

# Start all services
sudo systemctl start ablage-system.target

# Check status
sudo systemctl status ablage-system.service
```

## 📋 Services

### Main Services

- **ablage-system.target**: Target unit grouping all services
- **ablage-system.service**: Main Docker Compose stack service

### Component Services

- **ablage-backend.service**: Backend API service
- **ablage-worker.service**: Celery worker with GPU support

## ⚙️ Installation

### Automatic Installation

```bash
sudo ./install-services.sh
```

This script will:
1. Check prerequisites (systemd, Docker, docker-compose)
2. Create `ablage` system user
3. Setup `/opt/ablage-system` directory
4. Copy application files
5. Install systemd service files
6. Enable services for auto-start
7. Configure logging and logrotate
8. Setup firewall rules
9. Optionally start services

### Manual Installation

```bash
# Copy service files
sudo cp *.service *.target /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable services
sudo systemctl enable ablage-system.target
sudo systemctl enable ablage-system.service

# Start services
sudo systemctl start ablage-system.target
```

## 🔧 Configuration

### Environment File

Edit `/opt/ablage-system/.env`:

```bash
sudo nano /opt/ablage-system/.env
```

Required variables:
- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_URL`: Redis connection string
- `MINIO_*`: MinIO credentials
- `SECRET_KEY`: Application secret key

### Service Customization

Edit service files in `/etc/systemd/system/`:

```bash
sudo nano /etc/systemd/system/ablage-backend.service
```

After editing, reload:

```bash
sudo systemctl daemon-reload
sudo systemctl restart ablage-backend.service
```

## 📝 Common Commands

### Starting Services

```bash
# Start all services
sudo systemctl start ablage-system.target

# Start specific service
sudo systemctl start ablage-backend.service
```

### Stopping Services

```bash
# Stop all services
sudo systemctl stop ablage-system.target

# Stop specific service
sudo systemctl stop ablage-backend.service
```

### Restarting Services

```bash
# Restart all
sudo systemctl restart ablage-system.target

# Restart specific
sudo systemctl restart ablage-backend.service
```

### Status Check

```bash
# Status of all services
systemctl list-units ablage-* --all

# Detailed status
sudo systemctl status ablage-system.service

# Check if service is active
systemctl is-active ablage-backend.service
```

### Enable/Disable Auto-start

```bash
# Enable auto-start on boot
sudo systemctl enable ablage-system.target

# Disable auto-start
sudo systemctl disable ablage-system.target

# Check if enabled
systemctl is-enabled ablage-system.service
```

## 📊 Logging

### View Logs

```bash
# All services
sudo journalctl -u ablage-system.service -f

# Backend only
sudo journalctl -u ablage-backend.service -f

# Worker only
sudo journalctl -u ablage-worker.service -f

# Last 100 lines
sudo journalctl -u ablage-system.service -n 100

# Since today
sudo journalctl -u ablage-system.service --since today

# Filter by priority
sudo journalctl -u ablage-system.service -p err
```

### Log Rotation

Configured via `/etc/logrotate.d/ablage-system`:

- Rotation: Daily
- Retention: 14 days
- Compression: Enabled
- Location: `/opt/ablage-system/logs/`

Manually rotate logs:

```bash
sudo logrotate -f /etc/logrotate.d/ablage-system
```

## 🔒 Security

### Service Security Features

All services include:
- **NoNewPrivileges**: Prevents privilege escalation
- **PrivateTmp**: Isolated `/tmp` directory
- **User/Group**: Runs as `ablage` (non-root)
- **Resource Limits**: CPU, memory, and task limits

### Resource Limits

**Backend**:
- CPUQuota: 200%
- MemoryLimit: 4GB
- TasksMax: 256

**Worker**:
- CPUQuota: 400%
- MemoryLimit: 16GB (GPU workload)
- TasksMax: 512

### Firewall

Automatically configured with UFW or firewalld:
- Port 80 (HTTP)
- Port 443 (HTTPS)
- Port 22 (SSH)

## 🔄 Service Dependencies

```
ablage-system.target
├── ablage-system.service
├── ablage-backend.service
│   ├── docker.service
│   ├── ablage-postgres.service
│   └── ablage-redis.service
└── ablage-worker.service
    ├── docker.service
    ├── ablage-backend.service
    └── ablage-redis.service
```

## 🐛 Troubleshooting

### Service Won't Start

```bash
# Check status
sudo systemctl status ablage-backend.service

# View logs
sudo journalctl -u ablage-backend.service -n 50

# Check Docker
sudo docker ps

# Test configuration
sudo systemctl show ablage-backend.service
```

### Service Keeps Restarting

```bash
# Check restart count
systemctl show ablage-backend.service | grep NRestarts

# View restart times
journalctl -u ablage-backend.service | grep "Started\|Stopped"

# Check resource limits
systemctl show ablage-backend.service | grep -E "MemoryLimit|CPUQuota"
```

### Permission Issues

```bash
# Check file ownership
ls -la /opt/ablage-system

# Fix ownership
sudo chown -R ablage:ablage /opt/ablage-system

# Check Docker group
groups ablage
```

### GPU Not Working (Worker)

```bash
# Check nvidia-smi
nvidia-smi

# Check Docker GPU support
sudo docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi

# View worker logs
sudo journalctl -u ablage-worker.service -f
```

## 📈 Monitoring

### Service Health

```bash
# All services
systemctl status ablage-*

# Only failed services
systemctl --failed

# Service uptime
systemctl show ablage-backend.service -p ActiveEnterTimestamp
```

### Resource Usage

```bash
# Memory usage
systemctl status ablage-backend.service | grep Memory

# CPU usage
systemctl status ablage-backend.service | grep CPU

# View all resource stats
systemctl show ablage-backend.service | grep -E "Memory|CPU|Tasks"
```

### Health Checks

Built-in health checks:
- Backend: `ExecReload` checks `/health` endpoint
- Worker: Process monitoring via Docker

Manual health check:

```bash
curl -f http://localhost:8000/health || echo "Backend unhealthy"
```

## 🔄 Updates

### Update Application

```bash
# Stop services
sudo systemctl stop ablage-system.target

# Pull latest code
cd /opt/ablage-system
sudo -u ablage git pull

# Pull latest Docker images
sudo -u ablage docker-compose pull

# Start services
sudo systemctl start ablage-system.target
```

### Update Service Files

```bash
# Edit service
sudo nano /etc/systemd/system/ablage-backend.service

# Reload systemd
sudo systemctl daemon-reload

# Restart service
sudo systemctl restart ablage-backend.service
```

## 🎯 Best Practices

1. **Always use systemctl for service management**
   - Don't use `docker-compose` directly
   - Let systemd handle restarts

2. **Monitor logs regularly**
   - Setup log monitoring/alerting
   - Check for errors daily

3. **Test before production**
   - Use `systemctl status` before declaring healthy
   - Verify health endpoints

4. **Keep backups**
   - Backup before updates
   - Test restore procedures

5. **Resource monitoring**
   - Monitor memory/CPU usage
   - Adjust limits if needed

## 📚 References

- [systemd Documentation](https://www.freedesktop.org/software/systemd/man/)
- [systemd for Administrators](https://www.freedesktop.org/wiki/Software/systemd/)
- [Docker and systemd](https://docs.docker.com/config/daemon/systemd/)

---

**Last Updated**: 2025-01-24
**Maintainer**: Ablage-System Team
