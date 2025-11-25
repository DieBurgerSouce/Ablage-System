# Compute Module Outputs

output "backend_vm_ids" {
  description = "IDs of backend VMs"
  value       = proxmox_vm_qemu.backend[*].vmid
}

output "backend_vm_ips" {
  description = "IP addresses of backend VMs"
  value       = proxmox_vm_qemu.backend[*].default_ipv4_address
}

output "backend_vm_names" {
  description = "Names of backend VMs"
  value       = proxmox_vm_qemu.backend[*].name
}

output "worker_vm_ids" {
  description = "IDs of worker VMs"
  value       = proxmox_vm_qemu.worker[*].vmid
}

output "worker_vm_ips" {
  description = "IP addresses of worker VMs"
  value       = proxmox_vm_qemu.worker[*].default_ipv4_address
}

output "worker_vm_names" {
  description = "Names of worker VMs"
  value       = proxmox_vm_qemu.worker[*].name
}

output "ssh_commands" {
  description = "SSH commands for connecting to VMs"
  value = {
    backend = [for ip in proxmox_vm_qemu.backend[*].default_ipv4_address : "ssh root@${ip}"]
    worker  = [for ip in proxmox_vm_qemu.worker[*].default_ipv4_address : "ssh root@${ip}"]
  }
}

output "ssh_config_file" {
  description = "Path to SSH config file"
  value       = local_file.ssh_config.filename
}
