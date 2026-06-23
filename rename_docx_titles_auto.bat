@echo off
setlocal
REM Copy this BAT into any folder, double-click it, and it will rename .docx filenames in that folder.
REM It only changes filenames. It does NOT modify docx content.
REM Rule: only process .docx filenames with >=64 characters. Default 8 workers.
REM Log file: rename_docx_titles.log in the same folder.

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "LOG=%ROOT%\rename_docx_titles.log"
set "MINIMAX_API_KEY=sk-cp-5r5l00rWjnZ0sytIGOqk7QVOI-uark2RSetPHdvHFFgSs4oWbpyQ243Yk1BCzCX6aSLUswFaaAzXkXtXkPqv34EgUd_tZxbDmKWYRDSTlO3_f859KEuhZU8"
set "MINIMAX_API_BASE=https://api.minimaxi.com/v1"
set "MINIMAX_MODEL=MiniMax-M3"
set "SCRIPT=D:\milu_publish_reverse_20260513\src\shorten_docx_titles.py"
set "REPORT=D:\milu_publish_reverse_20260513\debug\shorten_docx_titles_report.jsonl"

echo [%date% %time%] start root=%ROOT% > "%LOG%"
python "%SCRIPT%" --root "%ROOT%" --threshold 64 --max-chars 20 --apply --quiet --workers 8 --api-key "%MINIMAX_API_KEY%" --api-base "%MINIMAX_API_BASE%" --model "%MINIMAX_MODEL%" --report "%REPORT%" >> "%LOG%" 2>&1
set "CODE=%ERRORLEVEL%"
echo [%date% %time%] exit_code=%CODE% >> "%LOG%"
exit /b %CODE%
