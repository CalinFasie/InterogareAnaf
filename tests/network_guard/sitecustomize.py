"""Protect subprocess-based acceptance tests from accidental external HTTP.

Python imports sitecustomize automatically when PYTHONPATH includes this directory.
Only loopback TCP connections are allowed during contract tests.
"""
import socket

_original_connect = socket.socket.connect
_original_connect_ex = socket.socket.connect_ex

_ALLOWED_HOSTS = {"127.0.0.1", "::1", "localhost"}


def _check(address):
    if isinstance(address, tuple) and address:
        if address[0] not in _ALLOWED_HOSTS:
            raise OSError("Contract tests forbid external connections: " + str(address[0]))


def connect(self, address):
    _check(address)
    return _original_connect(self, address)


def connect_ex(self, address):
    _check(address)
    return _original_connect_ex(self, address)


socket.socket.connect = connect
socket.socket.connect_ex = connect_ex
