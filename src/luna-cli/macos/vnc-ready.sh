#!/usr/bin/env bash
# Docker can accept TCP before QEMU is ready. Require its complete RFB banner.
# The caller bounds both connect and read time with timeout.
set -euo pipefail
exec 3<>"/dev/tcp/127.0.0.1/${1:-5900}"
IFS= read -r banner <&3
[[ $banner =~ ^RFB\ 003\.(003|007|008)$ ]]
