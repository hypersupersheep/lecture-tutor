# Installer for tutor-any-lecture on Windows.
# It installs the command-line tool with uv (or, without uv, into a private venv),
# records the tool's full path in <config dir>\cli-path, copies this skill folder
# to your agents and runs `tutor-any-lecture doctor --json`.
# It never downloads a script to run it; uv or pip fetch the package itself.
# Works in Windows PowerShell 5.1 and PowerShell 7.
#
#   -DryRun          print the plan as PLAN: lines and change nothing
#   -Yes             never ask for confirmation
#   -Agents LIST     comma-separated list of claude, codex, agents
#                    (default: each of them whose home folder exists)
#   -From PATH|URL   what to install, passed unchanged to uv or pip
#                    (default: this checkout, else the GitHub repository)
#
# Exit codes: 0 ready, 1 failed or cancelled, 2 bad agent name, 3 needs action.
param(
    [switch]$DryRun,
    [switch]$Yes,
    [string[]]$Agents,
    [string]$From
)
$ErrorActionPreference = 'Stop'

function Say([string]$Message) {
    [Console]::Out.WriteLine($Message)
}

function Fail([string]$Message, [int]$Code) {
    [Console]::Error.WriteLine($Message)
    exit $Code
}

# Run a native command with each argument passed separately; stop with exit 1
# when it fails. Native commands never stop a script on their own, so the exit
# code is checked here.
function Invoke-Native([string]$What, [string]$Exe, [string[]]$Arguments) {
    $ErrorActionPreference = 'Continue'
    & $Exe @Arguments | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Fail "install.ps1: $What failed (exit code $LASTEXITCODE)." 1
    }
}

# ---- locate this script ----------------------------------------------------
# $PSScriptRoot is this script's folder as an absolute path, whatever the
# caller's current folder. The caller's current folder is never changed.
$D = $PSScriptRoot
$SkillSrc = [System.IO.Path]::GetFullPath((Join-Path $D '..'))
if ($PSBoundParameters.ContainsKey('From')) {
    if ([string]::IsNullOrEmpty($From)) {
        Fail 'install.ps1: -From needs a path or URL.' 2
    }
} else {
    if (Test-Path -LiteralPath (Join-Path $D '..\..\..\pyproject.toml') -PathType Leaf) {
        $From = [System.IO.Path]::GetFullPath((Join-Path $D '..\..\..'))
    } else {
        $From = 'git+https://github.com/hypersupersheep/tutor-any-lecture'
    }
}

if ([string]::IsNullOrEmpty($env:USERPROFILE)) {
    Fail 'install.ps1: USERPROFILE is not set.' 1
}
$HomeDir = $env:USERPROFILE

# ---- agents ----------------------------------------------------------------
# -Agents is a string array; each element is split on ',' so that both
# `-Agents claude,codex` typed in PowerShell and the single string that
# `pwsh -File` passes work.
$AgentNames = New-Object System.Collections.Generic.List[string]
if ($PSBoundParameters.ContainsKey('Agents')) {
    foreach ($element in $Agents) {
        foreach ($part in ([string]$element).Split(',')) {
            $name = $part.Trim().ToLowerInvariant()
            if (@('claude', 'codex', 'agents') -notcontains $name) {
                Fail "install.ps1: unknown agent name '$name' (use claude, codex or agents)." 2
            }
            if (-not $AgentNames.Contains($name)) {
                $AgentNames.Add($name)
            }
        }
    }
} else {
    foreach ($name in @('claude', 'codex', 'agents')) {
        if (Test-Path -LiteralPath ($HomeDir + '\.' + $name) -PathType Container) {
            $AgentNames.Add($name)
        }
    }
}

# ---- install method --------------------------------------------------------
function Test-Python([string]$Exe, [string[]]$Prefix) {
    if (-not (Get-Command $Exe -CommandType Application -ErrorAction SilentlyContinue)) {
        return $false
    }
    $ErrorActionPreference = 'Continue'
    $probe = 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'
    & $Exe @Prefix -c $probe *> $null
    return ($LASTEXITCODE -eq 0)
}

