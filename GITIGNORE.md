# Política de `.gitignore` — Enquire_Fluent

Mono-repo único: **um** repositório Git na raiz. Não há repositórios Git separados por serviço.

## O que vai para o GitHub / servidor (via `git clone`)

| Conteúdo | Exemplos |
|----------|----------|
| Código-fonte | `fluent/app/`, `fluent-flask/app/`, etc. |
| Lockfiles | `composer.lock`, `package-lock.json`, `requirements.txt` |
| Config sem segredos | `.env.example`, `docker-compose.infra.yml`, `Manifests/` |
| Infra Docker (sem dados) | `docker/infra/init-databases.sql` |
| Documentação | `INICIALIZACAO_LOCAL.md`, `MIGRACAO_GIT_SERVIDOR.md` |

## O que **não** vai (instalar no servidor)

| Pasta / ficheiro | Serviço | Comando no servidor |
|------------------|---------|---------------------|
| `vendor/` | Fluent, Engine, ACT, Express | `composer install --no-dev` |
| `node_modules/` | Fluent, ACT, Express, express-engine | `npm install` |
| `public/build/` | Laravel + Vite | `npm run build` |
| `dist/` | express-engine | `npm run build` |
| `venv/` | fluent-flask | `python3 -m venv venv && pip install -r requirements.txt` |
| `docker/data/` | Infra local | BD vazia + `php artisan migrate` |
| `.env`, `*.env` | Todos | Copiar via SCP / secrets manager |
| `enviroment.md` | — | **Só na tua máquina** (credenciais Contabo/VPS) |

## Hierarquia dos `.gitignore`

1. **Raiz** `/.gitignore` — regra principal para todo o mono-repo.
2. **Por serviço** — complementam padrões Laravel/Vue/Python locais:
   - `fluent/.gitignore`
   - `fluent-engine/.gitignore`
   - `fluent-flask/.gitignore`
   - `act_express/act/.gitignore`
   - `act_express/express/.gitignore`
   - `express-engine/.gitignore`
   - `docker/.gitignore` (só `data/`)
   - `act_express/.gitignore` (atalho para os dois apps)

## Validar antes do primeiro commit

```bash
cd Enquire_Fluent
git add .
git ls-files | grep -E 'node_modules|vendor/|venv/|docker/data|\.env$|\.env\.development' | head
# ↑ deve estar VAZIO

git ls-files | wc -l   # milhares de ficheiros de código, não ~GB
```

## `enviroment.md`

Ficheiro **local** com passwords do VPS e painel Contabo. Está no `.gitignore` e **nunca** deve ir para o Git nem para o clone no servidor.
