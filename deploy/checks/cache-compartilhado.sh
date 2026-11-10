#!/usr/bin/env bash
# Confere se o Fluent e o motor de entrada (survey.nextsensus.com) usam o mesmo
# cache no Redis. O Fluent grava ali a configuração das pesquisas (status,
# rotas, grupos, painéis, scripts) a cada mudança, pelos observers e pelo
# StatusController, e o motor lê dali. Prefixos diferentes = o motor fica com
# a cópia antiga para sempre (ex.: pesquisa Live que abre como "not live").
#
# Uso no VPS: bash deploy/checks/cache-compartilhado.sh
set -euo pipefail
FLUENT=${FLUENT:-/var/www/enquire-survey/.env}
ENGINE=${ENGINE:-/var/www/enquire-survey-engine/.env}
falha=0
for v in REDIS_PREFIX CACHE_PREFIX REDIS_HOST REDIS_PORT REDIS_DB REDIS_CACHE_DB; do
  a=$(grep -E "^$v=" "$FLUENT" | cut -d= -f2- || true)
  b=$(grep -E "^$v=" "$ENGINE" | cut -d= -f2- || true)
  if [ "$a" = "$b" ]; then echo "ok    $v=${a:-<padrão>}"
  else echo "ERRO  $v: Fluent='${a:-<padrão>}' motor='${b:-<padrão>}'"; falha=1; fi
done
a=$(grep -E "^REDIS_PASSWORD=" "$FLUENT" | cut -d= -f2- | md5sum)
b=$(grep -E "^REDIS_PASSWORD=" "$ENGINE" | cut -d= -f2- | md5sum)
[ "$a" = "$b" ] && echo "ok    REDIS_PASSWORD (igual)" || { echo "ERRO  REDIS_PASSWORD diferente"; falha=1; }
[ $falha = 0 ] && echo "Cache compartilhado: OK" || { echo "Cache NÃO compartilhado: alinhe o .env do motor ao do Fluent e rode php artisan optimize:clear nos dois."; exit 1; }
