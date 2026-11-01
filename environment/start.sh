#!/usr/bin/env bash
# Find enough Python to run bootstrap.py, without activating or editing a shell.
set -euo pipefail
whut_environment="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
whut_args=("$@")
whut_requested=''
whut_runtime="${WHUTOCEANSHIP_RUNTIME_ROOT:-}"
whut_isolated=0
whut_check=0
for ((whut_i=0; whut_i<${#whut_args[@]}; whut_i++)); do
  case "${whut_args[$whut_i]}" in
    --) break ;;
    --python)
      if ((whut_i + 1 >= ${#whut_args[@]})); then printf '%s\n' '--python requires a path.' >&2; exit 2; fi
      whut_requested="${whut_args[$((whut_i + 1))]}"
      ;;
    --python=*) whut_requested="${whut_args[$whut_i]#--python=}" ;;
    --runtime-dir)
      if ((whut_i + 1 >= ${#whut_args[@]})); then printf '%s\n' '--runtime-dir requires a path.' >&2; exit 2; fi
      whut_runtime="${whut_args[$((whut_i + 1))]}"
      ;;
    --runtime-dir=*) whut_runtime="${whut_args[$whut_i]#--runtime-dir=}" ;;
    --isolated) whut_isolated=1 ;;
    --check) whut_check=1 ;;
  esac
done
if [[ -z "$whut_requested" && "$whut_isolated" == 0 ]]; then whut_requested="${WHUTOCEANSHIP_PYTHON:-}"; fi
whut_python=''
whut_find_python() {
  local whut_candidate="$1" whut_resolved=''
  [[ -n "$whut_candidate" ]] || return 1
  if [[ -f "$whut_candidate" && -x "$whut_candidate" ]]; then whut_resolved="$whut_candidate";
  else whut_resolved="$(command -v -- "$whut_candidate" 2>/dev/null || true)"; fi
  [[ -n "$whut_resolved" ]] || return 1
  if "$whut_resolved" -c 'import sys; sys.exit(0 if sys.version_info >= (3,9) else 2)' >/dev/null 2>&1; then
    whut_python="$whut_resolved"
    return 0
  fi
  return 1
}
if [[ -n "$whut_requested" ]]; then
  if ! whut_find_python "$whut_requested"; then printf '[LLM4Ship] Requested Python cannot start: %s\n' "$whut_requested" >&2; exit 2; fi
fi
whut_cache="${WHUTOCEANSHIP_CACHE:-${XDG_CACHE_HOME:-$HOME/.cache}/WhutOceanShip-Skills}"
whut_miniforge="$whut_cache/bootstrap/miniforge3"
if [[ -z "$whut_python" ]]; then
  if [[ -n "$whut_runtime" ]]; then whut_find_python "$whut_runtime/env/bin/python" || true; fi
fi
if [[ -z "$whut_python" ]]; then
  for whut_candidate in "${CONDA_PYTHON_EXE:-}" "$whut_miniforge/bin/python" "$whut_environment/../runtime/env/bin/python" python3 python "$HOME/miniforge3/bin/python" "$HOME/miniconda3/bin/python" "$HOME/anaconda3/bin/python"; do
    if whut_find_python "$whut_candidate"; then break; fi
  done
fi
if [[ -z "$whut_python" ]]; then
  whut_conda="${CONDA_EXE:-$(command -v conda 2>/dev/null || true)}"
  if [[ -n "$whut_conda" ]]; then
    whut_conda_base="$("$whut_conda" info --base 2>/dev/null || true)"
    if [[ -n "$whut_conda_base" ]]; then whut_find_python "$whut_conda_base/bin/python" || true; fi
  fi
fi
if [[ -z "$whut_python" && "$whut_check" == 1 ]]; then
  printf '%s\n' '[LLM4Ship] No Python was found. --check never installs software. Run --setup to prepare a runtime.' >&2
  exit 2
fi
if [[ -z "$whut_python" ]]; then
  if [[ "$(uname -s)" != Linux || "$(uname -m)" != x86_64 ]]; then printf '%s\n' 'Automatic setup supports Linux x86-64.' >&2; exit 2; fi
  if [[ -e "$whut_miniforge" ]]; then printf '[LLM4Ship] Refusing to overwrite an incomplete Miniforge prefix: %s\n' "$whut_miniforge" >&2; exit 2; fi
  whut_release="$(tr -d '\r\n' < "$whut_environment/miniforge-release.txt")"
  if [[ ! "$whut_release" =~ ^[0-9]+\.[0-9]+\.[0-9]+-[0-9]+$ ]]; then printf '%s\n' 'Invalid Miniforge release.' >&2; exit 2; fi
  whut_url="https://github.com/conda-forge/miniforge/releases/download/$whut_release/Miniforge3-$whut_release-Linux-x86_64.sh"
  whut_temporary="$(mktemp -d)"
  trap 'rm -rf -- "$whut_temporary"' EXIT
  whut_download() {
    if command -v curl >/dev/null 2>&1; then curl --fail --location --retry 2 --output "$2" "$1";
    elif command -v wget >/dev/null 2>&1; then wget --output-document="$2" "$1";
    else printf '%s\n' 'Install curl or wget so the official Miniforge installer can be downloaded.' >&2; exit 2; fi
  }
  printf '[LLM4Ship] No Python found; downloading official Miniforge: %s\n' "$whut_url" >&2
  whut_download "$whut_url" "$whut_temporary/Miniforge3.sh"
  whut_download "$whut_url.sha256" "$whut_temporary/checksum.txt"
  whut_expected="$(awk 'match($0, /[a-fA-F0-9]+/) { print substr($0, RSTART, RLENGTH); exit }' "$whut_temporary/checksum.txt")"
  if [[ ! "$whut_expected" =~ ^[a-fA-F0-9]{64}$ ]]; then printf '%s\n' 'Invalid official SHA-256 checksum.' >&2; exit 2; fi
  if command -v sha256sum >/dev/null 2>&1; then whut_actual="$(sha256sum "$whut_temporary/Miniforge3.sh")";
  elif command -v shasum >/dev/null 2>&1; then whut_actual="$(shasum -a 256 "$whut_temporary/Miniforge3.sh")";
  else printf '%s\n' 'sha256sum or shasum is required to verify Miniforge.' >&2; exit 2; fi
  whut_actual="${whut_actual%% *}"
  if [[ "${whut_actual,,}" != "${whut_expected,,}" ]]; then printf '%s\n' 'Miniforge SHA-256 verification failed; installer was not executed.' >&2; exit 2; fi
  mkdir -p -- "$(dirname -- "$whut_miniforge")"
  bash "$whut_temporary/Miniforge3.sh" -b -p "$whut_miniforge"
  rm -rf -- "$whut_temporary"
  trap - EXIT
  whut_python="$whut_miniforge/bin/python"
fi
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1
unset PYTHONHOME
exec "$whut_python" "$whut_environment/bootstrap.py" "${whut_args[@]}"
