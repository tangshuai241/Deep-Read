# DeepRead 安装脚本 (Windows PowerShell)
# 用法: .\install.ps1 -Profile trial
#       .\install.ps1 -Profile personal
# 或: powershell -ExecutionPolicy Bypass -File install.ps1 -Profile trial

param(
    [ValidateSet("trial", "personal")]
    [string]$Profile = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

$profileLabel = if ($Profile) { " [$Profile]" } else { "" }
Write-Host "============================================"
Write-Host "  DeepRead 安装向导$profileLabel"
Write-Host "============================================"
Write-Host ""

# ── 1. 检查 Python ──
Write-Host "[1/5] 检查 Python ..."
try {
    $pyVersion = python --version 2>&1
    Write-Host "  $pyVersion"
} catch {
    Write-Host "  [FAIL] 未找到 Python，请先安装 Python 3.9+"
    Write-Host "  下载: https://www.python.org/downloads/"
    Write-Host "  安装时勾选 'Add Python to PATH'"
    exit 1
}

# 检查版本 >= 3.9
$verStr = (python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')") 2>&1
$verParts = $verStr -split '\.'
if ([int]$verParts[0] -lt 3 -or ([int]$verParts[0] -eq 3 -and [int]$verParts[1] -lt 9)) {
    Write-Host "  [FAIL] Python 版本过低: $verStr，需要 >= 3.9"
    exit 1
}
Write-Host "  [OK] Python $verStr"

# ── 2. 检查 pip ──
Write-Host ""
Write-Host "[2/5] 检查 pip ..."
$pipOk = python -m pip --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [FAIL] pip 不可用，请重新安装 Python 并勾选 pip"
    exit 1
}
Write-Host "  [OK] pip 可用"

# ── 3. 创建虚拟环境 ──
Write-Host ""
Write-Host "[3/5] 创建虚拟环境 ..."
$venvPath = Join-Path $ScriptDir ".venv"
if (Test-Path $venvPath) {
    Write-Host "  .venv 已存在，跳过创建"
} else {
    python -m venv $venvPath
    Write-Host "  [OK] .venv 已创建"
}

# 激活脚本路径
$activateScript = Join-Path $venvPath "Scripts\Activate.ps1"
$pipPath = Join-Path $venvPath "Scripts\pip.exe"
if (-not (Test-Path $pipPath)) {
    Write-Host "  [FAIL] .venv 创建失败，未找到 pip"
    exit 1
}

# ── 4. 安装依赖 ──
Write-Host ""
Write-Host "[4/5] 安装依赖 ..."
& $pipPath install -r requirements.txt -q 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [WARN] 部分依赖安装失败，尝试继续..."
} else {
    Write-Host "  [OK] 依赖安装完成"
}

# ── 5. 检查配置并运行 doctor ──
Write-Host ""
Write-Host "[5/5] 检查配置 ..."
$configPath = Join-Path $ScriptDir "config.yaml"
if (-not (Test-Path $configPath)) {
    Write-Host "  config.yaml 不存在，运行初始化向导..."
    Write-Host ""
    $initArgs = @()
    if ($Profile) { $initArgs += "--profile"; $initArgs += $Profile }
    & $venvPath\Scripts\python.exe init.py @initArgs
    if (-not (Test-Path $configPath)) {
        Write-Host "  [WARN] 仍未找到 config.yaml，请手动运行: python init.py"
    }
} else {
    Write-Host "  [OK] config.yaml 已存在"
}

# ── 运行 doctor ──
Write-Host ""
Write-Host "运行健康检查..."
& $venvPath\Scripts\python.exe cli.py doctor

Write-Host ""
Write-Host "============================================"
Write-Host "  安装完成！"
Write-Host "============================================"
Write-Host ""
Write-Host "下一步:"
Write-Host "  1. 编辑 config.yaml 填写 Obsidian 路径和 API Key"
Write-Host "  2. 启动 Web 控制台: .\start.ps1"
Write-Host "  3. 启动飞书 Bot:   .\start-bot.ps1"
Write-Host ""
