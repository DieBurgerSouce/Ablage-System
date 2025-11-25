# Networking Module Outputs

output "network_id" {
  description = "Network ID"
  value       = local.network_id
}

output "public_subnet_id" {
  description = "Public subnet ID"
  value       = local.public_subnet_id
}

output "private_subnet_id" {
  description = "Private subnet ID"
  value       = local.private_subnet_id
}

output "private_subnet_cidr" {
  description = "Private subnet CIDR"
  value       = var.private_subnet_cidr
}

output "firewall_rules_file" {
  description = "Path to firewall rules file"
  value       = local_file.firewall_rules.filename
}
