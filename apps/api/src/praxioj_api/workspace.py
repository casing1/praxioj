"""Session-bound logical storage. No filesystem calls or host path resolution."""
from hashlib import sha256
from sqlalchemy import select
from praxioj.tools import WorkspaceDocument, WorkspaceLimits, validate_workspace_path
from .models import SolveSession, WorkspaceFile


class DatabaseWorkspaceStore:
    """Caller must hold the session row lock for writes and quota checks."""
    def __init__(self, db, session_id: str, limits: WorkspaceLimits):
        self.db, self.session_id, self.limits = db, session_id, limits
        session = db.get(SolveSession, session_id)
        cap = session.profile_snapshot.get("resource_policy", {}).get("artifact_max_bytes") if session else None
        if cap is not None:
            self.limits = limits.model_copy(update={"max_workspace_bytes": min(cap, limits.max_workspace_bytes)})

    def _rows(self):
        return list(self.db.scalars(select(WorkspaceFile).where(
            WorkspaceFile.session_id == self.session_id).order_by(WorkspaceFile.path)))

    @staticmethod
    def document(row):
        return WorkspaceDocument(path=row.path, content=row.content, sha256=row.sha256,
                                 byte_size=row.byte_size, revision=row.revision)

    def list_files(self):
        return [self.document(row) for row in self._rows()]

    def read(self, path):
        path = validate_workspace_path(path)
        row = self.db.scalar(select(WorkspaceFile).where(
            WorkspaceFile.session_id == self.session_id, WorkspaceFile.path == path))
        return self.document(row) if row else None

    def write(self, path, content):
        path = validate_workspace_path(path)
        size = len(content.encode("utf-8"))
        rows = self._rows()
        row = next((r for r in rows if r.path == path), None)
        if size > self.limits.max_file_bytes:
            raise ValueError("File size limit exceeded")
        if row is None and len(rows) >= self.limits.max_workspace_files:
            raise ValueError("Workspace file limit exceeded")
        if sum(r.byte_size for r in rows) - (row.byte_size if row else 0) + size > self.limits.max_workspace_bytes:
            raise ValueError("Workspace size limit exceeded")
        if row is None:
            row = WorkspaceFile(session_id=self.session_id, path=path, revision=0)
            self.db.add(row)
        row.content, row.byte_size, row.sha256 = content, size, sha256(content.encode("utf-8")).hexdigest()
        row.revision += 1
        self.db.flush()
        return self.document(row)
