#!/usr/bin/env bash
# Resolve the project without changing the caller's working directory.
set -euo pipefail
whut_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)
    exec powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "$whut_root/environment/start.ps1")" "$@"
    ;;
  Linux*) exec bash "$whut_root/environment/start.sh" "$@" ;;
  *) printf '%s\n' 'Automatic runtime setup supports Windows/Linux x86-64.' >&2; exit 2 ;;
esac
