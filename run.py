#!/usr/bin/env python3
"""
Entry point for the Accounting System application.

Initializes Flask and starts both the API server (port 5061) and the HMI
server (port 5062) — either together (default) or one at a time.

Fail-fast on port conflict: if either port is already bound when we try to
bind, the whole process exits with code 2 so systemd's StartLimitBurst=10
stops the restart-loop. Otherwise the daemon threads die cleanly (rc=0),
which `Restart=always` happily restarts — that catch-all is preserved for
the 2026-08-27 daemon-thread-crash case.

Clean shutdown: SIGTERM/SIGINT triggers server.shutdown() on both servers
so ports are released promptly, avoiding the race where systemd's restart
sends SIGTERM to a process that takes its sweet time releasing sockets.
"""

import errno
import os
import signal
import socket
import sys
import argparse
from threading import Thread

from dotenv import load_dotenv

load_dotenv()

from app import create_app
from app.models import db
from werkzeug.serving import make_server


# Exit code we use for "port collision" so systemd's StartLimitBurst caps
# the retry spam and operators see the service land in 'failed' state.
EXIT_PORT_IN_USE = 2


def init_database(app):
    """Initialize the database tables."""
    with app.app_context():
        db.create_all()
        print("Database tables created successfully.")


def _make_flask_server(host, port, app, label):
    """Bind+listen ourselves, then hand the socket fd to werkzeug so it
    skips its own bind_and_activate — and thus its `sys.exit(1)` failure
    path. That silent exit was turning EADDRINUSE into an infinite restart
    loop (systemd Restart=always + StartLimitBurst never tripping, because
    bind conflicts yielded exit code 1 with no operator-visible failure
    state). Pre-binding lets us fail loud with exit code 2.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        sock.listen(64)  # werkzeug default request_queue_size; doesn't matter much since threaded=True
    except OSError as e:
        sock.close()
        if e.errno == errno.EADDRINUSE:
            print(
                f"FATAL [{label}]: port {port} already in use by another "
                f"process. Run `ss -tlnp 'sport = :{port}'` to find the "
                f"holder. Exiting {EXIT_PORT_IN_USE} so systemd stops "
                f"auto-restarting.",
                file=sys.stderr,
                flush=True,
            )
            os._exit(EXIT_PORT_IN_USE)
        raise
    sock_fd = sock.fileno()
    # Hand the bound+listening socket to werkzeug via its `fd=` param.
    # When fd is passed, BaseWSGIServer.__init__ skips its own bind/activate
    # and just wraps our socket via socket.fromfd.
    server = make_server(host, port, app, threaded=True, fd=sock_fd)
    # Close our local handle; werkzeug's fromfd duplicated the fd, our copy
    # is no longer needed.
    sock.close()
    return server


def _serve(server, label):
    """Block on the WSGI server until shutdown() is called. Exits non-zero
    if the port is yanked out from under us mid-serve."""
    print(f"Starting {label} server on {server.host}:{server.port}", flush=True)
    try:
        server.serve_forever()
    except OSError as e:
        if e.errno == errno.EADDRINUSE:
            print(
                f"FATAL [{label}]: port {server.port} became in-use during "
                f"serve_forever. Exiting {EXIT_PORT_IN_USE}.",
                file=sys.stderr,
                flush=True,
            )
            os._exit(EXIT_PORT_IN_USE)
        raise
    print(f"{label} server stopped.", flush=True)


def _install_signal_handlers(servers):
    """SIGTERM/SIGINT → server.shutdown() on every server. Called from the
    main thread before threading starts so port release is prompt."""
    def _shutdown_all(*_):
        for s in servers:
            try:
                s.shutdown()
            except Exception:
                pass

    signal.signal(signal.SIGTERM, _shutdown_all)
    signal.signal(signal.SIGINT, _shutdown_all)


def main():
    parser = argparse.ArgumentParser(description='Accounting System')
    parser.add_argument('--config', '-c', default='config.yaml',
                        help='Path to configuration file')
    parser.add_argument('--init-db', action='store_true',
                        help='Initialize database tables only')
    parser.add_argument('--api-only', action='store_true',
                        help='Run API server only')
    parser.add_argument('--hmi-only', action='store_true',
                        help='Run HMI server only')
    parser.add_argument('--api-port', type=int, default=5061,
                        help='API server port (default: 5061)')
    parser.add_argument('--hmi-port', type=int, default=5062,
                        help='HMI server port (default: 5062)')
    parser.add_argument('--host', default='192.168.4.44',
                        help='Host address (default: 192.168.4.44)')

    args = parser.parse_args()

    config_path = args.config
    if not os.path.exists(config_path):
        print(f"Warning: Config file '{config_path}' not found. Using defaults.")

    app = create_app(config_path if os.path.exists(config_path) else None)

    init_database(app)

    if args.init_db:
        print("Database initialization complete.")
        return

    host = args.host

    if args.api_only:
        server = _make_flask_server(host, args.api_port, app, 'API')
        _install_signal_handlers([server])
        _serve(server, 'API')
        return

    if args.hmi_only:
        server = _make_flask_server(host, args.hmi_port, app, 'HMI')
        _install_signal_handlers([server])
        _serve(server, 'HMI')
        return

    # Both servers — bind BEFORE starting threads so a port conflict fails
    # the main process (with exit 2) instead of crashing a daemon thread.
    api_server = _make_flask_server(host, args.api_port, app, 'API')
    hmi_server = _make_flask_server(host, args.hmi_port, app, 'HMI')
    servers = [api_server, hmi_server]

    _install_signal_handlers(servers)

    api_thread = Thread(target=_serve, args=(api_server, 'API'), daemon=True)
    hmi_thread = Thread(target=_serve, args=(hmi_server, 'HMI'), daemon=True)
    api_thread.start()
    hmi_thread.start()

    print("Both servers started. SIGTERM/SIGINT for clean shutdown.", flush=True)

    api_thread.join()
    hmi_thread.join()


if __name__ == '__main__':
    main()
