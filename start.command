#!/bin/zsh
set -e

project_dir="${0:A:h}"
cd "$project_dir"

python_command="${PYTHON_COMMAND:-python3}"
if [[ ! -x ".venv/bin/python" ]]; then
  echo "首次启动：正在创建本地 Python 环境…"
  "$python_command" -m venv .venv
fi

if ! .venv/bin/python -c "import fastapi, uvicorn" >/dev/null 2>&1; then
  echo "正在安装本项目依赖…"
  .venv/bin/python -m pip install -r requirements.txt
fi

echo ""
echo "正在检查本地端口并启动面试答题本…"
exec .venv/bin/python run.py