$Method = ''
$PyExe = ''
$PyPrefix = @()
if (Get-Command 'uv' -CommandType Application -ErrorAction SilentlyContinue) {
    $Method = 'uv'
} elseif (Test-Python 'py' @('-3')) {
    $Method = 'venv'
    $PyExe = 'py'
    $PyPrefix = @('-3')
} elseif (Test-Python 'python' @()) {
    $Method = 'venv'
    $PyExe = 'python'
    $PyPrefix = @()
}
if ($Method -eq '') {
    [Console]::Error.WriteLine('tutor-any-lecture needs uv or Python 3.10 or newer, and found neither on PATH.')
    [Console]::Error.WriteLine('Install uv with one of these commands:')
    [Console]::Error.WriteLine('  winget install astral-sh.uv')
    [Console]::Error.WriteLine('  pipx install uv')
    [Console]::Error.WriteLine('  brew install uv   (macOS)')
    [Console]::Error.WriteLine('or follow https://docs.astral.sh/uv/getting-started/installation/')
    [Console]::Error.WriteLine('Then run this installer again.')
    exit 3
}

# ---- paths (joined from the environment, never resolved) -------------------
$AppData = $env:APPDATA
if ([string]::IsNullOrEmpty($AppData)) {
    $AppData = $HomeDir + '\AppData\Roaming'
}
$LocalAppData = $env:LOCALAPPDATA
if ([string]::IsNullOrEmpty($LocalAppData)) {
    $LocalAppData = $HomeDir + '\AppData\Local'
}
$CfgDir = $AppData + '\tutor-any-lecture'
$CliPathFile = $CfgDir + '\cli-path'
$Venv = $LocalAppData + '\tutor-any-lecture\venv'
$VenvPy = $Venv + '\Scripts\python.exe'
$script:Cli = ''

# ---- steps: each takes 'plan' (print a PLAN: line) or 'run' (do it) ---------
# The dry run, the confirmation prompt and the real run all go through these
# functions, so the printed plan and the real run cannot drift apart.

# Steps 1 and 2: install the CLI with uv, or into a private venv.
function Install-Cli([string]$Mode) {
    if ($Method -eq 'uv') {
        if ($Mode -eq 'plan') {
            Say "PLAN: uv tool install --force $From"
            return
        }
        Invoke-Native "'uv tool install --force $From'" 'uv' @('tool', 'install', '--force', $From)
        $ErrorActionPreference = 'Continue'
        # uv prints UTF-8; read it as UTF-8 so a non-ASCII user folder survives.
        $saved = [Console]::OutputEncoding
        try {
            try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch { }
            $binOut = & uv tool dir --bin
            $code = $LASTEXITCODE
        } finally {
            try { [Console]::OutputEncoding = $saved } catch { }
        }
        if ($code -ne 0) {
            Fail "install.ps1: 'uv tool dir --bin' failed (exit code $code)." 1
        }
        $binDir = ([string](@($binOut) | Select-Object -Last 1)).Trim()
        $script:Cli = $binDir + '\tutor-any-lecture.exe'
    } else {
        if ($Mode -eq 'plan') {
            Say "PLAN: python -m venv $Venv"
            Say "PLAN: $VenvPy -m pip install --upgrade $From"
            return
        }
        Invoke-Native "creating the venv at $Venv" $PyExe ($PyPrefix + @('-m', 'venv', $Venv))
        Invoke-Native "'pip install --upgrade $From'" $VenvPy @('-m', 'pip', 'install', '--upgrade', $From)
        $script:Cli = $Venv + '\Scripts\tutor-any-lecture.exe'
    }
}

# Step 4: record the CLI's full path in <config dir>\cli-path (UTF-8, no BOM, LF).
function Write-CliPath([string]$Mode) {
    if ($Mode -eq 'plan') {
        Say "PLAN: write $CliPathFile"
        return
    }
    if (-not (Test-Path -LiteralPath $script:Cli -PathType Leaf)) {
        Fail "install.ps1: the command was not found at $($script:Cli) after the install." 1
    }
    try {
        [void][System.IO.Directory]::CreateDirectory($CfgDir)
        [System.IO.File]::WriteAllText($CliPathFile, $script:Cli + "`n", (New-Object System.Text.UTF8Encoding($false)))
    } catch {
        Fail "install.ps1: could not write $CliPathFile." 1
    }
    Say "Recorded $($script:Cli) in $CliPathFile"
}

