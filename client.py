"""
client.py
---------
Minimal CLI client. Two modes:

  Interactive:
      python3 client.py --host 127.0.0.1 --port 9000
      > SET foo bar
      +OK 1
      > GET foo
      +VALUE bar

  One-shot:
      python3 client.py --host 127.0.0.1 --port 9000 --cmd "GET foo"
"""

from __future__ import annotations
import argparse
import socket

from protocol import LineConn, ConnectionClosed


def main() -> None:
    p = argparse.ArgumentParser(description="KV store client")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--cmd", default=None, help="run a single command and exit")
    args = p.parse_args()

    raw_sock = socket.create_connection((args.host, args.port))
    conn = LineConn(raw_sock)

    if args.cmd:
        conn.send_line(args.cmd)
        try:
            print(conn.read_line())
        except ConnectionClosed:
            print("(connection closed by server)")
        return

    print(f"connected to {args.host}:{args.port}. Commands: SET/GET/DEL/PING/INFO. Ctrl-D to quit.")
    try:
        while True:
            line = input("> ")
            if not line.strip():
                continue
            conn.send_line(line)
            print(conn.read_line())
    except (EOFError, KeyboardInterrupt):
        print()
    except ConnectionClosed:
        print("(connection closed by server)")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
