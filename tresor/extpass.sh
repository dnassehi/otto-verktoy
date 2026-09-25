#!/usr/bin/env bash
# Skriver tresor-passordet til stdout (brukes som -extpass for gocryptfs).
# Passordet hentes fra 1Password og skrives aldri til disk.
#
# Krever:  TRESOR_OP_REF  (f.eks. "op://Assistent/Tresor gocryptfs/password")
# Token:   miljøvariabelen OP_SERVICE_ACCOUNT_TOKEN, eller en fil (rettigheter 600)
#          angitt i TRESOR_OP_TOKEN_FILE (standard ~/.config/op/service-account-token)
set -euo pipefail
: "${TRESOR_OP_REF:?sett TRESOR_OP_REF, f.eks. op://Assistent/Tresor gocryptfs/password}"
if [ -z "${OP_SERVICE_ACCOUNT_TOKEN:-}" ]; then
  f="${TRESOR_OP_TOKEN_FILE:-$HOME/.config/op/service-account-token}"
  [ -r "$f" ] || { echo "finner ikke token-fil $f" >&2; exit 1; }
  OP_SERVICE_ACCOUNT_TOKEN="$(cat "$f")"
  export OP_SERVICE_ACCOUNT_TOKEN
fi
exec op read --no-newline "$TRESOR_OP_REF"
