@echo off
setlocal
REM 把本 bat 复制到任意 docx 文件夹里，双击只预览，不改名。

set "ROOT=%CD%"
set "MINIMAX_API_KEY=sk-cp-5r5l00rWjnZ0sytIGOqk7QVOI-uark2RSetPHdvHFFgSs4oWbpyQ243Yk1BCzCX6aSLUswFaaAzXkXtXkPqv34EgUd_tZxbDmKWYRDSTlO3_f859KEuhZU8"
set "SCRIPT=D:\milu_publish_reverse_20260513\src\shorten_docx_titles.py"

python "%SCRIPT%" --root "%ROOT%" --threshold 64 --max-chars 20 --workers 8 --api-key "%MINIMAX_API_KEY%" --api-base "https://api.minimaxi.com/v1" --model "MiniMax-M3" --report "D:\milu_publish_reverse_20260513\debug\shorten_docx_titles_preview.jsonl"
pause
