#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$DIR/.venv"
REQ="$DIR/requirements.txt"

if [ ! -d "$VENV" ]; then
    echo "🔧 首次运行，创建虚拟环境..."
    python3 -m venv "$VENV"
    echo "📦 安装 Python 依赖..."
    "$VENV/bin/pip" install --quiet -r "$REQ"
fi

if [ ! -d "$DIR/web/node_modules" ]; then
    echo "📦 安装前端依赖..."
    (cd "$DIR/web" && npm install)
fi

echo "🚀 启动前端 (localhost:5173) ..."
(cd "$DIR/web" && npm run dev > /dev/null 2>&1) &
PID_FRONTEND=$!

sleep 1

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 启动后端 (localhost:8000)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

cleanup() {
    echo ""
    echo "⏹ 关闭服务..."
    kill "$PID_FRONTEND" 2>/dev/null
    wait "$PID_FRONTEND" 2>/dev/null
    exit 0
}
trap cleanup INT TERM

cd "$DIR"
"$VENV/bin/uvicorn" server.app:app --host 0.0.0.0 --port 8000 --reload --log-level info
