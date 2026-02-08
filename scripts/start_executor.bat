@echo off
REM Start ActionExecutor server for SEDT
REM Place this in shell:startup to run at login

cd /d C:\sedt
C:\Users\analyst\AppData\Local\Programs\Python\Python311\pythonw.exe C:\sedt\src\actions\action_executor.py --server --port 9999
