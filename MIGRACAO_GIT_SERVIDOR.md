# Migração para servidor de nuvem via Git — Multi-repo

Plano para subir o **Enquire** (multi-repo, 5 serviços + 1 infra) para a conta
`guaranta-disrupy` no GitHub e clonar/configurar no VPS Contabo (Cloud VPS 30 SSD).

> **Decisão de arquitetura:** multi-repo (cada serviço = repo próprio).
> Local: tudo continua em `~/Documents/Projetos/Disrupy/Enquire_Fluent/` por conveniência de dev.
> Servidor (VPS): cada repo clonado em `/var/www/<repo>/` (flat).

---

## Repositórios

| Repo | Pasta local | Pasta VPS | Serviço |
|---|---|---|---|
| `enquire-survey` | `fluent/` | `/var/www/enquire-survey/` | Laravel app principal (8000) |
| `enquire-survey-engine` | `fluent-engine/` | `/var/www/enquire-survey-engine/` | Laravel preview (8001) |
| `enquire-survey-flask` | `fluent-flask/` | `/var/www/enquire-survey-flask/` | FastAPI + Celery (8002) |
| `enquire-act-express` | `act_express/` | `/var/www/enquire-act-express/` | Express (8003) + ACT (8004) |
| `enquire-express-engine` | `express-engine/` | `/var/www/enquire-express-engine/` | Vue preview (7878) |
| `enquire-infra` | (raiz) | `/var/www/enquire-infra/` | Docker compose local, manifests prod, docs, scripts |

Todos privados na conta `guaranta-disrupy`. Acesso via SSH alias `github-disrupy`
(chave `~/.ssh/id_ed25519_disrupy`, ver `~/.ssh/config`).

---

## PARTE 1 — Estado local (já feito)

- ✅ `.gitignore` por serviço corrigido (cobre `.env`, `.env.*`, `vendor/`, `node_modules/`, `venv/`, builds, Swagger, Zone.Identifier, .DS_Store)
- ✅ Symlinks broken `fluent-storage` removidos
- ✅ Ficheiros NTFS `*:Zone.Identifier` deletados
- ✅ Cada repo inicializado com `git init -b main`, primeiro commit feito
- ✅ Remotes apontam para `git@github-disrupy:guaranta-disrupy/<repo>.git`
- ⏳ Push (`git push -u origin main`) — pendente

Pendências de revisão futura registadas em [REVIEW_LATER.md](REVIEW_LATER.md).

---

## PARTE 2 — Pré-requisitos no VPS Contabo

```bash
# Pacotes base (Ubuntu/Debian)
apt update && apt install -y git curl unzip software-properties-common

# PHP 8.4 (ACT/Express) + 8.3 (Fluent/Engine) — instalar via ondrej/php
add-apt-repository ppa:ondrej/php -y && apt update
apt install -y php8.4-{cli,fpm,mbstring,xml,pdo-mysql,mongodb,gd,zip,bcmath,curl}

# Composer
curl -sS https://getcomposer.org/installer | php -- --install-dir=/usr/local/bin --filename=composer

# Node.js 22 LTS
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt install -y nodejs

# Python 3.10+
apt install -y python3 python3-pip python3-venv

# Docker + Compose
curl -fsSL https://get.docker.com | sh
apt install -y docker-compose-plugin

# nginx (proxy/produção)
apt install -y nginx
```

---

## PARTE 3 — Clone de todos os repos (bootstrap)

A chave SSH de deploy (criar no VPS e adicionar nas Deploy Keys de CADA repo):

```bash
ssh-keygen -t ed25519 -C "vps-contabo-deploy" -f ~/.ssh/id_ed25519_deploy
cat ~/.ssh/id_ed25519_deploy.pub   # adicionar em github.com/<repo>/settings/keys
```

Depois, no VPS:

```bash
cd /var/www
git clone git@github.com:guaranta-disrupy/enquire-infra.git
cd enquire-infra
bash bootstrap.sh    # clona os outros 5 repos em /var/www/<repo>/
```

---

## PARTE 4 — Configurar `.env` por serviço

Os `.env` NÃO vêm do git. Transferir do Mac local via SCP:

```bash
# Do Mac:
scp ~/Documents/Projetos/Disrupy/Enquire_Fluent/fluent/.env           root@161.97.178.169:/var/www/enquire-survey/.env
scp ~/Documents/Projetos/Disrupy/Enquire_Fluent/fluent-engine/.env    root@161.97.178.169:/var/www/enquire-survey-engine/.env
scp ~/Documents/Projetos/Disrupy/Enquire_Fluent/fluent-flask/.env     root@161.97.178.169:/var/www/enquire-survey-flask/.env
scp ~/Documents/Projetos/Disrupy/Enquire_Fluent/act_express/act/.env  root@161.97.178.169:/var/www/enquire-act-express/act/.env
scp ~/Documents/Projetos/Disrupy/Enquire_Fluent/act_express/express/.env root@161.97.178.169:/var/www/enquire-act-express/express/.env
scp ~/Documents/Projetos/Disrupy/Enquire_Fluent/express-engine/.env.local root@161.97.178.169:/var/www/enquire-express-engine/.env.local
```

