#!/usr/bin/env python3
"""
一次性迁移脚本：把现有 wiki/、raw/、memory/ 移到 workspaces/{user_id}/ 下。

用法:
  python migrate_to_workspace.py              # 自动生成 UUID
  python migrate_to_workspace.py <user_id>    # 指定 user_id
"""
import os
import shutil
import sys
import uuid

PROJECT_ROOT = os.path.dirname(__file__)
DIRS_TO_MOVE = ["wiki", "raw", "memory"]


def main():
    user_id = sys.argv[1] if len(sys.argv) > 1 else uuid.uuid4().hex[:12]

    workspace_dir = os.path.join(PROJECT_ROOT, "workspaces", user_id)
    if os.path.exists(workspace_dir):
        print(f"错误: 目标目录已存在: {workspace_dir}")
        sys.exit(1)

    dirs_found = [d for d in DIRS_TO_MOVE if os.path.isdir(os.path.join(PROJECT_ROOT, d))]
    if not dirs_found:
        print("没有找到需要迁移的目录 (wiki/, raw/, memory/)")
        sys.exit(0)

    print(f"将迁移以下目录到 workspaces/{user_id}/:")
    for d in dirs_found:
        print(f"  {d}/")

    os.makedirs(workspace_dir, exist_ok=True)

    for d in dirs_found:
        src = os.path.join(PROJECT_ROOT, d)
        dst = os.path.join(workspace_dir, d)
        print(f"  移动 {d}/ -> workspaces/{user_id}/{d}/")
        shutil.move(src, dst)

    for d in DIRS_TO_MOVE:
        if d not in dirs_found:
            os.makedirs(os.path.join(workspace_dir, d), exist_ok=True)

    print(f"\n迁移完成。user_id: {user_id}")
    print(f"请在浏览器 console 中执行:")
    print(f'  localStorage.setItem("lucas_user_id", "{user_id}")')


if __name__ == "__main__":
    main()
