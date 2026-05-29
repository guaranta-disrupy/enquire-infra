# Inicialização do ambiente local (Fluent + Docker)

PHP e Node correm na tua máquina; MariaDB, MongoDB, Redis e Neo4j sobem via Docker. Ajusta caminhos se o clone estiver noutro sítio.

**Pré-requisitos:** Docker Desktop, PHP 8.3+ (Fluent/Engine) / 8.4+ (ACT), Composer, Node.js 20.19+ ou 22.12+ (recomendado para o Vite 7).

---

## 1. Infra (Docker)

Na **raiz do repositório** (`Enquire_Fluent`):

```bash
docker compose -f docker-compose.infra.yml up -d
```

Serviços e portas padrão:

| Serviço  | Porta |
|----------|-------|
| MariaDB  | 3306  |
| MongoDB  | 27017 |
| Redis    | 6379  |
| Neo4j    | 7474 (HTTP), 7687 (Bolt) |

Utilizador SQL de exemplo (ver `docker/infra/init-databases.sql`): `local` / `secret`; base `fluent` (partilhada entre Fluent e Engine).

**Parar infra:**

```bash
docker compose -f docker-compose.infra.yml down
```

**MongoDB a não subir após reboot:** pode ser corrupção do volume em `docker/data/mongodb`. Parar o serviço, renomear essa pasta para backup e criar `docker/data/mongodb` vazio; voltar a subir o compose (perdes dados só do Mongo local).

---

## 2. Variáveis de ambiente

- **Fluent:** `fluent/.env` — alinha com `fluent/.env.development`; para este stack, `DB_HOST=127.0.0.1`, `DB_DATABASE=fluent`, `MONGODB_URI=mongodb://127.0.0.1:27017`, `APP_URL=http://127.0.0.1:8000`, `APP_ENGINE_URL=http://127.0.0.1:8001`.
- **Fluent Engine:** `fluent-engine/.env` — mesma lógica para MySQL/Mongo em `127.0.0.1` e **base `fluent` (partilhada)**.
- **Fluent Flask:** `fluent-flask/.env` — credenciais locais MySQL/Mongo/Redis (ver seção 5).

Se ainda não existir `.env`:

```bash
cp fluent/.env.example fluent/.env
# Editar fluent/.env manualmente (ou copiar de .env.development e ajustar hosts para 127.0.0.1)
```

---

## 3. Fluent (app principal)

```bash
cd fluent
composer install
npm install
```

Chave da aplicação (se `APP_KEY` estiver vazio):

```bash
php artisan key:generate
```

Base de dados (cria todas as tabelas):

```bash
php artisan migrate --force
```

**Utilizador admin local** (só com `APP_ENV=local`; e-mail já "verificado", sem depender de SMTP):

```bash
php artisan fluent:make-local-admin --email=admin@local.dev --password=admin123 --name="Admin Local" --role=admin
```

**Correr em desenvolvimento** (servidor HTTP, fila, logs Pail e Vite):

```bash
composer run dev
```

Por defeito o Laravel serve em `http://127.0.0.1:8000`. O Vite usa `http://127.0.0.1:5173` (configuração em `vite.config.js`).

Alternativa mínima (dois terminais): `php artisan serve` e `npm run dev`.

---

## 4. Fluent Engine

```bash
cd fluent-engine
composer install
php artisan key:generate
# Nota: migrate não é necessário, pois Engine partilha a base 'fluent'
php artisan serve --port=8001
```

URL típica: `http://127.0.0.1:8001`. O Fluent deve apontar para esta URL em `APP_ENGINE_URL` no `.env`.

---

## 5. Fluent Flask (opcional/FastAPI)

O `fluent-flask` usa FastAPI (uvicorn) e depende de Python 3.10+.

### Problemas conhecidos

A instalação das dependências requer compilação de extensões C++ (`greenlet`, `opencv-python-headless`). Se não tiveres Xcode Command Line Tools completo instalado, a instalação pode falhar com:

```
fatal error: 'cstdlib' file not found
```

### Instalação (se resolveres as dependências de build)

