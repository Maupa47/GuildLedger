<#
.SYNOPSIS
  Junctions the addon folders from this repo (GuildLedger, AmazingHub) into the WoW: Forever AddOns folder,
  so a /reload in game picks up every change. Finds the AddOns folder on any drive by itself.
.EXAMPLE
  .\tools\install.ps1
  .\tools\install.ps1 -AddOnsDir "E:\Games\World of Warcraft\_forever_\Interface\AddOns"
  .\tools\install.ps1 -Remove
#>
param(
    [string]$AddOnsDir = "",
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
$repoAddons = Join-Path (Split-Path $PSScriptRoot -Parent) "addon"

if (-not $AddOnsDir) {
    $tail = "World of Warcraft\_forever_\Interface\AddOns"
    $roots = Get-PSDrive -PSProvider FileSystem | ForEach-Object { $_.Root }
    $candidates = foreach ($r in $roots) {
        Join-Path $r $tail
        Join-Path $r "Program Files (x86)\$tail"
        Join-Path $r "Program Files\$tail"
        Join-Path $r "Games\$tail"
    }
    $AddOnsDir = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $AddOnsDir) { Write-Error "WoW: Forever AddOns folder not found; pass -AddOnsDir `"<path>`"" }
}
if (-not (Test-Path $AddOnsDir)) { Write-Error "AddOns folder not found: $AddOnsDir" }
Write-Host "AddOns folder: $AddOnsDir"

foreach ($dir in Get-ChildItem -Path $repoAddons -Directory) {
    $toc = Join-Path $dir.FullName "$($dir.Name).toc"
    if (-not (Test-Path $toc)) { continue }   # not an addon (e.g. tests/)
    $link = Join-Path $AddOnsDir $dir.Name
    $existing = Get-Item $link -ErrorAction SilentlyContinue

    if ($Remove) {
        if ($existing -and $existing.LinkType -eq "Junction") {
            $existing.Delete()   # removes the junction only, never the repo files
            Write-Host "removed $link"
        }
        continue
    }

    if ($existing) {
        if ($existing.LinkType -eq "Junction") { Write-Host "ok   $($dir.Name) (already linked)"; continue }
        Write-Warning "$link exists and is a real folder; leaving it alone. Delete it yourself to link."
        continue
    }
    New-Item -ItemType Junction -Path $link -Target $dir.FullName | Out-Null
    Write-Host "link $link -> $($dir.FullName)"
}
