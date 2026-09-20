#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_NAME="cgat-server"
SPEC_FILE="${SCRIPT_DIR}/cgat-server.conda-spec.txt"
OWNER_MARKER_NAME="cgat-server-owner.tsv"
STATE_MARKER_NAME="cgat-server-state.tsv"
TOOLS_REPORT_NAME="cgat-server-tools.tsv"
MARKER_SCHEMA_VERSION="1"
MICROMAMBA_URL_BASE="https://micro.mamba.pm/api/micromamba"

ENV_MANAGER=""
ENV_MANAGER_KIND=""
AUTO_INSTALLED_MICROMAMBA="false"
BOOTSTRAP_TMP_DIR=""
REQUESTED_MANAGER=""
MODE="install"
INSTALL_ENTRYPOINT="${CGAT_SERVER_INSTALL_ENTRYPOINT:-${SCRIPT_DIR}/env.sh}"
readonly -a REQUIRED_COMMANDS=(
  python
  samtools
  minimap2
  nucmer
  delta-filter
  show-coords
  meryl
  merqury.sh
  craq
  blastn
  makeblastdb
  winnowmap
  zip
  gzip
)

die() {
  echo "ERROR: $*" >&2
  exit 1
}

cleanup() {
  if [[ -n "$BOOTSTRAP_TMP_DIR" && -d "$BOOTSTRAP_TMP_DIR" ]]; then
    rm -rf -- "$BOOTSTRAP_TMP_DIR"
  fi
}
trap cleanup EXIT

usage() {
  cat <<EOF
Usage:
  bash server/install.sh [--manager mamba|micromamba|conda]
  bash server/install.sh --check [--manager mamba|micromamba|conda]

Options:
  --manager <name>  Use a specific installed environment manager.
                    If omitted, the order is mamba, micromamba, then conda.
  --check           Verify the existing managed environment without changing it.
  -h, --help        Show this help message.

Compatibility:
  bash server/env.sh accepts the same options.
EOF
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --manager)
        [[ $# -ge 2 ]] || die "--manager requires mamba, micromamba, or conda"
        REQUESTED_MANAGER="$2"
        case "$REQUESTED_MANAGER" in
          mamba|micromamba|conda) ;;
          *) die "unsupported environment manager: $REQUESTED_MANAGER" ;;
        esac
        shift 2
        ;;
      --check)
        MODE="check"
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        die "unknown argument: $1; run 'bash ${INSTALL_ENTRYPOINT} --help'"
        ;;
    esac
  done
}

sha256_file() {
  local path="$1"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$path" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$path" | awk '{print $1}'
  else
    die "sha256sum or shasum is required"
  fi
}

detect_environment_manager() {
  local candidate
  if [[ -n "$REQUESTED_MANAGER" ]]; then
    if command -v "$REQUESTED_MANAGER" >/dev/null 2>&1; then
      ENV_MANAGER="$(command -v "$REQUESTED_MANAGER")"
      ENV_MANAGER_KIND="$REQUESTED_MANAGER"
      return 0
    fi
    return 1
  fi
  for candidate in mamba micromamba conda; do
    if command -v "$candidate" >/dev/null 2>&1; then
      ENV_MANAGER="$(command -v "$candidate")"
      ENV_MANAGER_KIND="$candidate"
      return 0
    fi
  done
  return 1
}

micromamba_platform() {
  [[ "$(uname -s)" == "Linux" ]] \
    || die "automatic micromamba installation currently supports Linux only"
  case "$(uname -m)" in
    x86_64|amd64)
      printf '%s\n' "linux-64"
      ;;
    aarch64|arm64)
      printf '%s\n' "linux-aarch64"
      ;;
    ppc64le)
      printf '%s\n' "linux-ppc64le"
      ;;
    *)
      die "unsupported Linux architecture for micromamba: $(uname -m)"
      ;;
  esac
}

download_file() {
  local url="$1"
  local output_path="$2"
  if command -v curl >/dev/null 2>&1; then
    curl --fail --location --silent --show-error "$url" --output "$output_path"
  elif command -v wget >/dev/null 2>&1; then
    wget --quiet --output-document="$output_path" "$url"
  else
    die "curl or wget is required to install micromamba"
  fi
}

bootstrap_micromamba() {
  local platform
  platform="$(micromamba_platform)"
  local install_dir="${CGAT_SERVER_MICROMAMBA_INSTALL_DIR:-${HOME}/.local/bin}"
  local install_path="${install_dir}/micromamba"
  local root_prefix="${CGAT_SERVER_MICROMAMBA_ROOT_PREFIX:-${XDG_DATA_HOME:-${HOME}/.local/share}/cgat-server/micromamba}"
  local download_url="${CGAT_SERVER_MICROMAMBA_URL:-${MICROMAMBA_URL_BASE}/${platform}/latest}"

  command -v tar >/dev/null 2>&1 || die "tar is required to install micromamba"
  BOOTSTRAP_TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/cgat-server-micromamba.XXXXXX")"
  local archive_path="${BOOTSTRAP_TMP_DIR}/micromamba.tar.bz2"

  echo "No mamba, micromamba, or conda found; installing micromamba for the current user."
  download_file "$download_url" "$archive_path"
  tar -xjf "$archive_path" -C "$BOOTSTRAP_TMP_DIR" bin/micromamba
  [[ -f "${BOOTSTRAP_TMP_DIR}/bin/micromamba" ]] \
    || die "downloaded micromamba archive does not contain bin/micromamba"
  mkdir -p "$install_dir" "$root_prefix"
  cp -f "${BOOTSTRAP_TMP_DIR}/bin/micromamba" "$install_path"
  chmod +x "$install_path"

  ENV_MANAGER="$install_path"
  ENV_MANAGER_KIND="micromamba"
  AUTO_INSTALLED_MICROMAMBA="true"
  export MAMBA_ROOT_PREFIX="$root_prefix"
  "$ENV_MANAGER" shell init -s bash -r "$root_prefix"
}

