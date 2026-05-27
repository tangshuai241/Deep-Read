# DeepRead Web 控制台启动脚本 (Windows PowerShell)
# 用法: .\start.ps1

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

$venvPath = Join-Path $ScriptDir ".venv"
$activateScript = Join-Path $venvPath "Scripts\Activate.ps1"
$pythonExe = Join-Path $venvPath "Scripts\python.exe"

# 检查 .venv
if (-not (Test-Path $pythonExe)) {
    Write-Host ".venv 不存在，请先运行 install.ps1"
    exit 1
}

# 检查端口 8765 是否被占用
$portInUse = netstat -ano 2>$null | Select-String "127.0.0.1:8765"
if ($portInUse) {
    Write-Host "[WARN] 端口 8765 已被占用"
    Write-Host ""
    Write-Host $portInUse
    Write-Host ""
    Write-Host "处理建议:"
    Write-Host "  1. 如果已有一个 DeepRead Studio 在运行，直接打开 http://127.0.0.1:8765/"
    Write-Host "  2. 如果是其他程序占用，停止该程序后重试"
    Write-Host "  3. 停止占用进程: taskkill /PID <PID> /F"
    Write-Host ""
    $choice = Read-Host "是否仍要启动？(可能失败) [y/N]"
    if ($choice -notmatch '^[yY]') {
        exit 0
    }
}

Write-Host "启动 DeepRead Studio..."
Write-Host "Web 控制台: http://127.0.0.1:8765/"
Write-Host "按 Ctrl+C 停止"
Write-Host ""

# 启动 Web 服务器
& $pythonExe server.py

# 尝试自动打开浏览器
Start-Process "http://127.0.0.1:8765/" -ErrorAction SilentlyContinue