# The physical path of a folder: a symlink or junction is followed one level.
function Get-PhysicalPath([string]$Path) {
    $item = Get-Item -LiteralPath $Path -Force
    $resolved = $item.FullName
    if ($item.LinkType -and $item.Target) {
        $linkTarget = [string](@($item.Target)[0])
        if (-not [System.IO.Path]::IsPathRooted($linkTarget)) {
            $linkTarget = Join-Path (Split-Path -Parent $item.FullName) $linkTarget
        }
        $resolved = [System.IO.Path]::GetFullPath($linkTarget)
    }
    return $resolved.TrimEnd('\', '/')
}

# True when the target exists and is the skill source folder (letter case ignored).
function Test-SameAsSource([string]$Target) {
    if (-not (Test-Path -LiteralPath $Target -PathType Container)) {
        return $false
    }
    try {
        $physical = Get-PhysicalPath $Target
    } catch {
        return $false
    }
    return ($physical -ieq $SkillSrc.TrimEnd('\', '/'))
}

# Step 5: copy the skill folder to each agent.
function Copy-Skills([string]$Mode) {
    if ($AgentNames.Count -eq 0) {
        if ($Mode -eq 'plan') {
            Say 'PLAN: skip copying skills (no agent folder found; use -Agents claude,codex,agents)'
        } else {
            Say 'Note: no agent folder found (.claude, .codex, .agents in your user folder), so the skill was not copied; use -Agents claude,codex,agents to choose.'
        }
        return
    }
    foreach ($name in $AgentNames) {
        $skillsDir = $HomeDir + '\.' + $name + '\skills'
        $target = $skillsDir + '\tutor-any-lecture'
        if (Test-SameAsSource $target) {
            if ($Mode -eq 'plan') {
                Say "PLAN: skip $target (same folder as the skill source)"
            } else {
                Say "skip $target (same folder as the skill source)"
            }
            continue
        }
        if ($Mode -eq 'plan') {
            Say "PLAN: copy $SkillSrc to $target"
            continue
        }
        try {
            [void][System.IO.Directory]::CreateDirectory($skillsDir)
            # Only a path named exactly <agent home>\skills\tutor-any-lecture is
            # removed. A symlink or junction is removed as a link; what it points
            # to is left alone.
            $old = Get-Item -LiteralPath $target -Force -ErrorAction SilentlyContinue
            if ($old) {
                if ($old.LinkType) {
                    [System.IO.Directory]::Delete($target)
                } elseif ($old.PSIsContainer) {
                    Remove-Item -LiteralPath $target -Recurse -Force
                } else {
                    Remove-Item -LiteralPath $target -Force
                }
            }
            Copy-Item -LiteralPath $SkillSrc -Destination $target -Recurse -Force
        } catch {
            Fail "install.ps1: could not copy the skill to $target." 1
        }
        Say "Copied the skill to $target"
    }
}

function Show-Plan {
    Install-Cli 'plan'
    Write-CliPath 'plan'
    Copy-Skills 'plan'
    Say 'PLAN: run tutor-any-lecture doctor --json'
}

# ---- dry run ---------------------------------------------------------------
if ($DryRun) {
    Show-Plan
    exit 0
}

# ---- confirmation (only with a terminal and without -Yes) ------------------
if ((-not $Yes) -and (-not [Console]::IsInputRedirected)) {
    Show-Plan
    [Console]::Out.Write('Proceed? [y/N] ')
    $answer = [Console]::In.ReadLine()
    if ($null -eq $answer) {
        $answer = ''
    }
    $answer = $answer.Trim().ToLowerInvariant()
    if (($answer -ne 'y') -and ($answer -ne 'yes')) {
        Say 'Nothing was changed.'
        exit 1
    }
}

# ---- real run --------------------------------------------------------------
Install-Cli 'run'
Write-CliPath 'run'
Copy-Skills 'run'
# Steps 6 and 7: run doctor by its full path; its JSON line is the last stdout
# line, and its exit code (0 ready, 3 not ready) is ours.
$ErrorActionPreference = 'Continue'
& $script:Cli doctor --json
exit $LASTEXITCODE
