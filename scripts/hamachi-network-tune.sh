#!/usr/bin/env bash
set -euo pipefail

IFACE="${1:-ham0}"
MTU="${2:-${HAMACHI_MTU:-1250}}"
MSS_MODE="${3:-${HAMACHI_MSS_MODE:-clamp}}"

if ! command -v ip >/dev/null 2>&1; then
  echo "ip command not found" >&2
  exit 1
fi

if ! command -v iptables >/dev/null 2>&1; then
  echo "iptables command not found" >&2
  exit 1
fi

if ! ip link show "${IFACE}" >/dev/null 2>&1; then
  echo "Interface ${IFACE} not found; skipping Hamachi tuning"
  exit 0
fi

ip link set dev "${IFACE}" mtu "${MTU}"

cleanup_chain() {
  local chain="$1"
  while IFS= read -r rule; do
    [ -n "${rule}" ] || continue
    iptables -t mangle ${rule/-A /-D }
  done < <(iptables -t mangle -S "${chain}" | grep -F -- "-o ${IFACE}" | grep -F -- "-j TCPMSS" || true)
}

for chain in OUTPUT FORWARD; do
  cleanup_chain "${chain}"
  if [ "${MSS_MODE}" = "clamp" ]; then
    iptables -t mangle -A "${chain}" -o "${IFACE}" -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu
  else
    iptables -t mangle -A "${chain}" -o "${IFACE}" -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --set-mss "${MSS_MODE}"
  fi
done

if [ "${MSS_MODE}" = "clamp" ]; then
  echo "Applied Hamachi tuning on ${IFACE}: MTU=${MTU}, MSS=clamp-to-pmtu"
else
  echo "Applied Hamachi tuning on ${IFACE}: MTU=${MTU}, MSS=${MSS_MODE}"
fi
