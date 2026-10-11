@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 goto use_py
where python >nul 2>nul
if not errorlevel 1 goto use_python
echo Chua tim thay Python. Cai Python 3.13 tu https://www.python.org/downloads/
echo Khi cai dat, bat Add Python to PATH, sau do chay lai file nay.
pause
exit /b 1

:use_py
py -3 "%~dp0run.py" %*
goto finished

:use_python
python "%~dp0run.py" %*

:finished
if not errorlevel 1 exit /b 0
echo.
echo Khoi dong that bai. Xem thong bao loi phia tren.
pause
exit /b 1