channel_args() {
  printf '%s\n' -c conda-forge -c bioconda --override-channels
  if [[ "$ENV_MANAGER_KIND" == "conda" ]]; then
    printf '%s\n' --strict-channel-priority
  else
    printf '%s\n' --channel-priority strict
  fi
}

environment_exists() {
  "$ENV_MANAGER" env list \
    | awk -v target="$ENV_NAME" '$1 == target { found = 1 } END { exit !found }'
}

environment_prefix() {
  "$ENV_MANAGER" env list \
    | awk -v target="$ENV_NAME" '$1 == target { print $NF; exit }'
}

read_marker_value() {
  local marker_path="$1"
  local key="$2"
  awk -F '\t' -v key="$key" '$1 == key { print $2; exit }' "$marker_path"
}

write_owner_marker() {
  local marker_path="$1"
  local temporary_path="${marker_path}.tmp.$$"
  {
    printf 'key\tvalue\n'
    printf 'schema_version\t%s\n' "$MARKER_SCHEMA_VERSION"
    printf 'environment_name\t%s\n' "$ENV_NAME"
  } > "$temporary_path"
  mv -f "$temporary_path" "$marker_path"
}

validate_owner_marker() {
  local marker_path="$1"
  [[ -f "$marker_path" ]] \
    || die "environment '$ENV_NAME' already exists but is not managed by CGAT; refusing to modify it"
  [[ "$(read_marker_value "$marker_path" schema_version)" == "$MARKER_SCHEMA_VERSION" ]] \
    || die "environment '$ENV_NAME' has an unsupported CGAT ownership marker"
  [[ "$(read_marker_value "$marker_path" environment_name)" == "$ENV_NAME" ]] \
    || die "environment '$ENV_NAME' has an invalid CGAT ownership marker"
}

create_environment() {
  local -a channels=()
  mapfile -t channels < <(channel_args)
  echo "Creating environment '$ENV_NAME' with $ENV_MANAGER_KIND..."
  if ! "$ENV_MANAGER" create -n "$ENV_NAME" \
    "${channels[@]}" \
    --file "$SPEC_FILE" \
    -y; then
    "$ENV_MANAGER" env remove -n "$ENV_NAME" -y >/dev/null 2>&1 || true
    die "failed to create environment '$ENV_NAME'"
  fi
}

update_environment() {
  local -a channels=()
  mapfile -t channels < <(channel_args)
  echo "Updating environment '$ENV_NAME' because its dependency specification changed..."
  "$ENV_MANAGER" install -n "$ENV_NAME" \
    "${channels[@]}" \
    --file "$SPEC_FILE" \
    -y \
    || die "failed to update environment '$ENV_NAME'"
}

verify_environment() {
  local report_path="$1"
  local temporary_path="${report_path}.tmp.$$"
  if ! "$ENV_MANAGER" run -n "$ENV_NAME" python -c '
import shutil
import sys

rows = []
missing = []
for command in sys.argv[1:]:
    resolved = shutil.which(command)
    if resolved is None:
        missing.append(command)
    else:
        rows.append((command, resolved))
if missing:
    print("missing required commands: " + ", ".join(missing), file=sys.stderr)
    raise SystemExit(1)
print("command\tresolved_path")
for command, resolved in rows:
    print(f"{command}\t{resolved}")
' "${REQUIRED_COMMANDS[@]}" > "$temporary_path"; then
    rm -f "$temporary_path"
    return 1
  fi
  mv -f "$temporary_path" "$report_path"
}

