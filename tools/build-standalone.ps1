# 把肉段收成一个独立目录：Electron + 窗口程序 + 动画和配置。
# 播放时不再需要 DSH、Node、Python 或 8231 端口。
$ErrorActionPreference = 'Stop'
$src = 'D:\dsh-pet-kitten'
$dest = 'D:\dsh-pet-kitten\dist\肉段'
$electron = Join-Path $env:USERPROFILE '.dsh\electron'

if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
New-Item -ItemType Directory -Force -Path "$dest\app" | Out-Null
New-Item -ItemType Directory -Force -Path "$dest\pet" | Out-Null

$keep = @(
  'electron.exe', 'ffmpeg.dll', 'icudtl.dat', 'libEGL.dll', 'libGLESv2.dll',
  'd3dcompiler_47.dll', 'dxcompiler.dll', 'dxil.dll', 'vulkan-1.dll',
  'vk_swiftshader.dll', 'vk_swiftshader_icd.json',
  'resources.pak', 'chrome_100_percent.pak', 'chrome_200_percent.pak',
  'snapshot_blob.bin', 'v8_context_snapshot.bin', 'LICENSE'
)
foreach ($name in $keep) {
  Copy-Item (Join-Path $electron $name) $dest
}
Copy-Item (Join-Path $electron 'locales') "$dest\locales" -Recurse
Copy-Item (Join-Path $electron 'resources') "$dest\resources" -Recurse

Get-ChildItem "$src\runtime\electron-helper" -File | Copy-Item -Destination "$dest\app"
Copy-Item "$src\pet\kitten-config.jsonc" "$dest\pet"
Copy-Item "$src\pet\kitten-animation" "$dest\pet\kitten-animation" -Recurse

@'
@echo off
setlocal
cd /d "%~dp0"
set ELECTRON_RUN_AS_NODE=
set DSH_PET_PACK_ROOT=%~dp0
set DSH_PET_APP_NAME=rouduan
set DSH_PET_SCALE=1
start "" "%~dp0electron.exe" "%~dp0app\main.js"
'@ | Set-Content -Encoding ascii "$dest\start-rouduan.bat"

$bytes = (Get-ChildItem $dest -Recurse -File | Measure-Object Length -Sum).Sum
"built $dest"
"files $((Get-ChildItem $dest -Recurse -File).Count) size $([math]::Round($bytes/1MB,1)) MB"
