$ErrorActionPreference = 'Stop'
$workdir = 'D:\milu_publish_reverse_20260513'
$python = 'python'
$script = 'D:\milu_publish_reverse_20260513\debug_activity_hold.py'
$stdout = 'D:\milu_publish_reverse_20260513\debug\activity_hold_20260525_2302\launcher.stdout.log'
$stderr = 'D:\milu_publish_reverse_20260513\debug\activity_hold_20260525_2302\launcher.stderr.log'
New-Item -ItemType Directory -Force -Path (Split-Path $stdout) | Out-Null
$proc = Start-Process -FilePath $python -ArgumentList @($script) -WorkingDirectory $workdir -WindowStyle Normal -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
"STARTED_PID=$($proc.Id)" | Out-File -FilePath $stdout -Append -Encoding utf8
Write-Host "STARTED_PID=$($proc.Id)"
