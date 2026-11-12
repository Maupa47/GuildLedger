<#
.SYNOPSIS
  Builds dist\GuildLedger-collector.zip for another officer: the addon, the companion (code only, upload
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

# Companion: package code, starter, example config switched to upload mode.
$compDst = Join-Path $stage "companion"
New-Item -ItemType Directory -Force (Join-Path $compDst "guildledger") | Out-Null
Get-ChildItem (Join-Path $root "companion\guildledger") -File -Filter *.py | Copy-Item -Destination (Join-Path $compDst "guildledger")
Copy-Item (Join-Path $root "companion\start-companion.cmd") $compDst
$example = [IO.File]::ReadAllText((Join-Path $root "companion\config.example.toml"))
$example = $example -replace '(?m)^mode = "direct"', 'mode = "upload"'
[IO.File]::WriteAllText((Join-Path $compDst "config.example.toml"), $example, (New-Object Text.UTF8Encoding $false))
Copy-Item (Join-Path $root "docs\COLLECTOR.md") $stage

$version = (Select-String -Path (Join-Path $addonSrc "GuildLedger.toc") -Pattern '^## Version:\s*(.+)$').Matches[0].Groups[1].Value.Trim()
$zip = Join-Path $dist "GuildLedger-collector-$version.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip
Remove-Item -Recurse -Force $stage
Write-Host "==> $zip"
