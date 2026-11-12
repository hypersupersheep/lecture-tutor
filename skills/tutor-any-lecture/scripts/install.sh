#!/usr/bin/env bash
# Installer for tutor-any-lecture on macOS and Linux.
# It installs the command-line tool with uv (or, without uv, into a private venv),
# records the tool's full path in <config dir>/cli-path, copies this skill folder
# to your agents and runs `tutor-any-lecture doctor --json`.
# It never downloads a script to run it; uv or pip fetch the package itself.
# Runs under bash 3.2 (the macOS system bash): no arrays, no bash 4 syntax.

set -u
unset CDPATH

usage() {
  cat <<'EOF'
Usage: bash install.sh [--dry-run] [--yes] [--agents LIST] [--from PATH|URL]

Installs the tutor-any-lecture command-line tool, records its full path in
<config dir>/cli-path, copies the skill to your agents and runs doctor.

  --dry-run         print the plan as PLAN: lines and change nothing
  --yes             never ask for confirmation
  --agents LIST     comma-separated list of claude, codex, agents
                    (default: each of them whose home folder exists)
  --from PATH|URL   what to install, passed unchanged to uv or pip
                    (default: this checkout, else the GitHub repository)
  -h, --help        show this text and exit

Exit codes: 0 ready, 1 failed or cancelled, 2 bad option, 3 needs action.
EOF
}

say() { printf '%s\n' "$1"; }
die() { printf '%s\n' "$1" >&2; exit "$2"; }

# ---- options ---------------------------------------------------------------
DRY_RUN=0
YES=0
AGENTS_SET=0
AGENTS_ARG=""
FROM=""
FROM_SET=0
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --yes) YES=1 ;;
    --agents)
      [ $# -ge 2 ] || die "install.sh: --agents needs a value: claude, codex or agents (comma-separated)" 2
      AGENTS_ARG="$2"
      AGENTS_SET=1
      shift
      ;;
    --from)
      [ $# -ge 2 ] && [ -n "$2" ] || die "install.sh: --from needs a path or URL" 2
      FROM="$2"
      FROM_SET=1
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *) die "install.sh: unknown option: $1 (see --help)" 2 ;;
  esac
  shift
done

[ -n "${HOME:-}" ] || die "install.sh: HOME is not set" 1

# ---- locate this script ----------------------------------------------------
# D is this script's folder as an absolute physical path, whatever the caller's
# current folder. Every cd happens in a subshell, so the caller's folder is kept.
D="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)" || die "install.sh: cannot find its own folder" 1
SKILL_SRC="$(cd -- "$D/.." && pwd -P)" || die "install.sh: cannot find the skill folder" 1
if [ "$FROM_SET" -eq 0 ]; then
  if [ -f "$D/../../../pyproject.toml" ]; then
    FROM="$(cd -- "$D/../../.." && pwd -P)" || die "install.sh: cannot find the repository folder" 1
  else
    FROM="git+https://github.com/hypersupersheep/tutor-any-lecture"
  fi
fi

# ---- agents ----------------------------------------------------------------
# AGENT_NAMES is a space-separated list of fixed words (no arrays, so an empty
# list is safe under set -u in bash 3.2).
AGENT_NAMES=""
add_agent() {
  case " $AGENT_NAMES " in
    *" $1 "*) ;;
    *) AGENT_NAMES="${AGENT_NAMES:+$AGENT_NAMES }$1" ;;
  esac
}
if [ "$AGENTS_SET" -eq 1 ]; then
  rest="$AGENTS_ARG,"
  while [ -n "$rest" ]; do
    name="${rest%%,*}"
    rest="${rest#*,}"
    name="${name// /}"
    case "$name" in
      claude | codex | agents) add_agent "$name" ;;
      *) die "install.sh: unknown agent name '$name' (use claude, codex or agents)" 2 ;;
    esac
  done
else
  for name in claude codex agents; do
    if [ -d "$HOME/.$name" ]; then
      add_agent "$name"
    fi
  done
fi

# ---- install method --------------------------------------------------------
METHOD=""
PY=""
if command -v uv >/dev/null 2>&1; then
  METHOD="uv"
else
  for candidate in python3.13 python3.12 python3.11 python3.10 python3 python; do
    found="$(command -v "$candidate" 2>/dev/null)" || continue
    if "$found" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >/dev/null 2>&1; then
      PY="$found"
      METHOD="venv"
      break
    fi
  done
fi
if [ -z "$METHOD" ]; then
  cat >&2 <<'EOF'
tutor-any-lecture needs uv or Python 3.10 or newer, and found neither on PATH.
Install uv with one of these commands:
  brew install uv
  pipx install uv
  winget install astral-sh.uv   (Windows)
or follow https://docs.astral.sh/uv/getting-started/installation/
Then run this installer again.
EOF
  exit 3
fi

