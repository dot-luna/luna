#!/usr/bin/env bash
# Docker can accept TCP before Windows boots. Require an RDP connection-confirm packet.
# The caller bounds connection and read time with timeout.
set -euo pipefail

exec 3<>"/dev/tcp/127.0.0.1/${1:-3389}"
printf '\x03\x00\x00\x13\x0e\xe0\x00\x00\x00\x00\x00\x01\x00\x08\x00\x03\x00\x00\x00' >&3
header=$(dd bs=1 count=6 status=none <&3 | od -An -tx1 | tr -d ' \n')
[[ $header == 0300??????d0 ]]
