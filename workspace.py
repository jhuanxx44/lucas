"""本地工作区：所有用户数据访问的唯一入口。"""
import os
from abc import ABC, abstractmethod


class Workspace(ABC):
    """工作区抽象，保留后续替换存储后端的边界。"""

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
    def ingested_root(self) -> str: ...

    @property
    @abstractmethod
    def reports_root(self) -> str: ...

    @property
    @abstractmethod
    def memory_root(self) -> str: ...


_PROJECT_ROOT = os.path.dirname(__file__)


class LocalWorkspace(Workspace):
    """单用户本地文件系统实现，使用项目根目录下的数据。"""

    def __init__(self, user_id: str = "default"):
        self._user_id = "default"
        self._root = _PROJECT_ROOT

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
    def ingested_root(self) -> str:
        return os.path.join(self._root, "ingested")

    @property
    def reports_root(self) -> str:
        return os.path.join(self._root, "reports")

    @property
    def memory_root(self) -> str:
        return os.path.join(self._root, "memory")
