import hashlib
import shutil
import tempfile
from pathlib import Path


class TrialWorkspace:
    def __init__(self, fixture_dir: Path):
        self.fixture_dir = fixture_dir
        self.root = Path(tempfile.mkdtemp(prefix="lucas-eval-"))
        shutil.copytree(
            fixture_dir,
            self.root,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        self.baseline = snapshot_files(self.root)

    def changes(self) -> dict[str, str]:
        current = snapshot_files(self.root)
        changes = {}
        for path in sorted(self.baseline.keys() | current.keys()):
            if path not in self.baseline:
                changes[path] = "added"
            elif path not in current:
                changes[path] = "deleted"
            elif self.baseline[path] != current[path]:
                changes[path] = "modified"
        return changes

    def archive_to(self, destination: Path):
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(self.root, destination)

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


def snapshot_files(root: Path) -> dict[str, str]:
    snapshot = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"workspace symlink is not allowed: {path}")
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            snapshot[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return snapshot
