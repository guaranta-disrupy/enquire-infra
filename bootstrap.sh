#!/usr/bin/env bash
# bootstrap.sh — clona os 5 repos de serviço a partir do enquire-infra.
#
# Uso (depois de clonar enquire-infra para /var/www/enquire-infra):
#   cd /var/www/enquire-infra
#   bash bootstrap.sh                    # clona em /var/www/<repo>
#   bash bootstrap.sh /opt/enquire       # clona em /opt/enquire/<repo>
#
# Requer: chave SSH com acesso aos repos guaranta-disrupy/* já configurada no host.
# Verificar: ssh -T git@github.com   (deve dizer "Hi guaranta-disrupy! ...")

set -euo pipefail

DEST="${1:-/var/www}"
OWNER="guaranta-disrupy"

REPOS=(
  enquire-survey
  enquire-survey-engine
  enquire-survey-flask
  enquire-act-express
  enquire-express-engine
)

mkdir -p "$DEST"
cd "$DEST"

for repo in "${REPOS[@]}"; do
  if [ -d "$repo/.git" ]; then
    echo "[skip] $repo já existe em $DEST/$repo — git pull em vez disso"
    git -C "$repo" pull --ff-only
  else
    echo "[clone] $OWNER/$repo → $DEST/$repo"
    git clone "git@github.com:$OWNER/$repo.git" "$repo"
  fi
done

echo
echo "✅ Bootstrap concluído. Próximos passos:"
echo "   1. Copiar .env de cada serviço (ver MIGRACAO_GIT_SERVIDOR.md PARTE 4)"
echo "   2. Subir infra Docker: cd $DEST/enquire-infra && docker compose -f docker-compose.infra.yml up -d"
echo "   3. Instalar e migrar cada serviço (ver PARTE 6)"