write_state_marker() {
  local marker_path="$1"
  local spec_sha256="$2"
  local temporary_path="${marker_path}.tmp.$$"
  {
    printf 'key\tvalue\n'
    printf 'schema_version\t%s\n' "$MARKER_SCHEMA_VERSION"
    printf 'environment_name\t%s\n' "$ENV_NAME"
    printf 'spec_sha256\t%s\n' "$spec_sha256"
    printf 'manager\t%s\n' "$ENV_MANAGER_KIND"
    printf 'manager_path\t%s\n' "$ENV_MANAGER"
    printf 'verified_at_utc\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } > "$temporary_path"
  mv -f "$temporary_path" "$marker_path"
}

print_usage_summary() {
  local action="$1"
  local manager_command="$ENV_MANAGER_KIND"
  echo ""
  if [[ "$action" == "check" ]]; then
    echo "GPM Server environment check: READY"
  else
    echo "GPM Server installation: READY"
  fi
  echo "Environment: $ENV_NAME"
  echo "Manager:     $ENV_MANAGER_KIND ($ENV_MANAGER)"
  echo "Commands:    ${#REQUIRED_COMMANDS[@]}/${#REQUIRED_COMMANDS[@]} verified"
  if [[ "$AUTO_INSTALLED_MICROMAMBA" == "true" ]]; then
    echo "Micromamba was installed and initialized for Bash; open a new terminal before activation."
  fi
  echo "Activate:   $manager_command activate $ENV_NAME"
  echo "Deactivate: $manager_command deactivate"
  echo "Recheck:    bash $INSTALL_ENTRYPOINT --check --manager $ENV_MANAGER_KIND"
  echo "Next:       bash ${SCRIPT_DIR}/prepare.sh --help"
}

check_environment() {
  environment_exists \
    || die "environment '$ENV_NAME' does not exist for $ENV_MANAGER_KIND; run 'bash ${INSTALL_ENTRYPOINT}'"

  local prefix
  prefix="$(environment_prefix)"
  [[ -n "$prefix" ]] || die "could not resolve prefix for environment '$ENV_NAME'"

  local owner_marker="${prefix}/conda-meta/${OWNER_MARKER_NAME}"
  local state_marker="${prefix}/conda-meta/${STATE_MARKER_NAME}"
  validate_owner_marker "$owner_marker"
  [[ -f "$state_marker" ]] \
    || die "environment '$ENV_NAME' has no completed CGAT verification state; rerun the installer"

  local expected_spec_sha256
  expected_spec_sha256="$(sha256_file "$SPEC_FILE")"
  [[ "$(read_marker_value "$state_marker" spec_sha256)" == "$expected_spec_sha256" ]] \
    || die "environment '$ENV_NAME' uses an outdated dependency specification; rerun the installer"

  local check_report
  check_report="$(mktemp "${TMPDIR:-/tmp}/cgat-server-tools.XXXXXX")"
  if ! verify_environment "$check_report"; then
    rm -f "$check_report"
    die "environment '$ENV_NAME' is missing one or more required commands"
  fi
  rm -f "$check_report"
  print_usage_summary "check"
}

main() {
  parse_args "$@"
  [[ -s "$SPEC_FILE" ]] || die "dependency specification is missing or empty: $SPEC_FILE"

  if ! detect_environment_manager; then
    if [[ "$MODE" == "check" ]]; then
      if [[ -n "$REQUESTED_MANAGER" ]]; then
        die "requested environment manager is unavailable: $REQUESTED_MANAGER"
      fi
      die "no mamba, micromamba, or conda command is available"
    elif [[ -z "$REQUESTED_MANAGER" || "$REQUESTED_MANAGER" == "micromamba" ]]; then
      bootstrap_micromamba
    else
      die "requested environment manager is unavailable: $REQUESTED_MANAGER"
    fi
  fi
  echo "Using environment manager: $ENV_MANAGER_KIND ($ENV_MANAGER)"

  if [[ "$MODE" == "check" ]]; then
    check_environment
    return
  fi

  local spec_sha256
  spec_sha256="$(sha256_file "$SPEC_FILE")"
  local prefix
  local created="false"

  if environment_exists; then
    prefix="$(environment_prefix)"
    [[ -n "$prefix" ]] || die "could not resolve prefix for environment '$ENV_NAME'"
    local owner_marker="${prefix}/conda-meta/${OWNER_MARKER_NAME}"
    validate_owner_marker "$owner_marker"
    local state_marker="${prefix}/conda-meta/${STATE_MARKER_NAME}"
    local installed_spec_sha256=""
    if [[ -f "$state_marker" ]]; then
      installed_spec_sha256="$(read_marker_value "$state_marker" spec_sha256)"
    fi
    if [[ "$installed_spec_sha256" != "$spec_sha256" ]]; then
      update_environment
    else
      echo "Environment '$ENV_NAME' already matches the dependency specification."
    fi
  else
    create_environment
    created="true"
    prefix="$(environment_prefix)"
    [[ -n "$prefix" ]] || die "environment '$ENV_NAME' was created but its prefix cannot be resolved"
    mkdir -p "${prefix}/conda-meta"
    write_owner_marker "${prefix}/conda-meta/${OWNER_MARKER_NAME}"
  fi

  local state_marker="${prefix}/conda-meta/${STATE_MARKER_NAME}"
  local tools_report="${prefix}/conda-meta/${TOOLS_REPORT_NAME}"
  rm -f "$state_marker" "$tools_report"
  echo "Verifying required commands in '$ENV_NAME'..."
  if ! verify_environment "$tools_report"; then
    if [[ "$created" == "true" ]]; then
      echo "Environment creation completed, but verification failed; rerun env.sh after resolving the package issue." >&2
    fi
    die "environment '$ENV_NAME' is missing one or more required commands"
  fi
  write_state_marker "$state_marker" "$spec_sha256"
  print_usage_summary "install"
}

main "$@"
