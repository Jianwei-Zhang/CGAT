#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_SCRIPT="${REPO_ROOT}/server/env.sh"
SPEC_FILE="${REPO_ROOT}/server/cgat-server.conda-spec.txt"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

FAKE_MANAGER_TEMPLATE="${TMP_DIR}/fake-manager"
cat > "$FAKE_MANAGER_TEMPLATE" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

manager_kind="$(basename "$0")"
printf '%s\t%s\n' "$manager_kind" "$*" >> "$FAKE_MANAGER_LOG"

case "${1:-}" in
  env)
    case "${2:-}" in
      list)
        printf 'Name Active Path\n'
        if [[ -f "$FAKE_ENV_STATE" ]]; then
          printf 'cgat-server %s\n' "$FAKE_ENV_PREFIX"
        fi
        ;;
      remove)
        rm -f "$FAKE_ENV_STATE"
        rm -rf -- "$FAKE_ENV_PREFIX"
        ;;
      *)
        exit 2
        ;;
    esac
    ;;
  create)
    if [[ "${FAKE_CREATE_FAIL:-false}" == "true" ]]; then
      exit 9
    fi
    mkdir -p "${FAKE_ENV_PREFIX}/conda-meta"
    : > "$FAKE_ENV_STATE"
    ;;
  install)
    if [[ "${FAKE_INSTALL_FAIL:-false}" == "true" ]]; then
      exit 10
    fi
    ;;
  run)
    if [[ "${FAKE_VERIFY_FAIL:-false}" == "true" ]]; then
      echo 'missing required commands: craq' >&2
      exit 11
    fi
    printf 'command\tresolved_path\n'
    printf 'python\t%s/bin/python\n' "$FAKE_ENV_PREFIX"
    ;;
  shell)
    [[ "${2:-}" == "init" ]] || exit 2
    : > "$FAKE_SHELL_INIT_STATE"
    ;;
  *)
    exit 2
    ;;
esac
EOF
chmod +x "$FAKE_MANAGER_TEMPLATE"

copy_installer() {
  local case_dir="$1"
  mkdir -p "${case_dir}/server"
  cp "$ENV_SCRIPT" "${case_dir}/server/env.sh"
  cp "$SPEC_FILE" "${case_dir}/server/cgat-server.conda-spec.txt"
}

install_fake_managers() {
  local bin_dir="$1"
  shift
  mkdir -p "$bin_dir"
  local manager
  for manager in "$@"; do
    cp "$FAKE_MANAGER_TEMPLATE" "${bin_dir}/${manager}"
    chmod +x "${bin_dir}/${manager}"
  done
}

run_installer() {
  local case_dir="$1"
  local bin_dir="$2"
  shift 2
  PATH="${bin_dir}:/usr/bin:/bin" \
    HOME="${case_dir}/home" \
    FAKE_MANAGER_LOG="${case_dir}/manager.log" \
    FAKE_ENV_STATE="${case_dir}/environment.exists" \
    FAKE_ENV_PREFIX="${case_dir}/environment" \
    FAKE_SHELL_INIT_STATE="${case_dir}/shell-init.called" \
    "$@" \
    bash "${case_dir}/server/env.sh"
}

assert_file() {
  local path="$1"
  [[ -f "$path" ]] || {
    echo "expected file: $path" >&2
    exit 1
  }
}

assert_not_file() {
  local path="$1"
  [[ ! -e "$path" ]] || {
    echo "unexpected file: $path" >&2
    exit 1
  }
}

