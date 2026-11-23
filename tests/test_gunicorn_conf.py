"""gunicorn_conf.py: one worker (one poller), no access log (LOG-2), and
gunicorn's error log through the root logger's LOG-1 formats."""
import importlib
import logging
from types import SimpleNamespace

import pytest


@pytest.fixture
def conf(monkeypatch):
    root = logging.getLogger()
    saved = root.handlers[:], root.level
    import birdhouse.gunicorn_conf as c
    c = importlib.reload(c)
    yield c
    root.handlers[:], _ = saved
    root.setLevel(saved[1])


def test_one_worker_so_one_poller(conf):
    assert conf.workers == 1
    assert conf.threads >= 2


def test_no_access_log(conf):
    assert conf.accesslog is None


def test_binds_the_port(conf, monkeypatch):
    monkeypatch.setenv("PORT", "9001")
    import birdhouse.gunicorn_conf as c
    assert importlib.reload(c).bind == "0.0.0.0:9001"


def test_gunicorns_error_log_goes_through_the_root_logger(conf):
    from gunicorn.config import Config
    lg = conf.RootLogger(Config())
    assert lg.error_log.handlers == [] and lg.error_log.propagate
    assert lg.access_log.handlers == [] and not lg.access_log.propagate
