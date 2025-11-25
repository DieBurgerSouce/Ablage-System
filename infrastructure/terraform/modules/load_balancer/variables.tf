# Load Balancer Module Variables

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "name_prefix" {
  description = "Name prefix for resources"
  type        = string
}

variable "lb_vm_cores" {
  description = "CPU cores for load balancer VM"
  type        = number
}

variable "lb_vm_memory" {
  description = "Memory in MB for load balancer VM"
  type        = number
}

variable "backend_targets" {
  description = "List of backend IP addresses"
  type        = list(string)
}

variable "enable_ssl" {
  description = "Enable SSL/TLS"
  type        = bool
}

variable "ssl_cert_path" {
  description = "Path to SSL certificate"
  type        = string
}

variable "ssl_key_path" {
  description = "Path to SSL private key"
  type        = string
}

variable "domain_name" {
  description = "Domain name"
  type        = string
}

variable "health_check_path" {
  description = "Health check endpoint path"
  type        = string
}

variable "health_check_interval" {
  description = "Health check interval in seconds"
  type        = number
}

variable "health_check_timeout" {
  description = "Health check timeout in seconds"
  type        = number
}

variable "network_id" {
  description = "Network ID"
  type        = string
}

variable "public_subnet_id" {
  description = "Public subnet ID"
  type        = string
}

variable "tags" {
  description = "Tags for resources"
  type        = map(string)
  default     = {}
}
