"""Operator-only directory registration; no imports or evaluator code execution."""
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.orm import Session
from praxioj.problems import ProblemManifest, load_problem_package, manifest_digest
from .models import Problem, ProblemVersion


class VersionConflict(ValueError):
    """An existing immutable version has different content."""


def register_manifest(db: Session, manifest: ProblemManifest, *, author_id: str | None = None) -> ProblemVersion:
    digest = manifest_digest(manifest)
    existing = db.scalar(select(ProblemVersion).where(
        ProblemVersion.problem_id == manifest.id,
        ProblemVersion.version == manifest.version,
    ))
    if existing:
        if existing.manifest_sha256 != digest:
            raise VersionConflict("This problem version already exists with different content; increment the version")
        return existing
    if db.get(Problem, manifest.id) is None:
        db.add(Problem(id=manifest.id, author_id=author_id))
        db.flush()
    version = ProblemVersion(
        problem_id=manifest.id, version=manifest.version,
        manifest_sha256=digest, manifest=manifest.model_dump(mode="json"),
    )
    db.add(version)
    db.flush()
    return version


def register_directory(db: Session, path: str | Path) -> ProblemVersion:
    return register_manifest(db, load_problem_package(Path(path)))
