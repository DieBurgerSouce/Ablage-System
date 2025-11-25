# Compute Module Variables

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "name_prefix" {
  description = "Name prefix for resources"
  type        = string
}

variable "backend_vm_count" {
  description = "Number of backend VMs"
  type        = number
}

variable "backend_vm_cores" {
  description = "CPU cores for backend VMs"
  type        = number
}

variable "backend_vm_memory" {
  description = "Memory in MB for backend VMs"
  type        = number
}

variable "backend_vm_disk" {
  description = "Disk size in GB for backend VMs"
  type        = number
}

variable "worker_vm_count" {
  description = "Number of worker VMs"
  type        = number
}

variable "worker_vm_cores" {
  description = "CPU cores for worker VMs"
  type        = number
}

variable "worker_vm_memory" {
  description = "Memory in MB for worker VMs"
  type        = number
}

variable "worker_vm_disk" {
  description = "Disk size in GB for worker VMs"
  type        = number
}

variable "worker_gpu_type" {
  description = "GPU type for workers"
  type        = string
}

variable "worker_gpu_count" {
  description = "Number of GPUs per worker"
  type        = number
}

variable "ssh_public_key" {
  description = "SSH public key"
  type        = string
}

variable "network_id" {
  description = "Network ID"
  type        = string
}

variable "subnet_id" {
  description = "Subnet ID"
  type        = string
}

variable "tags" {
  description = "Tags for resources"
  type        = map(string)
  default     = {}
}
