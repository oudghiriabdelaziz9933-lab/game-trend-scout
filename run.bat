@echo off
REM One-click launcher for Windows: creates the environment on first run, then starts the app.
cd /d "%~dp0"
if not exist .venv (
    echo First run: creating the Python environment, this takes a minute...
    py -m venv .venv || python -m venv .venv
    call .venv\Scripts\activate
    python -m pip install -r requirements.txt
) else (
    call .venv\Scripts\activate
)
if not exist .env copy .env.example .env >nul
REM Open the browser once the server is up
start "" cmd /c "timeout /t 6 >nul & start http://localhost:8501"
streamlit run app.py --server.headless true
pause
