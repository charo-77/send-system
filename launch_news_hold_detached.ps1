$ErrorActionPreference = 'Stop'
$workdir = 'D:\milu_publish_reverse_20260513'
$python = 'python'
$script = 'D:\milu_publish_reverse_20260513\debug_news_hold.py'
$stdout = 'D:\milu_publish_reverse_20260513\debug\news_hold_20260525_2325\launcher.stdout.log'
$stderr = 'D:\milu_publish_reverse_20260513\debug\news_hold_20260525_2325\launcher.stderr.log'
New-Item -ItemType Directory -Force -Path (Split-Path $stdout) | Out-Null
Start-Process -FilePath $python -ArgumentList @($script) -WorkingDirectory $workdir -WindowStyle Normal -RedirectStandardOutput $stdout -RedirectStandardError $stderr
Write-Host 'DETACHED_STARTED'
