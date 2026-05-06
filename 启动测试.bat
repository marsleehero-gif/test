@echo off
echo ========================================
echo   好色指数测试 - 启动脚本
echo ========================================
echo.
echo 正在安装依赖...
D:\PYTHON\python.exe -m pip install flask --quiet
echo 依赖安装完成
echo.
echo 正在启动服务...
echo 访问地址: http://localhost:5000
echo 管理面板: http://localhost:5000/admin
echo 统计 API:  http://localhost:5000/api/stats
echo.
echo 按 Ctrl+C 停止服务
echo.
D:\PYTHON\python.exe app.py
pause
