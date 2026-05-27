# DeepRead 飞书 Bot 启动脚本 (Windows PowerShell)
# 用法: .\start-bot.ps1

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

$venvPath = Join-Path $ScriptDir ".venv"
$pythonExe = Join-Path $venvPath "Scripts\python.exe"

# 检查 .venv
if (-not (Test-Path $pythonExe)) {
    Write-Host ".venv 不存在，请先运行 install.ps1"
    exit 1
}

Write-Host "启动飞书 Bot 监听..."
Write-Host ""

# 启动 Bot（后台运行，自动回复）
& $pythonExe cli.py bot start --reply

# 等待一小段时间让进程启动
Start-Sleep -Seconds 2

Write-Host ""
Write-Host "--- 当前状态 ---"
& $pythonExe cli.py bot status

Write-Host ""
Write-Host "提示："
Write-Host "  - 查看实时日志: 打开 logs/feishu_bot.log"
Write-Host "  - 停止监听:     python cli.py bot stop"
Write-Host "  - 重启监听:     .\start-bot.ps1 或 python cli.py bot restart --reply"
