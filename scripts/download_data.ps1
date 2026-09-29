$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$rawPath = Join-Path $projectRoot "data\raw"
$archive = Join-Path $rawPath "OpenStack.tar.gz"
$expectedMd5 = "66bd42c07837a094d9b0ea2d036b5713"
$url = "https://zenodo.org/records/3227177/files/OpenStack.tar.gz?download=1"

New-Item -ItemType Directory -Path $rawPath -Force | Out-Null
Invoke-WebRequest -Uri $url -OutFile $archive
$actualMd5 = (Get-FileHash -LiteralPath $archive -Algorithm MD5).Hash.ToLowerInvariant()
if ($actualMd5 -ne $expectedMd5) {
    throw "MD5 mismatch. Expected $expectedMd5, got $actualMd5"
}
tar -xzf $archive -C $rawPath
Write-Host "Loghub OpenStack data downloaded and verified at $rawPath"
