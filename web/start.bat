@echo off
echo ==========================================
echo   Proxy Checker Pro - Web
echo ==========================================
echo.

echo [1/2] Backend (FastAPI)...
cd /d "%~dp0backend"
start "ProxyChecker-Backend" cmd /k "pip install -r requirements.txt && python -m uvicorn main:app --port 8000"

echo [2/2] Frontend (React + Vite)...
cd /d "%~dp0frontend"
start "ProxyChecker-Frontend" cmd /k "npm install && npm run dev"

echo.
echo  Frontend (dev):  http://localhost:5174
echo  App (build):     http://localhost:8000
echo  Para produccion: cd frontend ^&^& npm run build  (luego abre http://localhost:8000)
echo ==========================================
pause
