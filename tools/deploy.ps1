<#
.SYNOPSIS
  Deploys (or updates) the GuildLedger bot on the server: packs companion/ and bot/ without secrets,
  databases or logs, copies them over SSH and runs bot/deploy/setup.sh there.
.DESCRIPTION
  -FirstTime also takes your local bot setup along:
    * bot\config.toml -> /etc/guildledger/config.toml (db_path set to the server path, all else as written)
    * bot\archive.db  -> /var/lib/guildledger/guildledger.db (only if the server has no archive yet),
      so the server continues exactly where your PC stopped: nothing is posted twice.
  Stop the bot on your PC first. Without -FirstTime the server keeps its config and data (update).
  -UpdateConfig sends only bot\config.toml (e.g. after adding a collector's webhook ID); data stays.
  The server's SSH login comes from bot\config.toml, section [deploy], key ssh (git-ignored, so the address
  never lands in the repository), or from -Server.
.EXAMPLE
  .\tools\deploy.ps1 -FirstTime
  .\tools\deploy.ps1
  .\tools\deploy.ps1 -UpdateConfig
#>
param(
    [string]$Server = "",   # default: [deploy] ssh in bot\config.toml
    [switch]$FirstTime,
    [switch]$UpdateConfig,  # send bot\config.toml only (server values filled in); archive and data stay
    [switch]$DryRun    # only pack and list the files that would be sent; no connection to the server
)

$ErrorActionPreference = "Stop"
$tar = Join-Path $env:SystemRoot "System32\tar.exe"   # Windows' own tar (Git's GNU tar misreads C:\ paths)
$root = Split-Path $PSScriptRoot -Parent
$stage = Join-Path $env:TEMP "guildledger-deploy"
if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
New-Item -ItemType Directory -Force (Join-Path $stage "src") | Out-Null

function Step($msg) { Write-Host "==> $msg" -ForegroundColor Green }

try {
    Step "packing code (no config, databases, logs)"
    $skipDirs = @("__pycache__", "logs", "test2", ".pytest_cache", "build")
    $skipFiles = @("config.toml")
    $skipExt = @(".db", ".db-wal", ".db-shm", ".log", ".pyc", ".tmp", ".partial")
    foreach ($top in @("companion", "bot", "shared")) {
        $base = Join-Path $root $top
        Get-ChildItem -Path $base -Recurse -File | Where-Object {
            $rel = $_.FullName.Substring($root.Length + 1)
            $parts = $rel -split '[\\/]'
            -not ($parts | Where-Object { $skipDirs -contains $_ -or $_ -like "*.egg-info" }) -and
            -not ($skipFiles -contains $_.Name) -and
            -not ($skipExt -contains $_.Extension)
        } | ForEach-Object {
            $rel = $_.FullName.Substring($root.Length + 1)
            $dest = Join-Path (Join-Path $stage "src") $rel
            New-Item -ItemType Directory -Force (Split-Path $dest -Parent) | Out-Null
            Copy-Item $_.FullName $dest
        }
    }
    $tgz = Join-Path $stage "guildledger.tgz"
    & $tar -czf $tgz -C (Join-Path $stage "src") companion bot shared
    if ($LASTEXITCODE -ne 0) { throw "tar failed" }
    if ($DryRun) {
        & $tar -tzf $tgz | Where-Object { $_ -notmatch '/$' }
        Step "dry run: nothing sent"
        return
    }

    $toCopy = @($tgz)
    $setupArgs = ""
    if ($FirstTime -or $UpdateConfig) {
        $import = Join-Path $stage "import"
        New-Item -ItemType Directory -Force $import | Out-Null

        Step "server config from bot\config.toml"
        $cfgPath = Join-Path $root "bot\config.toml"
        if (-not (Test-Path $cfgPath)) { throw "bot\config.toml not found" }
        $cfg = [IO.File]::ReadAllText($cfgPath)
        $cfg = $cfg -replace '(?m)^db_path\s*=.*$', 'db_path = "/var/lib/guildledger/guildledger.db"'
        if ($cfg -notmatch '(?m)^db_path\s*=') { $cfg += "`n[storage]`ndb_path = `"/var/lib/guildledger/guildledger.db`"`n" }
        [IO.File]::WriteAllText((Join-Path $import "config.toml"), $cfg.Replace("`r`n", "`n"), (New-Object Text.UTF8Encoding $false))
        $toCopy += (Join-Path $import "config.toml")
        $setupArgs += " --config ~/guildledger-deploy/config.toml"

        $archive = Join-Path $root "bot\archive.db"
        if (-not $FirstTime) {
            # -UpdateConfig: never touch the server's archive
        } elseif (Test-Path $archive) {
            Step "snapshot of bot\archive.db"
            $snap = Join-Path $import "archive.db"
            python -c "import sqlite3,sys; s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close(); s.close()" $archive $snap
            if ($LASTEXITCODE -ne 0) { throw "could not snapshot bot\archive.db" }
            $toCopy += $snap
            $setupArgs += " --archive ~/guildledger-deploy/archive.db"
        } else {
            Write-Warning "bot\archive.db not found: the server starts with an empty archive"
        }
    }

    if (-not $Server) {
        $cfgFile = Join-Path $root "bot\config.toml"
        if (Test-Path $cfgFile) {
            $m = [regex]::Match([IO.File]::ReadAllText($cfgFile), '(?ms)^\[deploy\].*?^\s*ssh\s*=\s*"([^"]+)"')
            if ($m.Success) { $Server = $m.Groups[1].Value }
        }
    }
    if (-not $Server) { throw 'no server: put  [deploy]  ssh = "user@your-server"  into bot\config.toml, or pass -Server' }
    Step "copying to $Server"
    ssh $Server "rm -rf ~/guildledger-deploy && mkdir -p ~/guildledger-deploy"
    if ($LASTEXITCODE -ne 0) { throw "ssh to $Server failed" }
    scp -q @toCopy "${Server}:guildledger-deploy/"
    if ($LASTEXITCODE -ne 0) { throw "scp failed" }

    Step "running setup on the server (sudo may ask for your password)"
    $remote = "cd ~/guildledger-deploy && mkdir -p src && tar -xzf guildledger.tgz -C src && " +
              "sudo bash src/bot/deploy/setup.sh$setupArgs; rc=`$?; rm -rf ~/guildledger-deploy; exit `$rc"
    ssh -t $Server $remote
    if ($LASTEXITCODE -ne 0) { throw "setup on the server failed (see above)" }
    Step "deployed"
}
finally {
    if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }  # the staged config holds the token
}
