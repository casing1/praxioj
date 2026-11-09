#!/usr/bin/env python3
"""Copy canonical notices into independently distributed packages and web assets."""

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COPIES = {
    "LICENSE": ("packages/framework/LICENSE", "apps/api/LICENSE", "apps/web/public/LICENSE.txt"),
    "NOTICE": ("packages/framework/NOTICE", "apps/api/NOTICE", "apps/web/public/NOTICE.txt"),
    "THIRD_PARTY_NOTICES.txt": ("apps/web/public/THIRD_PARTY_NOTICES.txt",),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Report missing or outdated copies without writing")
    args = parser.parse_args()
    stale = []
    for source, destinations in COPIES.items():
        content = (ROOT / source).read_bytes()
        for relative in destinations:
            destination = ROOT / relative
            if args.check:
                if not destination.is_file() or destination.read_bytes() != content:
                    stale.append(relative)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
    if stale:
        parser.exit(1, "Outdated license copies; run python3 scripts/sync-licenses.py:\n" + "\n".join(stale) + "\n")
    print("License copies match canonical files." if args.check else "License copies updated.")


if __name__ == "__main__":
    main()