test_existing_manager_priority_create_reuse_and_update() {
  local case_dir="${TMP_DIR}/existing-manager"
  local bin_dir="${case_dir}/bin"
  copy_installer "$case_dir"
  install_fake_managers "$bin_dir" mamba micromamba conda
  mkdir -p "${case_dir}/home"

  run_installer "$case_dir" "$bin_dir" > "${case_dir}/first.out"
  grep -F $'mamba\tcreate -n cgat-server' "${case_dir}/manager.log" >/dev/null
  grep -F -- '-c conda-forge -c bioconda --override-channels --channel-priority strict' \
    "${case_dir}/manager.log" >/dev/null
  grep -F 'Activate:   mamba activate cgat-server' "${case_dir}/first.out" >/dev/null
  grep -F 'Deactivate: mamba deactivate' "${case_dir}/first.out" >/dev/null
  if grep -F $'\tactivate ' "${case_dir}/manager.log" >/dev/null; then
    echo "env.sh must not activate the environment" >&2
    exit 1
  fi

  local conda_meta="${case_dir}/environment/conda-meta"
  assert_file "${conda_meta}/cgat-server-owner.tsv"
  assert_file "${conda_meta}/cgat-server-state.tsv"
  assert_file "${conda_meta}/cgat-server-tools.tsv"
  local initial_hash
  initial_hash="$(awk -F '\t' '$1 == "spec_sha256" { print $2 }' "${conda_meta}/cgat-server-state.tsv")"

  run_installer "$case_dir" "$bin_dir" > "${case_dir}/second.out"
  [[ "$(grep -c $'mamba\tcreate ' "${case_dir}/manager.log")" -eq 1 ]]
  [[ "$(grep -c $'mamba\tinstall ' "${case_dir}/manager.log" || true)" -eq 0 ]]
  grep -F "already matches the dependency specification" "${case_dir}/second.out" >/dev/null

  printf 'bc\n' >> "${case_dir}/server/cgat-server.conda-spec.txt"
  run_installer "$case_dir" "$bin_dir" > "${case_dir}/update.out"
  [[ "$(grep -c $'mamba\tinstall -n cgat-server' "${case_dir}/manager.log")" -eq 1 ]]
  local updated_hash
  updated_hash="$(awk -F '\t' '$1 == "spec_sha256" { print $2 }' "${conda_meta}/cgat-server-state.tsv")"
  [[ -n "$updated_hash" && "$updated_hash" != "$initial_hash" ]]
}

test_conda_uses_strict_channel_priority() {
  local case_dir="${TMP_DIR}/conda-manager"
  local bin_dir="${case_dir}/bin"
  copy_installer "$case_dir"
  install_fake_managers "$bin_dir" conda
  mkdir -p "${case_dir}/home"

  run_installer "$case_dir" "$bin_dir" > "${case_dir}/output"
  grep -F $'conda\tcreate -n cgat-server' "${case_dir}/manager.log" >/dev/null
  grep -F -- '--override-channels --strict-channel-priority' "${case_dir}/manager.log" >/dev/null
  if grep -F -- '--channel-priority strict' "${case_dir}/manager.log" >/dev/null; then
    echo "conda must use --strict-channel-priority syntax" >&2
    exit 1
  fi
}

test_unmanaged_environment_is_rejected() {
  local case_dir="${TMP_DIR}/unmanaged-environment"
  local bin_dir="${case_dir}/bin"
  copy_installer "$case_dir"
  install_fake_managers "$bin_dir" micromamba
  mkdir -p "${case_dir}/home" "${case_dir}/environment/conda-meta"
  : > "${case_dir}/environment.exists"

  if run_installer "$case_dir" "$bin_dir" > "${case_dir}/output" 2> "${case_dir}/error"; then
    echo "expected unmanaged cgat-server environment to be rejected" >&2
    exit 1
  fi
  grep -F "already exists but is not managed by CGAT" "${case_dir}/error" >/dev/null
  if grep -E $'\t(create|install) ' "${case_dir}/manager.log" >/dev/null; then
    echo "unmanaged environment must not be modified" >&2
    exit 1
  fi
}

test_verification_failure_has_no_ready_state_and_can_recover() {
  local case_dir="${TMP_DIR}/verification-failure"
  local bin_dir="${case_dir}/bin"
  copy_installer "$case_dir"
  install_fake_managers "$bin_dir" micromamba
  mkdir -p "${case_dir}/home"

  if run_installer "$case_dir" "$bin_dir" env FAKE_VERIFY_FAIL=true \
    > "${case_dir}/output" 2> "${case_dir}/error"; then
    echo "expected environment verification to fail" >&2
    exit 1
  fi
  local conda_meta="${case_dir}/environment/conda-meta"
  assert_file "${conda_meta}/cgat-server-owner.tsv"
  assert_not_file "${conda_meta}/cgat-server-state.tsv"
  assert_not_file "${conda_meta}/cgat-server-tools.tsv"
  grep -F "missing one or more required commands" "${case_dir}/error" >/dev/null

  run_installer "$case_dir" "$bin_dir" > "${case_dir}/recovered.out"
  assert_file "${conda_meta}/cgat-server-state.tsv"
  assert_file "${conda_meta}/cgat-server-tools.tsv"
  grep -F $'micromamba\tinstall -n cgat-server' "${case_dir}/manager.log" >/dev/null
}

