#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:-0.1.0}"

IMAGES=(
  "gnmi-client:${VERSION}"
  "ntp-server:${VERSION}"
  "ztp-server:${VERSION}"
  "tacacs:${VERSION}"
)

# Verify images exist
for img in "${IMAGES[@]}"; do
  docker image inspect "$img" >/dev/null 2>&1 || {
    echo "Missing local image: $img" >&2
    exit 1
  }
done

BUNDLE="bundle-${VERSION}"
rm -rf "$BUNDLE"
mkdir -p "$BUNDLE/services/ztp-server/ztp/tftp" "$BUNDLE/services/ztp-server/ztp/www"

echo "[*] Saving images..."
docker save -o "$BUNDLE/images-${VERSION}.tar" "${IMAGES[@]}"

echo "[*] Copying compose + env + configs..."
cp docker-compose.yml "$BUNDLE/"
[ -f .env ] && cp .env "$BUNDLE/.env"
[ -f services/ztp-server/dnsmasq.conf ] && cp services/ztp-server/dnsmasq.conf "$BUNDLE/services/ztp-server/"
[ -f services/ztp-server/nginx.conf ]   && cp services/ztp-server/nginx.conf "$BUNDLE/services/ztp-server/"
# Optional: seed ZTP content if you want to ship defaults
# cp -r services/ztp-server/ztp/tftp/* "$BUNDLE/services/ztp-server/ztp/tftp/" 2>/dev/null || true
# cp -r services/ztp-server/ztp/www/*  "$BUNDLE/services/ztp-server/ztp/www/"  2>/dev/null || true

cp scripts/load_and_up.sh "$BUNDLE/load_and_up.sh"
chmod +x "$BUNDLE/load_and_up.sh"

( cd "$BUNDLE" && sha256sum images-${VERSION}.tar docker-compose.yml 2>/dev/null > SHA256SUMS || true )

tar czf "$BUNDLE.tgz" "$BUNDLE"
echo "[✓] Created $BUNDLE.tgz"