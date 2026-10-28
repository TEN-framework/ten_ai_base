#!/usr/bin/env bash
# ABOUTME: Applies local pyproject metadata patch required for uv-managed TEN runtime installs.
# ABOUTME: Keeps tman-installed ten_runtime_python compatible with workspace-wide uv sync.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
readonly REPO_ROOT
APP_ROOT="${TEN_RUNTIME_PYTHON_PATCH_ROOT:-${REPO_ROOT}/.ten/app}"
readonly APP_ROOT
readonly PYPROJECT_PATH="${APP_ROOT}/ten_packages/system/ten_runtime_python/pyproject.toml"

die() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

[[ -f "${PYPROJECT_PATH}" ]] || die "ten_runtime_python pyproject not found at '${PYPROJECT_PATH}'."

select_patch_path() {
  local os_name
  os_name="$(uname -s)"

  case "${os_name}" in
    Linux)
      printf '%s\n' "${SCRIPT_DIR}/ten_runtime_python_pyproject_linux.patch"
      return
      ;;
    Darwin)
      printf '%s\n' "${SCRIPT_DIR}/ten_runtime_python_pyproject_mac.patch"
      return
      ;;
    *)
      die "Unsupported host OS '${os_name}'. Expected Linux or Darwin."
      ;;
  esac
}

has_force_include_entries() {
  local os_name
  os_name="$(uname -s)"

  grep -Fxq '[tool.hatch.build.targets.wheel.force-include]' "${PYPROJECT_PATH}" \
    && grep -Fxq '"lib/libten_runtime_python.so" = "libten_runtime_python.so"' "${PYPROJECT_PATH}" \
    || return 1

  case "${os_name}" in
    Linux)
      grep -Fxq '"../ten_runtime/lib/libten_runtime.so" = "libten_runtime.so"' "${PYPROJECT_PATH}" \
        && grep -Fxq '"../ten_runtime/lib/libten_utils.so" = "libten_utils.so"' "${PYPROJECT_PATH}"
      ;;
    Darwin)
      grep -Fxq '"../ten_runtime/lib/libten_runtime.dylib" = "libten_runtime.dylib"' "${PYPROJECT_PATH}" \
        && grep -Fxq '"../ten_runtime/lib/libten_utils.dylib" = "libten_utils.dylib"' "${PYPROJECT_PATH}"
      ;;
    *)
      return 1
      ;;
  esac
}

append_force_include_entries() {
  local os_name
  os_name="$(uname -s)"

  {
    printf '\n[tool.hatch.build.targets.wheel.force-include]\n'
    printf '"lib/libten_runtime_python.so" = "libten_runtime_python.so"\n'

    case "${os_name}" in
      Linux)
        printf '"../ten_runtime/lib/libten_runtime.so" = "libten_runtime.so"\n'
        printf '"../ten_runtime/lib/libten_utils.so" = "libten_utils.so"\n'
        ;;
      Darwin)
        printf '"../ten_runtime/lib/libten_runtime.dylib" = "libten_runtime.dylib"\n'
        printf '"../ten_runtime/lib/libten_utils.dylib" = "libten_utils.dylib"\n'
        ;;
      *)
        die "Unsupported host OS '${os_name}'. Expected Linux or Darwin."
        ;;
    esac
  } >>"${PYPROJECT_PATH}"
}

[[ $# -eq 0 ]] || die "This script does not accept arguments."

PATCH_PATH="$(select_patch_path)"
readonly PATCH_PATH

[[ -f "${PATCH_PATH}" ]] || die "Patch file not found at '${PATCH_PATH}'."

if has_force_include_entries; then
  printf 'ten_runtime_python pyproject patch already applied.\n'
  exit 0
fi

if ! command -v patch >/dev/null 2>&1; then
  append_force_include_entries
  exit 0
fi

if patch --dry-run -N -p1 -d "${APP_ROOT}" <"${PATCH_PATH}" >/dev/null 2>&1; then
  patch -N -p1 -d "${APP_ROOT}" <"${PATCH_PATH}"
  exit 0
fi

die "Could not apply '${PATCH_PATH}'. ten_runtime_python/pyproject.toml may have changed."
