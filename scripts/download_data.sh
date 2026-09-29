#!/usr/bin/env sh
set -eu

project_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
raw_path="$project_root/data/raw"
archive="$raw_path/OpenStack.tar.gz"
expected_md5="66bd42c07837a094d9b0ea2d036b5713"
url="https://zenodo.org/records/3227177/files/OpenStack.tar.gz?download=1"

mkdir -p "$raw_path"
curl -fL "$url" -o "$archive"
actual_md5="$(md5sum "$archive" | awk '{print $1}')"
[ "$actual_md5" = "$expected_md5" ] || {
  echo "MD5 mismatch. Expected $expected_md5, got $actual_md5" >&2
  exit 1
}
tar -xzf "$archive" -C "$raw_path"
echo "Loghub OpenStack data downloaded and verified at $raw_path"
