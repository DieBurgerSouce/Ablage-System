# Monitoring Module - Ablage-System OCR
# Prometheus, Grafana, and Alertmanager VM

resource "proxmox_vm_qemu" "monitoring" {
  name        = "${var.name_prefix}-monitoring"
  target_node = "pve"  # Change to your Proxmox node name
  vmid        = 180

  # VM Configuration
  cores   = var.monitoring_vm_cores
  sockets = 1
  memory  = var.monitoring_vm_memory

  # Boot configuration
  boot    = "order=scsi0"
  agent   = 1
  onboot  = true

  # Disk configuration
  disk {
    slot    = 0
    size    = "${var.monitoring_vm_disk}G"
    type    = "scsi"
    storage = "local-lvm"
    ssd     = 1
    discard = "on"
  }

  # Network configuration
  network {
    model  = "virtio"
    bridge = var.network_id
  }

  # Cloud-init configuration
  os_type   = "cloud-init"
  ipconfig0 = "ip=dhcp"

  # Lifecycle
  lifecycle {
    ignore_changes = [
      network,
    ]
  }

  tags = var.tags
}

# Prometheus configuration
resource "local_file" "prometheus_config" {
  filename = "${path.module}/prometheus.yml.template"

  content = <<-EOT
    # Prometheus Configuration - Ablage-System ${var.environment}

    global:
      scrape_interval: 15s
      evaluation_interval: 15s
      external_labels:
        environment: ${var.environment}
        cluster: ablage-system

    alerting:
      alertmanagers:
        - static_configs:
            - targets: ['localhost:9093']

    rule_files:
      - 'alerts/*.yml'

    scrape_configs:
      # Prometheus self-monitoring
      - job_name: 'prometheus'
        static_configs:
          - targets: ['localhost:9090']

      # Backend servers
      - job_name: 'ablage-backend'
        static_configs:
          - targets: ${jsonencode([for ip in var.backend_targets : "${ip}:8000"])}

      # Worker servers
      - job_name: 'ablage-worker'
        static_configs:
          - targets: ${jsonencode([for ip in var.worker_targets : "${ip}:8001"])}

      # Database
      - job_name: 'postgres'
        static_configs:
          - targets: ${jsonencode([for ip in var.database_targets : "${ip}:9187"])}

      # Load balancer
      - job_name: 'nginx'
        static_configs:
          - targets: ${jsonencode([for ip in var.lb_targets : "${ip}:9113"])}

      # Node exporter (system metrics)
      - job_name: 'node'
        static_configs:
          - targets: ${jsonencode([for ip in concat(var.backend_targets, var.worker_targets, var.database_targets, var.lb_targets) : "${ip}:9100"])}
  EOT
}

# Grafana datasource configuration
resource "local_file" "grafana_datasource" {
  filename = "${path.module}/grafana-datasource.yml"

  content = <<-EOT
    apiVersion: 1

    datasources:
      - name: Prometheus
        type: prometheus
        access: proxy
        url: http://localhost:9090
        isDefault: true
        editable: true
  EOT
}