> **Ajustar no servidor**: `APP_ENV=production`, `APP_DEBUG=false`, hosts de BD/Redis/Mongo
> (se em Docker no mesmo host: `127.0.0.1`; se externos: endpoint real). Atualizar `APP_URL`
> e `APP_*_URL`/`APP_*_ENGINE_URL` para o domínio público do VPS.

---

## PARTE 5 — Subir infra (Docker)

```bash
cd /var/www/enquire-infra
docker compose -f docker-compose.infra.yml up -d
# MariaDB:3306, MongoDB:27017, Redis:6379, Neo4j:7474/7687
```

> Volumes de BD começam vazios. As tabelas serão criadas pelas migrations (parte 6).

---

## PARTE 6 — Instalar + migrar por serviço

```bash
# --- enquire-survey (Fluent — app principal) ---
cd /var/www/enquire-survey
composer install --no-dev --optimize-autoloader
npm install && npm run build
php artisan key:generate           # só se APP_KEY vazio
php artisan migrate --force
php artisan fluent:make-local-admin --email=admin@dominio --password=SENHA --name="Admin" --role=admin

# --- enquire-survey-engine ---
cd /var/www/enquire-survey-engine
composer install --no-dev --optimize-autoloader
php artisan key:generate

# --- enquire-act-express (express) ---
cd /var/www/enquire-act-express/express
composer install --no-dev --optimize-autoloader --ignore-platform-reqs
npm install && npm run build
php artisan key:generate
php artisan migrate --force
php artisan db:seed --class=QuestionTypeSeeder
php artisan db:seed --class=QuestionTemplateLanguageSeeder

# --- enquire-act-express (act) ---
cd /var/www/enquire-act-express/act
composer install --no-dev --optimize-autoloader --ignore-platform-reqs
npm install && npm run build
php artisan key:generate
php artisan migrate --force
php artisan act:sync-teams-for-fk

# --- enquire-express-engine ---
cd /var/www/enquire-express-engine
npm install && npm run build       # produção: nginx serve /dist

# --- enquire-survey-flask ---
cd /var/www/enquire-survey-flask
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

---

## PARTE 7 — Correr serviços em produção (resumido)

| Serviço | Comando dev | Produção |
|---|---|---|
| Fluent | `php artisan serve` | php-fpm + nginx (root: `enquire-survey/public`) |
| Engine | `php artisan serve --port=8001` | php-fpm + nginx |
| Express | `php artisan serve --port=8003` | php-fpm + nginx |
| ACT | `php artisan serve --port=8004` | php-fpm + nginx |
| Express Engine | `npm run serve` | nginx servindo `dist/` |
| Flask | `venv/bin/uvicorn app.main_fastapi:app --port 8002` | uvicorn + systemd (ou gunicorn) |
| Queues | `php artisan queue:work` (no enquire-survey) | supervisor |

Configurar HTTPS via Let's Encrypt antes de expor publicamente.

---

## PARTE 8 — Fluxo contínuo (depois da migração)

```bash
# Local — em cada repo, fluxo normal
cd ~/Documents/Projetos/Disrupy/Enquire_Fluent/fluent
git add . && git commit -m "..." && git push

# Servidor — em cada repo afetado
cd /var/www/enquire-survey
git pull
composer install --no-dev --optimize-autoloader  # se composer.lock mudou
npm install && npm run build                      # se package-lock.json mudou
php artisan migrate --force                       # se houver migrations novas
```

---

## Checklist de segurança final

- [ ] `git ls-files | grep -E '\.env$|venv/|node_modules|vendor/|docker/data'` em **cada** repo → vazio
- [ ] Nenhum segredo no histórico (se commitaste por engano: `git rm --cached <file>` + rotacionar credencial + force push)
- [ ] `.env` do servidor com credenciais de **produção** (não as locais)
- [ ] `APP_ENV=production`, `APP_DEBUG=false`, `APP_LOG_LEVEL=error` nos `.env` do servidor
- [ ] Deploy key SSH no VPS (ou PAT no `~/.netrc`) configurada para todos os repos
- [ ] HTTPS configurado (Let's Encrypt) antes de expor portas 80/443
- [ ] Firewall (`ufw`): apenas 22, 80, 443 públicas; portas 8000-8004, 7878, 3306, 27017, 6379, 7474 só localhost
