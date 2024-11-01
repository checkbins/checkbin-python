import argparse

from .local import launch


def main():
    parser = argparse.ArgumentParser(description="Command line interface for Checkbin")
    subparsers = parser.add_subparsers(dest="command")

    start_parser = subparsers.add_parser("start")
    start_parser.add_argument("--next-port", type=int, help="Next.js port")
    start_parser.add_argument("--fastapi-port", type=int, help="FastAPI port")

    args = parser.parse_args()

    if args.command == "start":
        launch(next_port=args.next_port, fastapi_port=args.fastapi_port)