```bash
cd fluent-flask
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

O `.env` já foi criado com credenciais locais (`fluent-flask/.env`). Para correr:

```bash
venv/bin/uvicorn app.main_fastapi:app --host 127.0.0.1 --port 8002 --reload
```

Docs interativas: `http://127.0.0.1:8002/docs`

---

## 6. Acesso rápido

| O quê        | URL |
|--------------|-----|
| Fluent       | http://127.0.0.1:8000 |
| Engine       | http://127.0.0.1:8001 |
| Flask (opt)  | http://127.0.0.1:8002 |
| API Express  | http://127.0.0.1:8003 (ver secção 10) |
| API ACT      | http://127.0.0.1:8004 (ver secção 10) |
| express-engine | http://127.0.0.1:7878 (ver secção 10) |
| Vite (assets)| http://127.0.0.1:5173 (uso normal via Fluent) |

Registo web em `/register` ou login com o utilizador criado por `fluent:make-local-admin`.

---

## 7. Opcional

- **E-mail real em local:** configurar SMTP no `.env` ou usar Mailhog; com `MAIL_MAILER=log` as mensagens vão para o log.
- **Neo4j:** já incluído no `docker-compose.infra.yml`; configura `NEO4J_URI` / credenciais no `.env` do Fluent se usares funcionalidades que dependam dele.
- **Qualidade de código (Fluent):** `./vendor/bin/pint`

---

## 8. Ordem resumida (checklist)

1. `docker compose -f docker-compose.infra.yml up -d`
2. Configurar `fluent/.env` e `fluent-engine/.env` (apontar para base `fluent` em ambos)
3. `cd fluent && composer install && npm install && php artisan key:generate && php artisan migrate --force`
4. `php artisan fluent:make-local-admin --email=admin@local.dev --password=admin123 --name="Admin Local" --role=admin`
5. `composer run dev` (dentro de `fluent`)
6. `cd fluent-engine && composer install && php artisan key:generate && php artisan serve --port=8001`
7. (Opcional) `fluent-flask`: resolver dependências de build e correr `uvicorn`
8. (Opcional) Express, ACT e `express-engine` — ver secção 10
   - Express: `cd act_express/express && php artisan migrate && php artisan db:seed --class=QuestionTypeSeeder && php artisan db:seed --class=QuestionTemplateLanguageSeeder && npm run build && php artisan serve --port=8003`
   - ACT: `cd act_express/act && php artisan migrate && php artisan act:sync-teams-for-fk && npm run build && php artisan serve --port=8004`
   - express-engine: `cd express-engine && npm run serve` (manter rodando para preview)

---

## 9. Estrutura de tabelas

Após `php artisan migrate --force`, a base `fluent` inclui:

**Tabelas core Laravel/Jetstream:**
- `users`, `teams`, `team_user`, `personal_access_tokens`, `sessions`, `password_reset_tokens`, `failed_jobs`, `jobs`, `job_batches`

**Tabelas de domínio (criadas pela migração `2026_04_15_100000_create_missing_core_tables.php`):**
- `surveys`, `records`, `routes`, `groups`, `panels`, `scripts`, `script_templates`, `setups`, `filters`, `merge_groups`, `logs`, `survey_user`, `analysis`, `team_invitations`

**Outras tabelas da aplicação:**
- `folders`, `workspaces`, `components`, `analysis_folders`, `analysis_projects`, `analysis_profiles`, `global_setups`, `global_galleries`, `survey_workspaces`, `crosstabs`, `widgets`, `notifications`, `reviews`, etc.

As foreign keys para `surveys` são adicionadas na migração `2026_04_15_100001_add_deferred_foreign_keys_to_surveys.php`.

---

## 10. Express / ACT (APIs locais) e `express-engine`

Bases SQL extra (além de `fluent`): `fluent_express` (API Express) e `act` (API ACT), criadas e concedidas no `docker/infra/init-databases.sql` para o utilizador de exemplo. No `.env` do **Fluent** (`DB_*_EXPRESS`, `DB_*_ACT` e `APP_EXPRESS_URL`, `APP_ACT_URL`, motores) aponta para o mesmo host em que correm o Express e o ACT; exemplos: `http://127.0.0.1:8003` (Express) e `http://127.0.0.1:8004` (ACT). No **Express** e no **ACT**, o auth principal usa a base do Fluent via `DB_DATABASE_AUTH=fluent` (e `DB_*_AUTH` alinhado com o Fluent).

