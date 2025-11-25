# Monitoring Module Outputs

output "monitoring_vm_id" {
  description = "Monitoring VM ID"
  value       = proxmox_vm_qemu.monitoring.vmid
}

output "monitoring_vm_ip" {
  description = "Monitoring VM IP"
  value       = proxmox_vm_qemu.monitoring.default_ipv4_address
}

output "grafana_url" {
  description = "Grafana URL"
  value       = "http://${proxmox_vm_qemu.monitoring.default_ipv4_address}:3000"
}

output "prometheus_url" {
  description = "Prometheus URL"
  value       = "http://${proxmox_vm_qemu.monitoring.default_ipv4_address}:9090"
}

output "alertmanager_url" {
  description = "Alertmanager URL"
  value       = var.alertmanager_enabled ? "http://${proxmox_vm_qemu.monitoring.default_ipv4_address}:9093" : null
}

output "prometheus_config_file" {
  description = "Path to Prometheus config template"
  value       = local_file.prometheus_config.filename
}

output "grafana_datasource_file" {
  description = "Path to Grafana datasource config"
  value       = local_file.grafana_datasource.filename
}
