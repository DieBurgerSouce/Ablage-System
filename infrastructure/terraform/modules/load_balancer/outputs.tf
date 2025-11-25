# Load Balancer Module Outputs

output "lb_vm_id" {
  description = "Load balancer VM ID"
  value       = proxmox_vm_qemu.load_balancer.vmid
}

output "lb_vm_ip" {
  description = "Load balancer VM IP"
  value       = proxmox_vm_qemu.load_balancer.default_ipv4_address
}

output "public_ip" {
  description = "Public IP address"
  value       = proxmox_vm_qemu.load_balancer.default_ipv4_address
}

output "private_ip" {
  description = "Private IP address"
  value       = proxmox_vm_qemu.load_balancer.default_ipv4_address
}

output "application_url" {
  description = "Application URL"
  value       = var.enable_ssl ? "https://${var.domain_name}" : "http://${var.domain_name}"
}

output "nginx_config_file" {
  description = "Path to Nginx config template"
  value       = local_file.nginx_config.filename
}

output "health_check_script" {
  description = "Path to health check script"
  value       = local_file.health_check.filename
}
