# Database Module Outputs

output "postgres_vm_id" {
  description = "PostgreSQL VM ID"
  value       = proxmox_vm_qemu.postgres.vmid
}

output "postgres_vm_ip" {
  description = "PostgreSQL VM IP address"
  value       = proxmox_vm_qemu.postgres.default_ipv4_address
}

output "postgres_endpoint" {
  description = "PostgreSQL connection endpoint"
  value       = "${proxmox_vm_qemu.postgres.default_ipv4_address}:5432"
}

output "postgres_config_file" {
  description = "Path to PostgreSQL config template"
  value       = local_file.postgres_config.filename
}

output "backup_script_path" {
  description = "Path to backup script"
  value       = local_file.backup_script.filename
}

output "connection_string" {
  description = "PostgreSQL connection string template"
  value       = "postgresql://ablage_user:PASSWORD@${proxmox_vm_qemu.postgres.default_ipv4_address}:5432/ablage_system"
  sensitive   = true
}
