<#
.SYNOPSIS
  Builds dist\GuildLedger-collector-<v>.zip for another officer and dist\GuildLedger-<v>.zip
  (addon only, for CurseForge and members; see docs/CURSEFORGE.md). The collector zip: the addon, the companion (code only, upload
  mode preset, no config, no data) and COLLECTOR.md. Send the zip and, separately and privately, the
  officer's own #gl-ingest webhook URL.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\tools\package-collector.ps1
#>
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$stage = Join-Path $env:TEMP "guildledger-collector"
$dist = Join-Path $root "dist"
if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
New-Item -ItemType Directory -Force $stage, $dist | Out-Null

# Addon: exactly the files the TOC loads, plus the TOC.
$addonSrc = Join-Path $root "addon\GuildLedger"
$addonDst = Join-Path $stage "GuildLedger"
New-Item -ItemType Directory -Force $addonDst | Out-Null
Get-ChildItem $addonSrc -File | Where-Object { $_.Extension -in ".toc", ".lua" } | Copy-Item -Destination $addonDst

# Amazing Hub (built by tools/rebrand-hub.py): the whole folder except GuildOS's test scripts (tools\).
$hubSrc = Join-Path $root "addon\AmazingHub"
$hubDst = Join-Path $stage "AmazingHub"
New-Item -ItemType Directory -Force $hubDst | Out-Null
Get-ChildItem $hubSrc | Where-Object { $_.Name -ne "tools" } | Copy-Item -Destination $hubDst -Recurse

# Companion: package code, starter, example config switched to upload mode.
$compDst = Join-Path $stage "companion"
New-Item -ItemType Directory -Force (Join-Path $compDst "guildledger") | Out-Null
Get-ChildItem (Join-Path $root "companion\guildledger") -File -Filter *.py | Copy-Item -Destination (Join-Path $compDst "guildledger")
Copy-Item (Join-Path $root "companion\start-companion.cmd") $compDst
Copy-Item (Join-Path $root "companion\autostart-on.cmd"), (Join-Path $root "companion\autostart-off.cmd") $compDst
$example = [IO.File]::ReadAllText((Join-Path $root "companion\config.example.toml"))
$example = $example -replace '(?m)^mode = "direct"', 'mode = "upload"'
[IO.File]::WriteAllText((Join-Path $compDst "config.example.toml"), $example, (New-Object Text.UTF8Encoding $false))
Copy-Item (Join-Path $root "docs\COLLECTOR.md") $stage

$version = (Select-String -Path (Join-Path $addonSrc "GuildLedger.toc") -Pattern '^## Version:\s*(.+)$').Matches[0].Groups[1].Value.Trim()
$zip = Join-Path $dist "GuildLedger-collector-$version.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip
Write-Host "==> $zip"

# Addon package for CurseForge and for members: both addon folders with README.md, nothing else (no programs).
$addonZip = Join-Path $dist "Amazing-Forever-Guild-Pack-$version.zip"
if (Test-Path $addonZip) { Remove-Item $addonZip }
Copy-Item (Join-Path $root "docs\ADDON_README.md") (Join-Path $addonDst "README.md")
Copy-Item (Join-Path $root "LICENSE") (Join-Path $addonDst "LICENSE.txt")
Copy-Item (Join-Path $root "THIRD_PARTY.md") (Join-Path $hubDst "THIRD_PARTY.md")
Compress-Archive -Path $addonDst, $hubDst -DestinationPath $addonZip
Remove-Item -Recurse -Force $stage
Write-Host "==> $addonZip   (CurseForge / members)"
