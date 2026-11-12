#!/usr/bin/env bash
# Wrapper. The installer itself lives in the skill folder, so a skill-only install carries it.
exec bash "$(dirname "$0")/skills/tutor-any-lecture/scripts/install.sh" "$@"
