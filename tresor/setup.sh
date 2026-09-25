#!/usr/bin/env bash
# Oppretter en kryptert mappe (gocryptfs) og monterer den.
#   krypterte filer:  ~/.tresor-cipher   (det som ligger på disk og i backup)
#   klartekst-visning: ~/tresor          (finnes bare mens den er montert)
#
# Bruk:   ./setup.sh            # opprett og monter (én gang)
#         ./setup.sh --service  # installer systemd-tjeneste som monterer ved oppstart
#
# Passordet leses via en "extpass"-kommando (standard: extpass.sh ved siden av,
# som henter det fra 1Password). Kan overstyres med TRESOR_EXTPASS.
# Miljøvariabler for test: TRESOR_CIPHER, TRESOR_MOUNT.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
CIPHER="${TRESOR_CIPHER:-$HOME/.tresor-cipher}"
MNT="${TRESOR_MOUNT:-$HOME/tresor}"
EXTPASS="${TRESOR_EXTPASS:-$HERE/extpass.sh}"

command -v gocryptfs >/dev/null || { echo "Installer først:  sudo apt install gocryptfs" >&2; exit 1; }

if [ "${1:-}" = "--service" ]; then
  unit="$HOME/.config/systemd/user/tresor.service"
  mkdir -p "$(dirname "$unit")"
  cat > "$unit" <<UNIT
[Unit]
Description=Kryptert mappe (gocryptfs, passord fra passordbehandler)
After=network-online.target

[Service]
Type=simple
Environment=TRESOR_OP_REF=${TRESOR_OP_REF:-}
ExecStartPre=/usr/bin/mkdir -p $MNT
ExecStart=/usr/bin/gocryptfs -fg -nosyslog -extpass $EXTPASS $CIPHER $MNT
ExecStop=/usr/bin/fusermount3 -u $MNT
Restart=on-failure
RestartSec=30

[Install]
WantedBy=default.target
UNIT
  systemctl --user daemon-reload
  systemctl --user enable --now tresor.service
  loginctl enable-linger "$USER"   # brukertjenester starter ved oppstart uten innlogging
  echo "Tjenesten er installert. Status:  systemctl --user status tresor"
  exit 0
fi

[ -e "$CIPHER/gocryptfs.conf" ] && { echo "$CIPHER er allerede opprettet." >&2; exit 1; }
mkdir -p "$CIPHER" "$MNT"
chmod 700 "$CIPHER" "$MNT"
echo ">>> gocryptfs skriver nå ut en MASTERNØKKEL. Lagre den i passordbehandleren med en gang."
gocryptfs -init -extpass "$EXTPASS" "$CIPHER"
gocryptfs -extpass "$EXTPASS" -nosyslog "$CIPHER" "$MNT"
echo "Montert på $MNT. Lagre også en kopi av $CIPHER/gocryptfs.conf i passordbehandleren."
