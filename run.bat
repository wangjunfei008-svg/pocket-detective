@echo off
chcp 65001 >nul
REM ============================================================
REM  口袋小神探：梧桐小学的消失金蛋 - Windows 一键启动
REM  双击本文件即可开始游戏（首次运行会自动安装依赖）
REM ============================================================

cd /d "%~dp0"

if "%PORT%"=="" set PORT=8501
if "%HOST%"=="" set HOST=127.0.0.1

where python >nul 2>nul
if errorlevel 1 (
  echo [X] 没有检测到 Python，请先安装 Python 3.9 以上
  echo     下载地址： https://www.python.org/downloads/
  echo     安装时记得勾选 "Add Python to PATH"
  pause
  exit /b 1
)

echo [1/2] 正在检查依赖...
python -c "import streamlit, requests, openai" >nul 2>nul
if errorlevel 1 (
  echo     首次运行，正在安装 streamlit / requests / openai ...
  python -m pip install -r requirements.txt
  if errorlevel 1 (
    echo [X] 依赖安装失败，请检查网络后重试
    pause
    exit /b 1
  )
)

echo.
echo [2/2] 启动成功！请用浏览器打开： http://%HOST%:%PORT%
echo       - 不填任何 API Key 也能完整通关（自动使用内置童趣剧本）
echo       - DGX Spark 本地推理：先启动本地服务，再在左侧栏选择算力模式
echo       - 教室平板访问： set HOST=0.0.0.0 ^&^& run.bat
echo       - 关闭游戏：在本窗口按 Ctrl+C
echo.

python -m streamlit run app.py --server.port %PORT% --server.address %HOST% --browser.gatherUsageStats false

pause