| Serviço         | Porta sugerida | Pasta                   | `vite.config.js` host |
|-----------------|----------------|-------------------------|------------------------|
| API Express     | 8003           | `act_express/express`   | `127.0.0.1` (Vite 4)  |
| API ACT         | 8004           | `act_express/act`       | `127.0.0.1` (Vite 6)  |
| express-engine  | 7878           | `express-engine`        | `0.0.0.0` (vue-cli)   |

### 10.1 Setup completo do ACT (primeira vez ou após `migrate:fresh`)

```bash
cd act_express/act
composer install           # dependências PHP (já instaladas se vendor/ existir)
npm install                # dependências JS (já instaladas se node_modules/ existir)
php artisan key:generate   # só se APP_KEY estiver vazio
php artisan migrate        # cria tabelas no banco 'act'
php artisan act:sync-teams-for-fk   # espelha teams do Fluent → act (necessário para FKs)
npm run build              # gera assets em public/build (ou 'npm run dev' para HMR)
php artisan serve --port=8004       # manter rodando em terminal separado
```

**Nota sobre `act:sync-teams-for-fk`:** deve ser rodado sempre que o banco `act` for recriado (`migrate:fresh`) ou quando novos teams forem criados no Fluent. Copia `teams` e `team_user` da conexão `mysql_auth` (Fluent) para a base `act`, mantendo os mesmos IDs.

### 10.2 Setup completo do Express (primeira vez ou após `migrate:fresh`)

```bash
cd act_express/express
composer install
npm install
php artisan key:generate
php artisan migrate
php artisan db:seed --class=QuestionTypeSeeder          # tipos de pergunta (obrigatório)
php artisan db:seed --class=QuestionTemplateLanguageSeeder  # idiomas dos templates (obrigatório)
npm run build
php artisan serve --port=8003
```

### 10.3 express-engine (preview Express no browser)

```bash
cd express-engine
npm install       # só na primeira vez
npm run serve     # dev server na porta 7878 — manter rodando enquanto faz preview
```

Arquivo `express-engine/.env.local`:
```
VUE_APP_TITLE=Express Engine
VUE_APP_API=http://127.0.0.1:8003/api/f8208271af
VUE_APP_HOST=http://127.0.0.1:8003
```

### 10.4 Preview do ACT

O preview do ACT usa o **Fluent Engine (porta 8001)**, não um serviço separado.  
`APP_ACT_ENGINE_URL=http://127.0.0.1:8001/preview/act/` no `fluent/.env` já aponta para ele.

Para o preview ACT funcionar, os três serviços precisam estar ativos:
- **Fluent** em 8000
- **Fluent Engine** em 8001 (`cd fluent-engine && php artisan serve --port=8001`)
- **ACT API** em 8004

### 10.5 Problemas conhecidos

- **`users.deleted_at` no Express/ACT:** certifique-se de que a migration com essa coluna foi aplicada no Fluent.
- **composer vs lockfile de PHP:** se reclamar de incompatibilidade de versão, use `composer install --ignore-platform-reqs`.
- **`ERR_CONNECTION_REFUSED` nos assets (Express):** o `npm run build` gerou `public/build/`. Se a porta 5173 (Vite dev) não estiver ativa, a página carrega normalmente pelos assets buildados.

**Checklist de fumo (browser):** criar um componente Express num questionário; abrir o item Express no Fluent e verificar se `users.__tokens.express` fica preenchido após o handshake; preview do componente com o `express-engine` a servir a UI e `VUE_APP_API` a apontar para o Express local (arquivo `express-engine/.env.local`).

Checklist análogo para ACT: criar componente ACT; clicar nele no Fluent; verificar redirect para `127.0.0.1:8004/survey/.../...` (back-office ACT).
