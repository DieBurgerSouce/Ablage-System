#!/usr/bin/env python3
"""
Start one or more servers, wait for them to be ready, run a command, then clean up.

Usage:
    # Single server
    python scripts/with_server.py --server "npm run dev" --port 5173 -- python automation.py
    python scripts/with_server.py --server "npm start" --port 3000 -- python test.py

    # Multiple servers
    python scripts/with_server.py \
      --server "cd backend && python server.py" --port 3000 \
      --server "cd frontend && npm run dev" --port 5173 \
      -- python test.py

    # Ablage-System (Docker already running)
    python scripts/with_server.py --port 80 -- python my_playwright_test.py
"""

import subprocess
import socket
import time
import sys
import argparse


def is_server_ready(port: int, timeout: int = 30) -> bool:
    """Wait for server to be ready by polling the port."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with socket.create_connection(('localhost', port), timeout=1):
                return True
        except (socket.error, ConnectionRefusedError):
            time.sleep(0.5)
    return False


def main():
    parser = argparse.ArgumentParser(
        description='Run command with one or more servers',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Wait for Docker services and run test
  python with_server.py --port 80 --port 8000 -- python test.py

  # Start server and run automation
  python with_server.py --server "npm run dev" --port 5173 -- python automation.py

  # Multiple servers
  python with_server.py \\
    --server "cd backend && uvicorn main:app" --port 8000 \\
    --server "cd frontend && npm run dev" --port 5173 \\
    -- python e2e_test.py
        """
    )
    parser.add_argument(
        '--server',
        action='append',
        dest='servers',
        default=[],
        help='Server command to start (can be repeated, optional if servers already running)'
    )
    parser.add_argument(
        '--port',
        action='append',
        dest='ports',
        type=int,
        required=True,
        help='Port to wait for (must match --server count if servers specified)'
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=30,
        help='Timeout in seconds per server (default: 30)'
    )
    parser.add_argument(
        'command',
        nargs=argparse.REMAINDER,
        help='Command to run after server(s) ready'
    )

    args = parser.parse_args()

    # Remove the '--' separator if present
    if args.command and args.command[0] == '--':
        args.command = args.command[1:]

    if not args.command:
        print("Error: No command specified to run")
        sys.exit(1)

    # Validate server/port count if servers specified
    if args.servers and len(args.servers) != len(args.ports):
        print("Error: Number of --server and --port arguments must match")
        sys.exit(1)

    server_processes = []

    try:
        if args.servers:
            # Start all servers
            for i, (cmd, port) in enumerate(zip(args.servers, args.ports)):
                print(f"Starting server {i+1}/{len(args.servers)}: {cmd}")

                # Use shell=True to support commands with cd and &&
                process = subprocess.Popen(
                    cmd,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                server_processes.append(process)

                # Wait for this server to be ready
                print(f"Waiting for server on port {port}...")
                if not is_server_ready(port, timeout=args.timeout):
                    raise RuntimeError(
                        f"Server failed to start on port {port} within {args.timeout}s"
                    )

                print(f"Server ready on port {port}")

            print(f"\nAll {len(args.servers)} server(s) ready")
        else:
            # Just wait for ports (servers already running, e.g., Docker)
            print(f"Waiting for {len(args.ports)} port(s)...")
            for port in args.ports:
                print(f"Checking port {port}...")
                if not is_server_ready(port, timeout=args.timeout):
                    raise RuntimeError(
                        f"No server found on port {port} within {args.timeout}s"
                    )
                print(f"Port {port} ready")

            print(f"\nAll {len(args.ports)} port(s) ready")

        # Run the command
        print(f"Running: {' '.join(args.command)}\n")
        result = subprocess.run(args.command)
        sys.exit(result.returncode)

    finally:
        # Clean up all servers we started
        if server_processes:
            print(f"\nStopping {len(server_processes)} server(s)...")
            for i, process in enumerate(server_processes):
                try:
                    process.terminate()
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                print(f"Server {i+1} stopped")
            print("All servers stopped")


if __name__ == '__main__':
    main()
