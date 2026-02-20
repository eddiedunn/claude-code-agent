"""Grind Server CLI."""
import argparse
import sys

def main() -> int:
    """Main entry point for grind-server command."""
    parser = argparse.ArgumentParser(
        prog="grind-server",
        description="Grind Server - REST API for the grind engine",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Start command
    start_parser = subparsers.add_parser("start", help="Start the server")
    start_parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    start_parser.add_argument("--port", type=int, default=8420, help="Port to bind to")
    start_parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    start_parser.add_argument("--daemon", action="store_true", help="Run as background daemon")

    # Status command
    subparsers.add_parser("status", help="Show server status")

    # Stop command
    subparsers.add_parser("stop", help="Stop the daemon")

    args = parser.parse_args()

    if args.command == "start":
        if args.daemon:
            return _start_daemon(args.host, args.port)
        return _run_server(args.host, args.port, args.reload)
    elif args.command == "status":
        return _show_status()
    elif args.command == "stop":
        return _stop_daemon()

    return 0

def _run_server(host: str, port: int, reload: bool) -> int:
    """Run the server with uvicorn."""
    import uvicorn
    uvicorn.run(
        "grind.server.app:create_app",
        factory=True,
        host=host,
        port=port,
        reload=reload,
    )
    return 0

def _start_daemon(host: str, port: int) -> int:
    """Start the server as a daemon."""
    from grind.server.daemon import daemonize, get_pid

    # Check if already running
    pid = get_pid()
    if pid is not None:
        print(f"Server already running (PID: {pid})", file=sys.stderr)
        return 1

    print(f"Starting grind-server daemon on {host}:{port}...")
    daemonize(host, port)
    # daemonize doesn't return (NoReturn)
    return 0

def _show_status() -> int:
    """Show server status."""
    from grind.server.daemon import get_pid, PID_FILE, LOG_FILE

    pid = get_pid()
    if pid is None:
        print("Server is not running")
        return 1

    print(f"Server is running (PID: {pid})")
    print(f"PID file: {PID_FILE}")
    print(f"Log file: {LOG_FILE}")
    return 0

def _stop_daemon() -> int:
    """Stop the daemon."""
    from grind.server.daemon import stop_daemon, get_pid

    pid = get_pid()
    if pid is None:
        print("Server is not running")
        return 1

    print(f"Stopping server (PID: {pid})...")
    if stop_daemon():
        print("Server stopped")
        return 0
    else:
        print("Failed to stop server", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
