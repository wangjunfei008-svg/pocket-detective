#!/usr/bin/env bash
# 口袋小神探：梧桐小学的消失金蛋 —— 本地一键启动（macOS / Linux）

cd "$(dirname "$0")" || exit 1

PORT="${PORT:-8501}"
HOST="${HOST:-127.0.0.1}"
PYTHON="${PYTHON:-python3}"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "❌ 没有找到 python3，请先安装 Python 3.9+"
  exit 1
fi

echo "🕵️  口袋小神探 · 正在检查依赖…"
if ! "$PYTHON" -c "import streamlit, requests, openai" >/dev/null 2>&1; then
  echo "📦 首次运行，正在安装依赖（streamlit / requests / openai）…"
  "$PYTHON" -m pip install -r requirements.txt || {
    echo "❌ 依赖安装失败，请检查网络或改用：$PYTHON -m venv .venv && source .venv/bin/activate"
    exit 1
  }
fi

echo ""
echo "🎉 启动成功！请用浏览器打开： http://${HOST}:${PORT}"
echo "   · 未配置任何 Key 也能完整通关（自动进入内置童趣 Mock 剧本）"
echo "   · DGX Spark 本地推理：先启动 OpenAI 兼容服务，再在侧边栏选「DGX Spark 本地端侧推理」"
echo "   · 想让教室里的平板也能访问：HOST=0.0.0.0 ./run.sh"
echo "   · 跑单元测试： $PYTHON -m pytest tests -q"
echo ""

exec "$PYTHON" -m streamlit run app.py \
  --server.port "$PORT" \
  --server.address "$HOST" \
  --browser.gatherUsageStats false
