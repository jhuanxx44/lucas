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

PIDS=()

cleanup() {
    echo ""
    echo "⏹ 关闭服务..."
    for pid in "${PIDS[@]}"; do
        kill -TERM "$pid" 2>/dev/null && wait "$pid" 2>/dev/null
    done
    exit 0
}
trap cleanup INT TERM

echo "🚀 启动前端 (localhost:5173) ..."
(cd "$DIR/web" && exec npm run dev) > /dev/null 2>&1 &
PIDS+=($!)

echo "⏳ 等待前端就绪..."
for _ in {1..30}; do
    if curl -s -o /dev/null http://localhost:5173; then
        break
    fi
    sleep 0.5
done

if command -v open > /dev/null 2>&1; then
    open http://localhost:5173
elif command -v xdg-open > /dev/null 2>&1; then
    xdg-open http://localhost:5173
else
    echo "🔗 前端地址: http://localhost:5173"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 启动后端 (localhost:8000)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

cd "$DIR"
mkdir -p "$DIR/logs"
LOG_FILE="$DIR/logs/backend-$(date +%Y%m%d).log"
echo "📝 后端日志: $LOG_FILE"
echo ""
"$VENV/bin/uvicorn" server.app:app --host 0.0.0.0 --port 8000 --reload --log-level info 2>&1 | tee -a "$LOG_FILE"
