# Compute Module - Ablage-System OCR
# Backend and Worker VMs

# Backend VMs
resource "proxmox_vm_qemu" "backend" {
  count = var.backend_vm_count

  name        = "${var.name_prefix}-backend-${count.index + 1}"
  target_node = "pve"  # Change to your Proxmox node name
  vmid        = 200 + count.index

  # VM Configuration
  cores   = var.backend_vm_cores
  sockets = 1
  memory  = var.backend_vm_memory

  # Boot configuration
  boot    = "order=scsi0"
  agent   = 1
  onboot  = true

  # Disk configuration
  disk {
    slot    = 0
    size    = "${var.backend_vm_disk}G"
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
  sshkeys   = var.ssh_public_key

  # Lifecycle
  lifecycle {
    ignore_changes = [
      network,
    ]
  }

  tags = var.tags
}

# Worker VMs (with GPU passthrough)
resource "proxmox_vm_qemu" "worker" {
  count = var.worker_vm_count

  name        = "${var.name_prefix}-worker-${count.index + 1}"
  target_node = "pve"  # Change to your Proxmox node name
  vmid        = 300 + count.index

  # VM Configuration
  cores   = var.worker_vm_cores
  sockets = 1
  memory  = var.worker_vm_memory

  # Boot configuration
  boot    = "order=scsi0"
  agent   = 1
  onboot  = true

  # GPU configuration
  # Note: Requires GPU passthrough configured in Proxmox
  # Format: hostpciX: 01:00,pcie=1
  # Uncomment and configure based on your GPU setup:
  # hostpci0 = "01:00,pcie=1"  # PCIe passthrough for GPU

  # Disk configuration
  disk {
    slot    = 0
    size    = "${var.worker_vm_disk}G"
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
  sshkeys   = var.ssh_public_key

  # Lifecycle
  lifecycle {
    ignore_changes = [
      network,
    ]
  }

  tags = var.tags
}

# Local file for SSH configuration
resource "local_file" "ssh_config" {
  filename = "${path.module}/ssh-config.txt"

  content = <<-EOT
    # SSH Configuration - Ablage-System ${var.name_prefix}

    # Backend VMs
    ${join("\n", [for i, vm in proxmox_vm_qemu.backend : "Host backend-${i + 1}\n  HostName ${vm.default_ipv4_address}\n  User root\n  IdentityFile ~/.ssh/id_rsa"])}

    # Worker VMs
    ${join("\n", [for i, vm in proxmox_vm_qemu.worker : "Host worker-${i + 1}\n  HostName ${vm.default_ipv4_address}\n  User root\n  IdentityFile ~/.ssh/id_rsa"])}
  EOT
}