# ---- paths (joined from the environment, never resolved) -------------------
CFG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/tutor-any-lecture"
CLI_PATH_FILE="$CFG_DIR/cli-path"
VENV="$HOME/.tutor-any-lecture/venv"
VENV_PY="$VENV/bin/python"
CLI=""

# ---- steps: each takes "plan" (print a PLAN: line) or "run" (do it) ---------
# The dry run, the confirmation prompt and the real run all go through these
# functions, so the printed plan and the real run cannot drift apart.

# Steps 1 and 2: install the CLI with uv, or into a private venv.
install_cli() {
  if [ "$METHOD" = "uv" ]; then
    if [ "$1" = "plan" ]; then
      say "PLAN: uv tool install --force $FROM"
      return 0
    fi
    uv tool install --force "$FROM" || die "install.sh: 'uv tool install --force $FROM' failed" 1
    bin_dir="$(uv tool dir --bin)" || die "install.sh: 'uv tool dir --bin' failed" 1
    CLI="$bin_dir/tutor-any-lecture"
  else
    if [ "$1" = "plan" ]; then
      say "PLAN: python -m venv $VENV"
      say "PLAN: $VENV_PY -m pip install --upgrade $FROM"
      return 0
    fi
    "$PY" -m venv "$VENV" || die "install.sh: could not create the venv at $VENV" 1
    "$VENV_PY" -m pip install --upgrade "$FROM" || die "install.sh: 'pip install --upgrade $FROM' failed" 1
    CLI="$VENV/bin/tutor-any-lecture"
  fi
}

# Step 4: record the CLI's full path in <config dir>/cli-path.
write_cli_path() {
  if [ "$1" = "plan" ]; then
    say "PLAN: write $CLI_PATH_FILE"
    return 0
  fi
  [ -f "$CLI" ] || die "install.sh: the command was not found at $CLI after the install" 1
  mkdir -p "$CFG_DIR" || die "install.sh: could not create $CFG_DIR" 1
  printf '%s\n' "$CLI" >"$CLI_PATH_FILE" || die "install.sh: could not write $CLI_PATH_FILE" 1
  say "Recorded $CLI in $CLI_PATH_FILE"
}

# True when the target exists and is physically the skill source folder.
same_as_source() {
  [ -d "$1" ] || return 1
  resolved="$(cd -- "$1" 2>/dev/null && pwd -P)" || return 1
  [ "$resolved" = "$SKILL_SRC" ]
}

# Step 5: copy the skill folder to each agent.
copy_skills() {
  if [ -z "$AGENT_NAMES" ]; then
    if [ "$1" = "plan" ]; then
      say "PLAN: skip copying skills (no agent folder found; use --agents claude,codex,agents)"
    else
      say "Note: no agent folder found (~/.claude, ~/.codex, ~/.agents), so the skill was not copied; use --agents claude,codex,agents to choose."
    fi
    return 0
  fi
  for name in $AGENT_NAMES; do
    skills_dir="$HOME/.$name/skills"
    target="$skills_dir/tutor-any-lecture"
    if same_as_source "$target"; then
      if [ "$1" = "plan" ]; then
        say "PLAN: skip $target (same folder as the skill source)"
      else
        say "skip $target (same folder as the skill source)"
      fi
      continue
    fi
    if [ "$1" = "plan" ]; then
      say "PLAN: copy $SKILL_SRC to $target"
      continue
    fi
    mkdir -p "$skills_dir" || die "install.sh: could not create $skills_dir" 1
    # Only a path named exactly <agent home>/skills/tutor-any-lecture is removed.
    # A symlink is removed as a link; what it points to is left alone.
    if [ -e "$target" ] || [ -L "$target" ]; then
      rm -rf "$target" || die "install.sh: could not remove the old copy at $target" 1
    fi
    cp -R "$SKILL_SRC" "$target" || die "install.sh: could not copy the skill to $target" 1
    say "Copied the skill to $target"
  done
}

# Step 6: doctor (planned here; run by its full path below).
plan_doctor() {
  say "PLAN: run tutor-any-lecture doctor --json"
}

print_plan() {
  install_cli plan
  write_cli_path plan
  copy_skills plan
  plan_doctor
}

# ---- dry run ---------------------------------------------------------------
if [ "$DRY_RUN" -eq 1 ]; then
  print_plan
  exit 0
fi

# ---- confirmation (only with a terminal and without --yes) -----------------
if [ "$YES" -eq 0 ] && [ -t 0 ]; then
  print_plan
  printf 'Proceed? [y/N] '
  answer=""
  read -r answer || answer=""
  case "$answer" in
    y | Y | yes | Yes | YES) ;;
    *)
      say "Nothing was changed."
      exit 1
      ;;
  esac
fi

# ---- real run --------------------------------------------------------------
install_cli run
write_cli_path run
copy_skills run
# Steps 6 and 7: run doctor by its full path; its JSON line is the last stdout
# line, and its exit code (0 ready, 3 not ready) is ours.
"$CLI" doctor --json
exit $?
