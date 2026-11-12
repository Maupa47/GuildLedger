<#
.SYNOPSIS
  Junctions the addon folders from this repo into the WoW: Forever AddOns directory.
.EXAMPLE
  .\tools\install.ps1
  .\tools\install.ps1 -AddOnsDir "E:\Games\World of Warcraft\_forever_\Interface\AddOns"
  .\tools\install.ps1 -Remove
#>
param(
    [string]$AddOnsDir = "D:\World of Warcraft\_forever_\Interface\AddOns",
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
$repoAddons = Join-Path (Split-Path $PSScriptRoot -Parent) "addon"
$target = $AddOnsDir

if (-not (Test-Path $target)) {
    Write-Error "AddOns folder not found: $target  (pass -AddOnsDir)"
}

foreach ($dir in Get-ChildItem -Path $repoAddons -Directory) {
    $toc = Join-Path $dir.FullName "$($dir.Name).toc"
    if (-not (Test-Path $toc)) { continue }   # not an addon (e.g. tests/)
    $link = Join-Path $target $dir.Name
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
