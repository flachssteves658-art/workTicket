@echo off
echo Starting Local Frontend...

cd examples\streaming_web\frontend

if not exist node_modules (
    echo Installing dependencies...
    call npm install
)

echo Starting Vite server...
echo Access the local frontend at: http://localhost:8888
call npm run dev
