# Jupyter Lab Configuration for Ablage-System

c = get_config()  # noqa

# Notebook directory
c.ServerApp.notebook_dir = 'notebooks'

# Network configuration
c.ServerApp.ip = '0.0.0.0'
c.ServerApp.port = 8888
c.ServerApp.open_browser = False

# Security (development only - change for production)
c.ServerApp.token = ''
c.ServerApp.password = ''
c.ServerApp.allow_origin = '*'
c.ServerApp.allow_remote_access = True

# File management
c.FileContentsManager.delete_to_trash = True
c.FileContentsManager.hide_globs = [
    '__pycache__',
    '*.pyc',
    '*.pyo',
    '.ipynb_checkpoints',
    '.git',
    '.DS_Store',
]

# Kernel management
c.MappingKernelManager.cull_idle_timeout = 3600  # 1 hour
c.MappingKernelManager.cull_interval = 300  # 5 minutes

# Extensions
c.ServerApp.jpserver_extensions = {
    'jupyterlab': True,
}

# Logging
c.ServerApp.log_level = 'INFO'

# Git integration
c.ServerApp.terminado_settings = {
    'shell_command': ['/bin/bash']
}

# Performance
c.NotebookApp.max_buffer_size = 1024 * 1024 * 100  # 100MB

# Code execution
c.ServerApp.tornado_settings = {
    'headers': {
        'Content-Security-Policy': "frame-ancestors 'self'"
    }
}

# German language support
c.ServerApp.extra_template_paths = []
c.ServerApp.extra_static_paths = []

# GPU support
import os
os.environ['CUDA_VISIBLE_DEVICES'] = '0'  # Use first GPU

# Auto-reload modules (useful for development)
c.InteractiveShellApp.exec_lines = [
    '%load_ext autoreload',
    '%autoreload 2',
]