test_no_manager_bootstraps_micromamba_for_current_user() {
  local case_dir="${TMP_DIR}/bootstrap-micromamba"
  local bin_dir="${case_dir}/restricted-bin"
  copy_installer "$case_dir"
  mkdir -p "$bin_dir" "${case_dir}/home"

  local command_name
  for command_name in awk bash basename chmod cp date dirname mkdir mktemp mv rm sha256sum uname; do
    ln -s "$(command -v "$command_name")" "${bin_dir}/${command_name}"
  done

  cat > "${bin_dir}/curl" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
output_path=""
while [[ $# -gt 0 ]]; do
  if [[ "$1" == "--output" ]]; then
    output_path="$2"
    shift 2
  else
    shift
  fi
done
[[ -n "$output_path" ]]
: > "$output_path"
EOF

  cat > "${bin_dir}/tar" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
destination=""
while [[ $# -gt 0 ]]; do
  if [[ "$1" == "-C" ]]; then
    destination="$2"
    shift 2
  else
    shift
  fi
done
[[ -n "$destination" ]]
mkdir -p "${destination}/bin"
cp "$FAKE_MANAGER_TEMPLATE" "${destination}/bin/micromamba"
chmod +x "${destination}/bin/micromamba"
EOF
  chmod +x "${bin_dir}/curl" "${bin_dir}/tar"

  PATH="$bin_dir" \
    HOME="${case_dir}/home" \
    XDG_DATA_HOME="${case_dir}/xdg-data" \
    FAKE_MANAGER_TEMPLATE="$FAKE_MANAGER_TEMPLATE" \
    FAKE_MANAGER_LOG="${case_dir}/manager.log" \
    FAKE_ENV_STATE="${case_dir}/environment.exists" \
    FAKE_ENV_PREFIX="${case_dir}/environment" \
    FAKE_SHELL_INIT_STATE="${case_dir}/shell-init.called" \
    /bin/bash "${case_dir}/server/env.sh" > "${case_dir}/output"

  assert_file "${case_dir}/home/.local/bin/micromamba"
  assert_file "${case_dir}/shell-init.called"
  assert_file "${case_dir}/environment/conda-meta/cgat-server-state.tsv"
  grep -F $'micromamba\tshell init -s bash -r ' "${case_dir}/manager.log" >/dev/null
  grep -F 'No mamba, micromamba, or conda found' "${case_dir}/output" >/dev/null
  grep -F 'open a new terminal before activation' "${case_dir}/output" >/dev/null
  grep -F 'Activate:   micromamba activate cgat-server' "${case_dir}/output" >/dev/null
}

test_dependency_spec_and_verifier_cover_server_commands() {
  local package_spec
  for package_spec in \
    python=3.11.14 \
    samtools=1.23.1 \
    minimap2=2.31 \
    mummer4=4.0.1 \
    meryl=1.4.1 \
    merqury=1.4.1 \
    craq=1.10 \
    blast=2.17.0 \
    winnowmap=2.03 \
    zip \
    gzip
  do
    grep -Fx "$package_spec" "$SPEC_FILE" >/dev/null
  done

  local command_name
  for command_name in \
    python samtools minimap2 nucmer delta-filter show-coords meryl merqury.sh \
    craq blastn makeblastdb winnowmap zip gzip
  do
    grep -F "    ${command_name}" "$ENV_SCRIPT" >/dev/null
  done
}

test_arguments_are_rejected() {
  local case_dir="${TMP_DIR}/arguments-rejected"
  copy_installer "$case_dir"
  mkdir -p "${case_dir}/home"
  if HOME="${case_dir}/home" bash "${case_dir}/server/env.sh" run \
    > "${case_dir}/output" 2> "${case_dir}/error"; then
    echo "expected env.sh arguments to be rejected" >&2
    exit 1
  fi
  grep -F "does not accept arguments; run it without arguments" "${case_dir}/error" >/dev/null
}

test_existing_manager_priority_create_reuse_and_update
test_conda_uses_strict_channel_priority
test_unmanaged_environment_is_rejected
test_verification_failure_has_no_ready_state_and_can_recover
test_no_manager_bootstraps_micromamba_for_current_user
test_dependency_spec_and_verifier_cover_server_commands
test_arguments_are_rejected

echo "gpm_server_env_test.sh: ok"
