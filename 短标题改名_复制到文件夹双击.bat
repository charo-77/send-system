@echo off
setlocal
REM 把本 bat 复制到任意 docx 文件夹里，双击即自动重命名该 bat 所在文件夹内所有文件名 >=64 字的 docx。
REM 只改文件名，不改 docx 内容。默认 8 并发。运行日志写到同文件夹：短标题改名日志.txt

set "ROOT=%~dp0"
set "LOG=%~dp0短标题改名日志.txt"
set "MINIMAX_API_KEY=sk-cp-5r5l00rWjnZ0sytIGOqk7QVOI-uark2RSetPHdvHFFgSs4oWbpyQ243Yk1BCzCX6aSLUswFaaAzXkXtXkPqv34EgUd_tZxbDmKWYRDSTlO3_f859KEuhZU8"
set "MINIMAX_API_BASE=https://api.minimaxi.com/v1"
set "MINIMAX_MODEL=MiniMax-M3"
set "SCRIPT=D:\milu_publish_reverse_20260513\src\shorten_docx_titles.py"
set "REPORT=D:\milu_publish_reverse_20260513\debug\shorten_docx_titles_report.jsonl"

echo [%date% %time%] start root=%ROOT% > "%LOG%"
python "%SCRIPT%" --root "%ROOT%" --threshold 64 --max-chars 20 --apply --quiet --workers 8 --api-key "%MINIMAX_API_KEY%" --api-base "%MINIMAX_API_BASE%" --model "%MINIMAX_MODEL%" --report "%REPORT%" >> "%LOG%" 2>&1
echo [%date% %time%] exit_code=%ERRORLEVEL% >> "%LOG%"
exit /b %ERRORLEVEL%
