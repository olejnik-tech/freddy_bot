param(
    [string]$BravePath = "",
    [int]$Port = 9222
)

$ErrorActionPreference = "Stop"

if (-not $BravePath) {
    $candidates = @(
        "$env:ProgramFiles\BraveSoftware\Brave-Browser\Application\brave.exe",
        "${env:ProgramFiles(x86)}\BraveSoftware\Brave-Browser\Application\brave.exe",
        "$env:LOCALAPPDATA\BraveSoftware\Brave-Browser\Application\brave.exe"
    )

    $BravePath = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}

if (-not $BravePath -or -not (Test-Path $BravePath)) {
    throw "Could not find brave.exe. Pass -BravePath with the full path to Brave."
}

$profileDir = Join-Path $env:TEMP "freddy_bot_brave"

Start-Process -FilePath $BravePath -ArgumentList @(
    "--remote-debugging-port=$Port",
    "--user-data-dir=$profileDir",
    "--incognito",
    "https://www.chat-avenue.com/singles"
)

Write-Host "Started Brave with remote debugging on http://127.0.0.1:$Port"
