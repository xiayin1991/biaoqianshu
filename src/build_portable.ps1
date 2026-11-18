param([string]$PythonExe = 'python')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (-not (Test-Path '.venv')) {
  & $PythonExe -m venv .venv
}
$py = Join-Path $root '.venv\Scripts\python.exe'
& $py -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple
& $py -m pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

if (-not (Test-Path 'assets\tree.ico')) {
  & $py 'assets\make_icon.py'
}

& $py -m PyInstaller --noconfirm --clean --onedir --windowed --distpath 'dist-v171' --workpath 'build-v171' --specpath '.' `
  --name '标签树' `
  --icon 'assets\tree.ico' `
  --add-data 'web;web' `
  --add-data 'assets;assets' `
  main.py

$portable = Join-Path $root 'dist\标签树-Portable-v1.7.1.zip'
$portableDir = Split-Path -Parent $portable
if (-not (Test-Path -LiteralPath $portableDir)) { New-Item -ItemType Directory -Path $portableDir -Force | Out-Null }
if (Test-Path $portable) { Remove-Item -LiteralPath $portable -Force }
Compress-Archive -Path 'dist-v171\标签树\*' -DestinationPath $portable -Force
Write-Host "Portable package: $portable"




















