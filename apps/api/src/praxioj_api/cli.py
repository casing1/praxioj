"""Trusted local operator commands; role elevation has no public bootstrap route."""
import argparse
import json
from sqlalchemy import select, update
from .database import make_engine, session_factory
from .models import AuthSession, User, utcnow
from .registry import register_directory
from .settings import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description="PraxiOJ local operator tools")
    sub = parser.add_subparsers(dest="command", required=True)
    register = sub.add_parser("register", help="Validate and register an operator-managed manifest directory")
    register.add_argument("directory")
    role = sub.add_parser("set-role", help="Set the role of an already registered account; revokes its login sessions")
    role.add_argument("username")
    role.add_argument("role", choices=["administrator", "author", "participant"])
    args = parser.parse_args()
    engine = make_engine(Settings().database_url)
    try:
        with session_factory(engine).begin() as db:
            if args.command == "set-role":
                user = db.scalar(select(User).where(User.username == args.username.strip().lower(), User.is_active.is_(True)).with_for_update())
                if user is None or not user.password_hash:
                    raise ValueError("An active registered account is required; legacy identities cannot be promoted")
                previous_role = user.role
                user.role = args.role
                db.execute(update(AuthSession).where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
                           .values(revoked_at=utcnow()))
                from .retention import audit
                audit(db, "role_changed", resource_id=user.id, previous_role=previous_role,
                      role=user.role, source="operator_cli")
                output = {"username": user.username, "role": user.role, "sessions_revoked": True}
            else:
                version = register_directory(db, args.directory)
                output = {"problem_id": version.problem_id, "version": version.version, "sha256": version.manifest_sha256}
        print(json.dumps(output))
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Operation rejected: {exc}\n")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
