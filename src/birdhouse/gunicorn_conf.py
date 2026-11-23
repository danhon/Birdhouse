"""gunicorn's settings for Birdhouse (reverse-proxy PY-2, Birdhouse#9).

`birdhouse` (app.main) execs `gunicorn -c python:birdhouse.gunicorn_conf
"birdhouse.app:serve()"`, so gunicorn is the container's PID 1.

- One worker, with threads: `serve()` starts the poller thread in the worker
  it runs in, so one worker is one poller. A worker gunicorn replaces (after a
  timeout) starts the poller again in the new process; the old one is gone.
- No access log: gunicorn's line holds the query string (LOG-2). app.py's
  `after_request` line is the access log.
- gunicorn's own logger goes through the root logger, so its lines keep the
  LOG-1 formats that logs.setup() installs. That runs here, in the master,
  before the worker forks, so both processes log the same way.
"""
import logging
import os
from pathlib import Path

from gunicorn.glogging import Logger

from birdhouse import logs

bind = f"0.0.0.0:{os.environ.get('PORT', '8090')}"
workers = 1
threads = 4
timeout = 60
accesslog = None

logs.setup(os.environ.get("BUILD_SHA", "dev")[:7],
           "/logs/app.log" if Path("/logs").is_dir() else None)


class RootLogger(Logger):
    """gunicorn's error log through the root logger's handlers; no access log."""

    def setup(self, cfg):
        super().setup(cfg)
        self.error_log.handlers[:] = []
        self.error_log.propagate = True
        self.access_log.handlers[:] = []
        self.access_log.propagate = False


logger_class = RootLogger
