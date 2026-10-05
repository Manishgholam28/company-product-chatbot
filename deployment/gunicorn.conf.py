"""One shared RAG instance; other threads can serve pages and health checks."""

import os

bind = f"0.0.0.0:{int(os.environ.get('PORT', '8000'))}"
workers = 1
worker_class = "gthread"
threads = 4
timeout = 240
graceful_timeout = 180
keepalive = 5
accesslog = "-"
errorlog = "-"
# Log paths without query strings, which can contain accidentally submitted text.
access_log_format = '%(h)s %(m)s %(U)s %(s)s %(L)s'
preload_app = False
