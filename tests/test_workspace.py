import os

from workspace import LocalWorkspace


PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))


def test_local_workspace_uses_single_project_root():
    workspace = LocalWorkspace("ignored-user-id")

    assert workspace.user_id == "default"
    assert workspace.root == PROJECT_ROOT
    assert workspace.wiki_root == os.path.join(PROJECT_ROOT, "wiki")
    assert workspace.raw_root == os.path.join(PROJECT_ROOT, "raw")
    assert workspace.ingested_root == os.path.join(PROJECT_ROOT, "ingested")
    assert workspace.reports_root == os.path.join(PROJECT_ROOT, "reports")
    assert workspace.memory_root == os.path.join(PROJECT_ROOT, "memory")
