"""
用户工作区：所有用户数据访问的唯一入口。

当前实现: LocalWorkspace (本地文件系统)
未来实现: 可替换为 RDS+OSS 后端，业务层不感知。
"""
import os
import re
from abc import ABC, abstractmethod

_USER_ID_RE = re.compile(r'^[a-zA-Z0-9_-]{1,64}$')


class Workspace(ABC):
    """用户工作区抽象。每个用户一个独立实例。"""

    @property
    @abstractmethod
    def user_id(self) -> str: ...

    @property
    @abstractmethod
    def wiki_root(self) -> str: ...

    @property
    @abstractmethod
    def raw_root(self) -> str: ...

    @property
    @abstractmethod
    def memory_root(self) -> str: ...


_PROJECT_ROOT = os.path.dirname(__file__)
_WORKSPACES_BASE = os.path.join(_PROJECT_ROOT, "workspaces")


class LocalWorkspace(Workspace):
    """本地文件系统实现。目录: workspaces/{user_id}/{wiki,raw,memory}/"""

    _initialized_users: set[str] = set()

    def __init__(self, user_id: str):
        if not _USER_ID_RE.match(user_id or ""):
            raise ValueError(f"invalid user_id: {user_id!r}")
        self._user_id = user_id
        self._root = os.path.join(_WORKSPACES_BASE, user_id)
        if user_id not in self._initialized_users:
            for sub in ("wiki", "raw", "memory"):
                os.makedirs(os.path.join(self._root, sub), exist_ok=True)
            self._initialized_users.add(user_id)

    @property
    def user_id(self) -> str:
        return self._user_id

    @property
    def root(self) -> str:
        return self._root

    @property
    def wiki_root(self) -> str:
        return os.path.join(self._root, "wiki")

    @property
    def raw_root(self) -> str:
        return os.path.join(self._root, "raw")

    @property
    def memory_root(self) -> str:
        return os.path.join(self._root, "memory")
