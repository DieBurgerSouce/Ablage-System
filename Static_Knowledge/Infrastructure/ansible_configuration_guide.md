# Ansible Configuration Management Guide
**Ablage-System - Automatisierte Konfigurationsverwaltung**

Version: 1.0
Last Updated: 2025-01-23
Owner: DevOps Team
Status: PRODUCTION

---

## Executive Summary

Complete Ansible configuration management guide for Ablage-System, covering automated server provisioning, application deployment, and configuration orchestration for on-premises infrastructure.

**Key Features:**
- ✅ Idempotent Playbooks: Safe to run multiple times
- ✅ Role-Based Organization: Modular, reusable components
- ✅ Secrets Management: Ansible Vault integration
- ✅ Multi-Environment: Dev, staging, production inventories

---

## Table of Contents

1. [Ansible Architecture](#ansible-architecture)
2. [Project Structure](#project-structure)
3. [Inventory Management](#inventory-management)
4. [Playbooks](#playbooks)
5. [Roles](#roles)
6. [Secrets Management](#secrets-management)
7. [Best Practices](#best-practices)

---

## Ansible Architecture

### Configuration Flow

```
Ansible Control Node
       ↓
    Playbook
       ↓
   Inventory (hosts)
       ↓
    Roles (tasks)
       ↓
  Target Servers
  ├── GPU Server
  ├── Database Server
  └── Application Servers
```

### Components

- **Control Node:** Machine running Ansible commands
- **Inventory:** List of target servers
- **Playbooks:** YAML files defining automation workflows
- **Roles:** Reusable collections of tasks, variables, and files
- **Modules:** Ansible built-in tools for system operations

---

## Project Structure

```
infrastructure/ansible/
├── ansible.cfg                    # Ansible configuration
├── requirements.yml               # Ansible Galaxy dependencies
│
├── inventory/
│   ├── dev/
│   │   ├── hosts.yml              # Development servers
│   │   └── group_vars/
│   │       ├── all.yml
│   │       └── gpu_servers.yml
│   ├── staging/
│   │   ├── hosts.yml
│   │   └── group_vars/
│   └── production/
│       ├── hosts.yml
│       ├── group_vars/
│       │   ├── all.yml
│       │   ├── gpu_servers.yml
│       │   └── db_servers.yml
│       └── host_vars/
│           └── ablage-prod-01.yml
│
├── playbooks/
│   ├── site.yml                   # Master playbook
│   ├── provision.yml              # Server provisioning
│   ├── deploy.yml                 # Application deployment
│   ├── update.yml                 # System updates
│   └── backup.yml                 # Backup operations
│
├── roles/
│   ├── common/                    # Common server setup
│   ├── docker/                    # Docker installation
│   ├── nvidia/                    # NVIDIA drivers & CUDA
│   ├── postgresql/                # PostgreSQL setup
│   ├── redis/                     # Redis setup
│   ├── minio/                     # MinIO object storage
│   ├── monitoring/                # Prometheus, Grafana
│   └── ablage_app/                # Ablage application
│
├── files/                         # Static files
│   ├── ssl/
│   │   ├── cert.pem
│   │   └── key.pem
│   └── configs/
│       └── nginx.conf
│
├── templates/                     # Jinja2 templates
│   ├── docker-compose.yml.j2
│   ├── nginx.conf.j2
│   └── env.j2
│
└── vars/
    ├── secrets.yml                # Encrypted secrets (Ansible Vault)
    └── versions.yml               # Software versions
```

---

## Inventory Management

### Inventory File Structure

```yaml
# inventory/production/hosts.yml

all:
  children:
    gpu_servers:
      hosts:
        ablage-prod-01:
          ansible_host: 192.168.1.10
          ansible_user: admin
          ansible_python_interpreter: /usr/bin/python3

    db_servers:
      hosts:
        ablage-db-01:
          ansible_host: 192.168.1.20
          ansible_user: admin
          postgresql_version: "16"

    app_servers:
      hosts:
        ablage-app-01:
          ansible_host: 192.168.1.30
        ablage-app-02:
          ansible_host: 192.168.1.31
```

### Group Variables

```yaml
# inventory/production/group_vars/all.yml

# Common variables for all hosts
environment: production
domain: ablage.local

# Docker configuration
docker_version: "24.0.7"
docker_compose_version: "2.23.0"

# Application configuration
app_version: "1.3.0"
app_port: 8000

# Timezone
timezone: "Europe/Berlin"

# User management
admin_users:
  - name: admin
    ssh_key: "{{ lookup('file', '~/.ssh/id_rsa.pub') }}"
```

```yaml
# inventory/production/group_vars/gpu_servers.yml

# GPU-specific configuration
nvidia_driver_version: "535.129.03"
cuda_version: "12.2"
cudnn_version: "8.9"

# GPU settings
gpu_memory_fraction: 0.85  # Use 85% of GPU memory max
gpu_compute_mode: "EXCLUSIVE_PROCESS"

# NVIDIA Container Toolkit
nvidia_docker_runtime: true
```

### Host Variables

```yaml
# inventory/production/host_vars/ablage-prod-01.yml

# Server-specific configuration
server_role: "gpu_worker"
gpu_device_id: 0
gpu_pci_address: "0000:01:00.0"

# Performance tuning
max_workers: 4
worker_timeout: 300

# Backup schedule
backup_enabled: true
backup_time: "02:00"
backup_retention_days: 30
```

---

## Playbooks

### Master Playbook

```yaml
# playbooks/site.yml
# Master playbook orchestrating all roles

---
- name: Configure all Ablage infrastructure
  hosts: all
  become: yes
  gather_facts: yes

  pre_tasks:
    - name: Update package cache
      apt:
        update_cache: yes
        cache_valid_time: 3600

  roles:
    - common

- name: Setup GPU servers
  hosts: gpu_servers
  become: yes

  roles:
    - nvidia
    - docker
    - ablage_app

- name: Setup database servers
  hosts: db_servers
  become: yes

  roles:
    - postgresql

- name: Setup monitoring
  hosts: all
  become: yes

  roles:
    - monitoring
```

### Provisioning Playbook

```yaml
# playbooks/provision.yml
# Provision new servers from scratch

---
- name: Provision Ablage servers
  hosts: all
  become: yes
  gather_facts: yes

  vars:
    server_hardening: true
    install_monitoring: true

  tasks:
    - name: Set hostname
      hostname:
        name: "{{ inventory_hostname }}"

    - name: Set timezone
      timezone:
        name: "{{ timezone }}"

    - name: Install common packages
      apt:
        name:
          - curl
          - wget
          - git
          - vim
          - htop
          - net-tools
          - ca-certificates
          - gnupg
        state: present
        update_cache: yes

    - name: Create admin users
      user:
        name: "{{ item.name }}"
        groups: sudo
        shell: /bin/bash
        create_home: yes
      loop: "{{ admin_users }}"

    - name: Add SSH keys
      authorized_key:
        user: "{{ item.name }}"
        key: "{{ item.ssh_key }}"
        state: present
      loop: "{{ admin_users }}"

    - name: Disable root SSH login
      lineinfile:
        path: /etc/ssh/sshd_config
        regexp: '^PermitRootLogin'
        line: 'PermitRootLogin no'
        state: present
      notify: Restart SSH

    - name: Configure firewall
      ufw:
        rule: "{{ item.rule }}"
        port: "{{ item.port }}"
        proto: "{{ item.proto }}"
      loop:
        - { rule: 'allow', port: '22', proto: 'tcp' }
        - { rule: 'allow', port: '80', proto: 'tcp' }
        - { rule: 'allow', port: '443', proto: 'tcp' }
        - { rule: 'allow', port: '8000', proto: 'tcp' }

    - name: Enable firewall
      ufw:
        state: enabled

  handlers:
    - name: Restart SSH
      service:
        name: sshd
        state: restarted
```

### Deployment Playbook

```yaml
# playbooks/deploy.yml
# Deploy Ablage application

---
- name: Deploy Ablage application
  hosts: gpu_servers
  become: yes
  gather_facts: yes

  vars:
    app_dir: /opt/ablage
    deploy_user: ablage

  tasks:
    - name: Create application directory
      file:
        path: "{{ app_dir }}"
        state: directory
        owner: "{{ deploy_user }}"
        group: "{{ deploy_user }}"
        mode: '0755'

    - name: Copy Docker Compose file
      template:
        src: ../templates/docker-compose.yml.j2
        dest: "{{ app_dir }}/docker-compose.yml"
        owner: "{{ deploy_user }}"
        group: "{{ deploy_user }}"
        mode: '0644'
      notify: Restart Ablage

    - name: Copy environment file
      template:
        src: ../templates/env.j2
        dest: "{{ app_dir }}/.env"
        owner: "{{ deploy_user }}"
        group: "{{ deploy_user }}"
        mode: '0600'
      notify: Restart Ablage

    - name: Pull Docker images
      docker_compose:
        project_src: "{{ app_dir }}"
        pull: yes

    - name: Run database migrations
      docker_container:
        name: ablage_migration
        image: "ablage-backend:{{ app_version }}"
        command: alembic upgrade head
        env:
          DATABASE_URL: "{{ database_url }}"
        detach: no
        cleanup: yes

    - name: Start Ablage services
      docker_compose:
        project_src: "{{ app_dir }}"
        state: present
        restarted: yes

    - name: Wait for health check
      uri:
        url: "http://localhost:8000/health"
        status_code: 200
      retries: 10
      delay: 5
      register: health_check
      until: health_check.status == 200

  handlers:
    - name: Restart Ablage
      docker_compose:
        project_src: "{{ app_dir }}"
        restarted: yes
```

---

## Roles

### Common Role

```yaml
# roles/common/tasks/main.yml

---
- name: Update system packages
  apt:
    upgrade: dist
    update_cache: yes
    cache_valid_time: 3600

- name: Install essential packages
  apt:
    name:
      - build-essential
      - python3
      - python3-pip
      - git
      - curl
    state: present

- name: Configure NTP
  include_tasks: ntp.yml

- name: Setup log rotation
  include_tasks: logrotate.yml

- name: Configure system limits
  include_tasks: limits.yml
```

### NVIDIA Role

```yaml
# roles/nvidia/tasks/main.yml

---
- name: Check if NVIDIA GPU is present
  shell: lspci | grep -i nvidia
  register: nvidia_gpu
  ignore_errors: yes
  changed_when: false

- name: Fail if no NVIDIA GPU found
  fail:
    msg: "No NVIDIA GPU detected on this system"
  when: nvidia_gpu.rc != 0

- name: Add NVIDIA driver PPA
  apt_repository:
    repo: ppa:graphics-drivers/ppa
    state: present

- name: Install NVIDIA driver
  apt:
    name: "nvidia-driver-{{ nvidia_driver_version }}"
    state: present
  notify: Reboot server

- name: Install CUDA toolkit
  apt:
    name:
      - nvidia-cuda-toolkit
      - nvidia-cuda-toolkit-gcc
    state: present

- name: Add NVIDIA Container Toolkit repository
  shell: |
    distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
    curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | apt-key add -
    curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
      tee /etc/apt/sources.list.d/nvidia-docker.list
  args:
    creates: /etc/apt/sources.list.d/nvidia-docker.list

- name: Install NVIDIA Container Toolkit
  apt:
    name:
      - nvidia-docker2
      - nvidia-container-toolkit
    state: present
    update_cache: yes
  notify: Restart Docker

- name: Configure Docker to use NVIDIA runtime
  copy:
    content: |
      {
        "runtimes": {
          "nvidia": {
            "path": "nvidia-container-runtime",
            "runtimeArgs": []
          }
        },
        "default-runtime": "nvidia"
      }
    dest: /etc/docker/daemon.json
    mode: '0644'
  notify: Restart Docker

- name: Verify NVIDIA installation
  command: nvidia-smi
  register: nvidia_smi_output
  changed_when: false

- name: Display GPU information
  debug:
    var: nvidia_smi_output.stdout_lines
```

### Docker Role

```yaml
# roles/docker/tasks/main.yml

---
- name: Install Docker prerequisites
  apt:
    name:
      - apt-transport-https
      - ca-certificates
      - curl
      - gnupg
      - lsb-release
    state: present

- name: Add Docker GPG key
  apt_key:
    url: https://download.docker.com/linux/ubuntu/gpg
    state: present

- name: Add Docker repository
  apt_repository:
    repo: "deb [arch=amd64] https://download.docker.com/linux/ubuntu {{ ansible_distribution_release }} stable"
    state: present

- name: Install Docker
  apt:
    name:
      - docker-ce={{ docker_version }}~ubuntu-{{ ansible_distribution_release }}
      - docker-ce-cli={{ docker_version }}~ubuntu-{{ ansible_distribution_release }}
      - containerd.io
    state: present
    update_cache: yes

- name: Install Docker Compose
  get_url:
    url: "https://github.com/docker/compose/releases/download/v{{ docker_compose_version }}/docker-compose-linux-x86_64"
    dest: /usr/local/bin/docker-compose
    mode: '0755'

- name: Create docker group
  group:
    name: docker
    state: present

- name: Add users to docker group
  user:
    name: "{{ item }}"
    groups: docker
    append: yes
  loop: "{{ docker_users }}"

- name: Enable Docker service
  systemd:
    name: docker
    enabled: yes
    state: started

- name: Verify Docker installation
  command: docker --version
  register: docker_version_output
  changed_when: false

- name: Display Docker version
  debug:
    var: docker_version_output.stdout
```

### PostgreSQL Role

```yaml
# roles/postgresql/tasks/main.yml

---
- name: Install PostgreSQL
  apt:
    name:
      - postgresql-{{ postgresql_version }}
      - postgresql-contrib-{{ postgresql_version }}
      - python3-psycopg2
    state: present

- name: Ensure PostgreSQL is running
  systemd:
    name: postgresql
    state: started
    enabled: yes

- name: Create application database
  postgresql_db:
    name: "{{ db_name }}"
    encoding: UTF-8
    lc_collate: de_DE.UTF-8
    lc_ctype: de_DE.UTF-8
    template: template0
  become_user: postgres

- name: Create application user
  postgresql_user:
    name: "{{ db_user }}"
    password: "{{ db_password }}"
    db: "{{ db_name }}"
    priv: ALL
  become_user: postgres

- name: Configure PostgreSQL authentication
  lineinfile:
    path: "/etc/postgresql/{{ postgresql_version }}/main/pg_hba.conf"
    line: "host    {{ db_name }}    {{ db_user }}    172.28.0.0/16    md5"
    insertafter: EOF
  notify: Reload PostgreSQL

- name: Configure PostgreSQL to listen on all interfaces
  lineinfile:
    path: "/etc/postgresql/{{ postgresql_version }}/main/postgresql.conf"
    regexp: '^#?listen_addresses'
    line: "listen_addresses = '*'"
  notify: Restart PostgreSQL

- name: Install pgvector extension
  postgresql_ext:
    name: vector
    db: "{{ db_name }}"
  become_user: postgres
```

---

## Secrets Management

### Ansible Vault

```bash
# Create encrypted secrets file
ansible-vault create vars/secrets.yml

# Edit encrypted file
ansible-vault edit vars/secrets.yml

# Encrypt existing file
ansible-vault encrypt vars/secrets.yml

# Decrypt file
ansible-vault decrypt vars/secrets.yml

# View encrypted file
ansible-vault view vars/secrets.yml
```

### Secrets File Structure

```yaml
# vars/secrets.yml (encrypted with ansible-vault)

---
# Database credentials
db_password: "supersecretdbpassword"

# MinIO credentials
minio_access_key: "minio_admin"
minio_secret_key: "minio_secret_key_12345"

# Application secrets
app_secret_key: "django-insecure-secret-key"

# SSL certificates
ssl_cert_path: "/etc/ssl/certs/ablage.pem"
ssl_key_path: "/etc/ssl/private/ablage-key.pem"

# Grafana admin
grafana_admin_password: "grafana_admin_pass"
```

### Using Secrets in Playbooks

```yaml
# playbooks/deploy.yml

---
- name: Deploy with secrets
  hosts: all
  become: yes

  vars_files:
    - ../vars/secrets.yml

  tasks:
    - name: Create .env file
      template:
        src: env.j2
        dest: /opt/ablage/.env
        mode: '0600'
      vars:
        database_password: "{{ db_password }}"
        minio_secret: "{{ minio_secret_key }}"
```

### Run Playbook with Vault

```bash
# Prompt for vault password
ansible-playbook playbooks/deploy.yml --ask-vault-pass

# Use password file
ansible-playbook playbooks/deploy.yml --vault-password-file ~/.vault_pass.txt

# Use environment variable
export ANSIBLE_VAULT_PASSWORD_FILE=~/.vault_pass.txt
ansible-playbook playbooks/deploy.yml
```

---

## Best Practices

### 1. Idempotency

```yaml
# ❌ BAD: Not idempotent
- name: Append to file
  shell: echo "log_level=debug" >> /etc/app/config.ini

# ✅ GOOD: Idempotent
- name: Set log level
  lineinfile:
    path: /etc/app/config.ini
    regexp: '^log_level='
    line: 'log_level=debug'
```

### 2. Use Modules, Not Shell

```yaml
# ❌ BAD: Using shell
- name: Install package
  shell: apt-get install -y nginx

# ✅ GOOD: Using apt module
- name: Install nginx
  apt:
    name: nginx
    state: present
```

### 3. Handlers for Service Restarts

```yaml
# tasks
- name: Update nginx config
  template:
    src: nginx.conf.j2
    dest: /etc/nginx/nginx.conf
  notify: Reload nginx

# handlers
handlers:
  - name: Reload nginx
    service:
      name: nginx
      state: reloaded
```

### 4. Check Mode (Dry Run)

```bash
# Run in check mode (don't make changes)
ansible-playbook playbooks/deploy.yml --check

# Show diffs of file changes
ansible-playbook playbooks/deploy.yml --check --diff
```

### 5. Tags for Selective Execution

```yaml
# Playbook with tags
- name: Deploy application
  hosts: all
  become: yes

  tasks:
    - name: Update code
      git:
        repo: https://github.com/company/ablage.git
        dest: /opt/ablage
      tags: [deploy, code]

    - name: Restart services
      docker_compose:
        project_src: /opt/ablage
        restarted: yes
      tags: [deploy, restart]

# Run only specific tags
ansible-playbook playbooks/deploy.yml --tags "code"

# Skip specific tags
ansible-playbook playbooks/deploy.yml --skip-tags "restart"
```

---

## Common Commands

```bash
# Ping all hosts
ansible all -m ping

# Check disk space
ansible all -m shell -a "df -h"

# Run playbook
ansible-playbook playbooks/site.yml

# Run playbook for specific inventory
ansible-playbook -i inventory/production playbooks/deploy.yml

# Run playbook with extra variables
ansible-playbook playbooks/deploy.yml -e "app_version=1.4.0"

# Limit to specific hosts
ansible-playbook playbooks/site.yml --limit gpu_servers

# Run with increased verbosity
ansible-playbook playbooks/site.yml -vvv

# Syntax check
ansible-playbook playbooks/site.yml --syntax-check

# List tasks
ansible-playbook playbooks/site.yml --list-tasks

# List hosts
ansible-playbook playbooks/site.yml --list-hosts
```

---

## Related Documents

- [Terraform Infrastructure Guide](terraform_infrastructure_guide.md)
- [Docker Containerization Guide](docker_containerization_guide.md)
- [CI/CD Pipeline Guide](cicd_pipeline_guide.md)
- [Deployment Runbook](../../Execution_Layer/Runbooks/deployment_runbook.md)

---

## Revision History

| Version | Date       | Author      | Changes                      |
|---------|------------|-------------|------------------------------|
| 1.0     | 2025-01-23 | DevOps Team | Initial Ansible guide        |

---

**"Automation is not just about speed, it's about consistency and reliability."**

⚙️ **Configuration Management Excellence Achieved!**
