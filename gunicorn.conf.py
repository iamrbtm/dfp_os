import os

bind = "0.0.0.0:5000"
workers = int(os.getenv("GUNICORN_WORKERS", "2"))
threads = int(os.getenv("GUNICORN_THREADS", "2"))
timeout = int(os.getenv("GUNICORN_TIMEOUT", "120"))
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", "5"))
preload_app = os.getenv("GUNICORN_PRELOAD", "true").lower() == "true"
reload = os.getenv("GUNICORN_RELOAD", "false").lower() == "true"
worker_class = "sync"
accesslog = "-"
errorlog = "-"
