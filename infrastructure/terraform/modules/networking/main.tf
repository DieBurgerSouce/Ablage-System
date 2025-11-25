# Networking Module - Ablage-System OCR

resource "proxmox_vm_qemu" "network_bridge" {
  count = 0  # Proxmox uses existing network bridges

  # This module configures firewall rules and network settings
  # Actual network infrastructure managed by Proxmox host
}

# Locals for network configuration
locals {
  network_id        = "vmbr0"  # Default Proxmox bridge
  public_subnet_id  = "vmbr0"
  private_subnet_id = "vmbr1"
}

# Security group rules (implemented via Proxmox firewall)
resource "local_file" "firewall_rules" {
  filename = "${path.module}/firewall-rules.txt"

  content = <<-EOT
    # Firewall Rules - Ablage-System ${var.environment}
    # Apply these rules in Proxmox firewall configuration

    # SSH access
    ${join("\n", [for cidr in var.allowed_ssh_cidrs : "ACCEPT tcp ${cidr} 22 # SSH from ${cidr}"])}

    # HTTP/HTTPS access
    ${join("\n", [for cidr in var.allowed_http_cidrs : "ACCEPT tcp ${cidr} 80 # HTTP from ${cidr}"])}
    ${join("\n", [for cidr in var.allowed_https_cidrs : "ACCEPT tcp ${cidr} 443 # HTTPS from ${cidr}"])}

    # Internal network communication
    ACCEPT all ${var.private_subnet_cidr} # Internal subnet

    # Drop all other traffic
    DROP all
  EOT
}
