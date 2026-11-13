# Wrapper. The installer itself lives in the skill folder, so a skill-only install carries it.
# It takes the same options; see the comments at the top of that script.
[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$DryRun,
    [switch]$Yes,
    [switch]$WithAsr,
    [switch]$CliOnly,
    [string[]]$Agents,
    [string]$From,
    # Anything else is passed on, and the installer refuses it with exit code 2.
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'skills/tutor-any-lecture/scripts/install.ps1') @PSBoundParameters
exit $LASTEXITCODE
