param([string]$Python = "py", [string]$WPScript = "")
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $ProjectRoot ".venv"
if ($WPScript) {
    if (-not (Test-Path -LiteralPath $WPScript -PathType Leaf)) { throw "wpscript.exe not found: $WPScript" }
    $env:WPSCRIPT_PATH = (Resolve-Path -LiteralPath $WPScript).Path
}
& $Python -m venv $Venv
if ($LASTEXITCODE -ne 0) { throw "Python virtual environment creation failed" }
$VenvPython = Join-Path $Venv "Scripts\python.exe"
& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed" }
& $VenvPython -m pip install -e $ProjectRoot
if ($LASTEXITCODE -ne 0) { throw "Package installation failed" }
& $VenvPython -m worldpainter_mcp --doctor
if ($LASTEXITCODE -ne 0) { throw "WorldPainter bridge check failed" }
& $VenvPython -m worldpainter_mcp --self-test
if ($LASTEXITCODE -ne 0) { throw "Offline checks failed" }
Write-Host "Installed. MCP command: $VenvPython -m worldpainter_mcp"
