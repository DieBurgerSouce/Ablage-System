# Networking Module Variables

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "name_prefix" {
  description = "Name prefix for resources"
  type        = string
}

variable "network_cidr" {
  description = "CIDR block for main network"
  type        = string
}

variable "public_subnet_cidr" {
  description = "CIDR block for public subnet"
  type        = string
}

variable "private_subnet_cidr" {
  description = "CIDR block for private subnet"
  type        = string
}

variable "allowed_ssh_cidrs" {
  description = "CIDR blocks allowed to SSH"
  type        = list(string)
}

variable "allowed_http_cidrs" {
  description = "CIDR blocks allowed HTTP access"
  type        = list(string)
}

variable "allowed_https_cidrs" {
  description = "CIDR blocks allowed HTTPS access"
  type        = list(string)
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
