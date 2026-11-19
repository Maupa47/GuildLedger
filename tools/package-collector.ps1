<#
.SYNOPSIS
  Builds the two packages in dist\ (version from addon\GuildLedger\GuildLedger.toc):

  Amazing-Forever-Guild-Pack-<v>.zip   for CurseForge and every player (docs\addon\CURSEFORGE.md):
      GuildLedger\  (Lua, TOC, README.md, LICENSE.txt)
      AmazingHub\   (built by tools\rebrand-hub.py, without its test scripts; THIRD_PARTY.md)
      No programs, no settings, no data.

  GuildLedger-collector-<v>.zip        for an officer who collects (companion\COLLECTOR.md); for setting one up by hand:
      GuildLedger\, AmazingHub\   the same addon folders
      companion\                  the program (code only), starters, config.example.toml, COLLECTOR.md (no secrets)
      Send the officer this zip, and separately and privately their own #gl-ingest webhook URL.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\tools\package-collector.ps1
#>
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$stage = Join-Path $env:TEMP "guildledger-package"
$dist = Join-Path $root "dist"
if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
New-Item -ItemType Directory -Force $stage, $dist | Out-Null

# Zip with forward slashes in entry names (the zip standard). Compress-Archive in Windows PowerShell 5.1
# writes backslashes, which some unzip tools and upload checks misread. $folders sit at the top of the zip.
Add-Type -AssemblyName System.IO.Compression, System.IO.Compression.FileSystem
function New-Zip($zipPath, $folders) {
    if (Test-Path $zipPath) { Remove-Item $zipPath }
    $zip = [IO.Compression.ZipFile]::Open($zipPath, [IO.Compression.ZipArchiveMode]::Create)
    try {
        foreach ($f in $folders) {
            $item = Get-Item $f
            $base = (Split-Path $item.FullName -Parent).TrimEnd('\') + '\'
            $files = if ($item.PSIsContainer) { Get-ChildItem $item.FullName -Recurse -File } else { @($item) }
            foreach ($file in $files) {
                $name = $file.FullName.Substring($base.Length).Replace('\', '/')
                [void][IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $file.FullName, $name,
                    [IO.Compression.CompressionLevel]::Optimal)
            }
        }
    } finally { $zip.Dispose() }
}

$addonSrc = Join-Path $root "addon\GuildLedger"
$version = (Select-String -Path (Join-Path $addonSrc "GuildLedger.toc") -Pattern '^## Version:\s*(.+)$').Matches[0].Groups[1].Value.Trim()

# --- addon folders (shared by both packages) ---------------------------------------------------------------
$addonDst = Join-Path $stage "GuildLedger"
New-Item -ItemType Directory -Force $addonDst | Out-Null
Get-ChildItem $addonSrc -File | Where-Object { $_.Extension -in ".toc", ".lua" } | Copy-Item -Destination $addonDst
Copy-Item (Join-Path $root "docs\addon\README.md") (Join-Path $addonDst "README.md")
Copy-Item (Join-Path $root "LICENSE") (Join-Path $addonDst "LICENSE.txt")

$hubDst = Join-Path $stage "AmazingHub"
New-Item -ItemType Directory -Force $hubDst | Out-Null
Get-ChildItem (Join-Path $root "addon\AmazingHub") | Where-Object { $_.Name -ne "tools" } |
    Copy-Item -Destination $hubDst -Recurse
Copy-Item (Join-Path $root "THIRD_PARTY.md") (Join-Path $hubDst "THIRD_PARTY.md")

# --- player package (CurseForge) ---------------------------------------------------------------------------
$packZip = Join-Path $dist "Amazing-Forever-Guild-Pack-$version.zip"
New-Zip $packZip @($addonDst, $hubDst)
Write-Host "==> $packZip   (CurseForge / players)"

# --- collector package -------------------------------------------------------------------------------------
$compDst = Join-Path $stage "companion"
New-Item -ItemType Directory -Force (Join-Path $compDst "guildledger") | Out-Null
Get-ChildItem (Join-Path $root "companion\guildledger") -File -Filter *.py |
    Copy-Item -Destination (Join-Path $compDst "guildledger")
foreach ($f in "start-companion.cmd", "autostart-on.cmd", "autostart-off.cmd", "config.example.toml", "COLLECTOR.md") {
    Copy-Item (Join-Path $root "companion\$f") $compDst
}

$collZip = Join-Path $dist "GuildLedger-collector-$version.zip"
New-Zip $collZip @(Get-ChildItem $stage | ForEach-Object FullName)
Remove-Item -Recurse -Force $stage
Write-Host "==> $collZip   (officers only; never upload this one)"
