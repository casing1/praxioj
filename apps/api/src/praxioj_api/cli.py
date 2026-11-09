"""Trusted local operator commands, intentionally unavailable through HTTP."""
import argparse
import json
from .database import make_engine, session_factory
from .registry import register_directory
from .settings import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description="PraxiOJ local operator tools")
    sub = parser.add_subparsers(dest="command", required=True)
    register = sub.add_parser("register", help="Validate and register a manifest directory")
    register.add_argument("directory")
    args = parser.parse_args()
    engine = make_engine(Settings().database_url)
    try:
        with session_factory(engine).begin() as db:
            version = register_directory(db, args.directory)
            output = {"problem_id": version.problem_id, "version": version.version, "sha256": version.manifest_sha256}
        print(json.dumps(output))
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Registration rejected: {exc}\n")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
