@echo off
setlocal
REM 用法1：把这个 bat 复制到某个 docx 文件夹里，双击运行 = 预览当前文件夹
REM 用法2：把文件夹拖到这个 bat 上 = 预览拖入文件夹
REM 用法3：命令行加 apply = 真正改名
REM 注意：只改 docx 文件名，不改 docx 内容。只处理文件名字符数 >=64 的 docx。

set "ROOT=%~1"
if "%ROOT%"=="" set "ROOT=%CD%"

set "APPLY_FLAG="
if /I "%~2"=="apply" set "APPLY_FLAG=--apply"
if /I "%~1"=="apply" (
  set "ROOT=%CD%"
  set "APPLY_FLAG=--apply"
)

set "MINIMAX_API_KEY=sk-cp-5r5l00rWjnZ0sytIGOqk7QVOI-uark2RSetPHdvHFFgSs4oWbpyQ243Yk1BCzCX6aSLUswFaaAzXkXtXkPqv34EgUd_tZxbDmKWYRDSTlO3_f859KEuhZU8"
set "MINIMAX_API_BASE=https://api.minimaxi.com/v1"
set "MINIMAX_MODEL=MiniMax-M3"

python "%~dp0src\shorten_docx_titles.py" --root "%ROOT%" --threshold 64 --max-chars 20 %APPLY_FLAG% --api-key "%MINIMAX_API_KEY%" --api-base "%MINIMAX_API_BASE%" --model "%MINIMAX_MODEL%" --report "%~dp0debug\shorten_docx_titles_report.jsonl"
pause
