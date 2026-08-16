#!/usr/bin/env bash
# Installation de Carte Cameras Live sur un VPS Debian/Ubuntu vierge.
#
#   sudo bash installer-vps.sh mondomaine.fr
#
# Installe le service en role "site" : la carte, les cameras, les evenements,
# l'assistant et les dossiers d'enquete tournent 24h/24 sans GPU.
# Les traitements lourds (analyse de photo) sont delegues a ton PC via CARTE_IA_URL.
set -euo pipefail

DOMAINE="${1:-}"
APP=/opt/carte
UTILISATEUR=carte

if [[ $EUID -ne 0 ]]; then echo "A lancer en root (sudo)."; exit 1; fi
if [[ -z "$DOMAINE" ]]; then echo "Usage : sudo bash installer-vps.sh mondomaine.fr"; exit 1; fi

echo "== 1/6  Paquets systeme =="
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip curl debian-keyring debian-archive-keyring apt-transport-https

echo "== 2/6  Utilisateur dedie =="
id -u "$UTILISATEUR" &>/dev/null || useradd --system --home "$APP" --shell /usr/sbin/nologin "$UTILISATEUR"
mkdir -p "$APP"

echo "== 3/6  Dependances Python (sans PyTorch ni CUDA) =="
python3 -m venv "$APP/.venv"
"$APP/.venv/bin/pip" install --quiet --upgrade pip
"$APP/.venv/bin/pip" install --quiet opencv-python-headless yt-dlp

echo "== 4/6  Jeton d'acces =="
JETON_FICHIER="$APP/jeton.txt"
if [[ ! -f "$JETON_FICHIER" ]]; then
  head -c 24 /dev/urandom | base64 | tr -d '/+=' > "$JETON_FICHIER"
  chmod 600 "$JETON_FICHIER"
fi
JETON=$(cat "$JETON_FICHIER")

echo "== 5/6  Service systeme =="
cat > /etc/systemd/system/carte.service <<SERVICE
[Unit]
Description=Carte Cameras Live
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$UTILISATEUR
WorkingDirectory=$APP
Environment=CARTE_ROLE=site
Environment=CARTE_BIND=127.0.0.1
Environment=CARTE_TOKEN=$JETON
# Adresse de ton PC (tunnel Cloudflare ou Tailscale) pour l'analyse de photo.
# Laisser vide desactive proprement cette fonction, le reste marche.
Environment=CARTE_IA_URL=
Environment=CARTE_IA_TOKEN=$JETON
ExecStart=$APP/.venv/bin/python $APP/earthcam_live_map.py
Restart=always
RestartSec=10
# Le service n'a besoin d'ecrire que dans son dossier.
ProtectSystem=strict
ReadWritePaths=$APP
PrivateTmp=true
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
SERVICE

echo "== 6/6  Caddy (HTTPS automatique) =="
if ! command -v caddy &>/dev/null; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -qq && apt-get install -y -qq caddy
fi
cat > /etc/caddy/Caddyfile <<CADDY
$DOMAINE {
    encode zstd gzip
    # Le front est statique : Caddy le sert directement, Python n'est pas sollicite.
    handle /app.* {
        root * $APP/web
        file_server
    }
    handle {
        reverse_proxy 127.0.0.1:8770
    }
}
CADDY

chown -R "$UTILISATEUR":"$UTILISATEUR" "$APP"
systemctl daemon-reload
systemctl enable --now carte.service
systemctl reload caddy || systemctl restart caddy

echo
echo "============================================================"
echo "  Installe."
echo
echo "  Copie maintenant les fichiers du projet dans $APP :"
echo "    earthcam_live_map.py  photo_osint.py  web/  keys.json"
echo "  puis : systemctl restart carte"
echo
echo "  Adresse   : https://$DOMAINE"
echo "  Jeton     : $JETON"
echo "  Journal   : journalctl -u carte -f"
echo "============================================================"
