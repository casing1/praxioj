# Licensing and distribution

PraxiOJ is DoHyun Choi's independent personal hobby open-source project, unrelated to university, research-laboratory, or corporate assignments. It is not an official institutional project. Choosing Apache-2.0 does not imply affiliation with the Apache Software Foundation.

## Project license and ownership

The official license for original PraxiOJ code is **Apache License 2.0**, SPDX identifier `Apache-2.0`. The root [LICENSE](../../LICENSE) is an unchanged copy of the [official Apache text](https://www.apache.org/licenses/LICENSE-2.0.txt). Its appendix is the upstream application template; the actual project attribution is in [NOTICE](../../NOTICE):

```text
Copyright 2026 DoHyun Choi
```

That project attribution does not claim ownership of contributions by others or of dependencies. Contributors retain their own copyright; no copyright assignment or CLA is required. See [CONTRIBUTING.md](../../CONTRIBUTING.md) for intentional contributions, third-party material, and review procedures.

Both Python distributions declare `license = "Apache-2.0"` and `license-files = ["LICENSE", "NOTICE"]` using [Python packaging metadata](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/#license). The web package and its root lockfile entry declare `"license": "Apache-2.0"`. The repository root `pyproject.toml` contains tool settings only; it is not a third Python distribution.

## NOTICE review

The 2026-11-09 review found no vendored third-party source in the project's own source directories that requires a specific upstream Apache NOTICE to be copied into the root NOTICE. The root NOTICE therefore contains project attribution and an explicit acknowledgment that contributors and third-party components retain their rights. It contains no invented institutional, sponsor, or Apache Software Foundation attribution.

Dependencies are not relicensed by this change. Their licenses in the npm lockfile and installed Python distributions remain intact. The root NOTICE is informational; it does not replace third-party license texts or add license conditions. The [Apache licensing FAQ](https://www.apache.org/foundation/license-faq.html#apply) describes keeping the license and considering a NOTICE file when applying the license to your own work.

The installed Python runtime includes `psycopg` and `psycopg-binary` 3.3.8, whose package metadata identifies `LGPL-3.0-only`, as well as dependencies under MIT, BSD, PSF, and Apache-2.0 terms. Binary wheels can also contain upstream native libraries with their own notices. Those components are not covered by PraxiOJ's project license; a binary or container release requires a review of that actual distribution and its applicable source and notice obligations.

## Distributed artifacts

- **Source checkout:** retain the root LICENSE, NOTICE, and applicable third-party notices.
- **Python wheels and source distributions:** package-local LICENSE and NOTICE copies are declared as license files so each distribution carries the project terms independently. Third-party dependencies are installed separately and keep their own license files; they are not bundled into the PraxiOJ wheels.
- **Static web bundle:** the bundle incorporates React, React DOM, Scheduler, and Vite's module-preload helper. Their confirmed original MIT notices are preserved in [THIRD_PARTY_NOTICES.txt](../../THIRD_PARTY_NOTICES.txt). Vite copies that file and the project LICENSE/NOTICE from `apps/web/public/` into `dist/`; the footer links to them. Minified code comments alone are not used to carry the attribution.
- **Containers:** the API includes the root project notices and installed dependency licenses. The web image includes the notices in its static assets. Base-image components retain their own terms; the web notices are not a complete inventory of the container operating system or all development tools.

The canonical files are at the repository root. After changing a canonical notice, synchronize its checked-in package copies and verify them:

```sh
python3 scripts/sync-licenses.py
python3 scripts/sync-licenses.py --check
```

For this change, both Python wheels were built and inspected: their metadata declares `License-Expression: Apache-2.0`, names DoHyun Choi as author, and includes byte-identical LICENSE and NOTICE files. The TypeScript/Vite build passed, and its three distributed notice files were compared with the canonical root files. This licensing change did not rerun the database or browser workflow tests recorded for Milestone 1.

Before distributing changed dependency sets, review the actual artifact and upstream license/NOTICE files. Preserve applicable copyright, permission, and attribution notices, record third-party source/version provenance, and identify modifications where required. Do not relabel dependencies as Apache-2.0 or replace another author's copyright with the project's copyright line. The current review covers the known project source and web bundle; it is not a blanket certification of every future artifact or dependency.
