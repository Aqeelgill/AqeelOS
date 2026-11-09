# Gunicorn config for AqeelOS production deployment
bind = "0.0.0.0:8000"
workers = 2
worker_class = "sync"
worker_connections = 1000
timeout = 300
keepalive = 5
max_requests = 1000
max_requests_jitter = 50
preload_app = True

# Logging
accesslog = "/home/yourusername/aqeelos/logs/access.log"
errorlog = "/home/yourusername/aqeelos/logs/error.log"
loglevel = "info"

# Process naming
proc_name = "aqeelos"

# Security
limit_request_line = 4096
limit_request_fields = 100
limit_request_field_size = 8190
