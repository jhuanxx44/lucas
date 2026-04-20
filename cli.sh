#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$DIR/.venv"
REQ="$DIR/requirements.txt"

if [ ! -d "$VENV" ]; then
    echo "🔧 首次运行，创建虚拟环境..."
    python3 -m venv "$VENV"
    echo "📦 安装依赖..."
    "$VENV/bin/pip" install --quiet -r "$REQ"
    echo "✅ 环境就绪"
fi

exec "$VENV/bin/python" "$DIR/cli.py" "$@"
