# Wrapper. The installer itself lives in the skill folder, so a skill-only install carries it.
param(
    [switch]$DryRun,
    [switch]$Yes,
    [string[]]$Agents,
    [string]$From
)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'skills/tutor-any-lecture/scripts/install.ps1') @PSBoundParameters
exit $LASTEXITCODE
