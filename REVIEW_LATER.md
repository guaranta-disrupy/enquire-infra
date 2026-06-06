# Pendências para revisão futura

Itens identificados durante o setup multi-repo + deploy VPS Contabo. Não bloqueiam o sistema funcional atual, mas precisam ser endereçados para produção real.

**Última atualização:** 2026-06-05 (pós-incidente ransomware + deploy completo).

---

## 🔴 Alta prioridade (segurança / operação)

### 1. PUSHER_APP_SECRET dummy
- Arquivo: `/var/www/enquire-survey-flask/.env` (VPS)
- Valor atual: `PUSHER_APP_SECRET=DUMMY_SECRET_REPLACE_LATER`
- Impacto: notificações de SPSS export do Flask vão falhar silenciosamente quando usadas (Pusher rejeita auth)
- Como resolver: obter o secret real do painel Pusher (dashboard.pusher.com) ou regenerar lá e atualizar nos `.env` do Fluent + Flask

### 2. APP_KEY do Express vazou no histórico Git
- Repo: `enquire-act-express` (commits iniciais)
- GitGuardian alertou; chave esvaziada no commit `bd42225` mas continua no histórico
- Como resolver: `git filter-repo` para remover do histórico + force push + confirmar com colaboradores
- Risco baixo agora (repo privado, chave nunca foi usada em produção), mas se um dia o repo virar público...

### 3. Histórico de senhas DB
- Local Mac: usa senha `secret` (fraca)
- VPS: usa senha forte `DR_<hex>` em `/root/.mariadb-root-pw` e `/root/.mariadb-local-pw`
- `enviroment.md` no Mac precisa ser atualizado com as senhas reais do VPS

### 4. HTTPS via Let's Encrypt
- Hoje todo o tráfego é HTTP em IPs públicos
- Browsers vão warn em forms de senha
- Solução: setar DNS (subdomínios em `enquire.disrupy.com` ou similar), nginx vhost com `certbot --nginx`
- Pré-requisito: definir domínio definitivo

---

## 🟡 Média prioridade (qualidade / performance)

### 5. `php artisan serve` → php-fpm + nginx
- Hoje rodando `php artisan serve --no-reload` com workaround:
  - `App\Console\Commands\ServeCommand` (override que silencia getRequestPortFromLine + getDateFromLine)
  - `PHP_CLI_SERVER_WORKERS=4`
- Para produção real: php-fpm + nginx vhost por serviço
- nginx + certbot já instalados no VPS — falta config

### 6. Tabelas Laravel standard ausentes no banco `fluent`
- Faltam: `sessions`, `cache`, `cache_locks`, `jobs`, `job_batches`
- Hoje contornado com `SESSION_DRIVER=file`, `CACHE_DRIVER=file`, `QUEUE_CONNECTION=sync` no .env
- Para alta carga: criar migrations + trocar drivers para `database`/`redis`

### 7. Comando `act:sync-teams-for-fk` inexistente
- Referenciado em [INICIALIZACAO_LOCAL.md:215](INICIALIZACAO_LOCAL.md#L215) mas código nunca foi commitado
- Hoje contornado via SQL manual:
  ```sql
  INSERT INTO act.teams (id, user_id, name, personal_team, fluent_id, ...)
    SELECT id, user_id, name, personal_team, id, ... FROM fluent.teams;
  ```
- Solução: criar Artisan command no `act_express/act/app/Console/Commands/` que faça este sync (idempotente, rodável depois de cada criação de team no Fluent)

### 8. Migration manual `2022_05_28_100000_create_act_core_domain_tables`
- Cria as tabelas `groups`, `projects`, `surveys`, `tests` no banco `act`
- **Só existe no banco** (entry em `migrations` + tabelas), arquivo `.php` não está no repo
- Patch SQL para fresh install: `/tmp/missing-vps/patch-act.sql` (extraído via `SHOW CREATE TABLE` do banco local)
- Solução: criar arquivo de migration no `act_express/act/database/migrations/` com o schema correto

### 9. Colunas faltantes em tabelas `fluent.*` (não-commitadas no repo)

Todas adicionadas manualmente no banco local em algum ponto, sem migration. No VPS precisaram ser patched via SQL. **Solução: criar migrations no `fluent/database/migrations/` consolidando todas:**

| Tabela | Coluna | Tipo | Necessária para |
|---|---|---|---|
| `users` | `deleted_at` | timestamp NULL | Express/ACT SoftDeletes via mysql_auth |
| `logs` | `data` | longtext JSON | RouteController::store → Auth::user()->logs()->create |
| `merge_groups` | `user_id` | bigint(20) unsigned | (controller que cria merge_groups) |
| `records` | `links_list` | longtext JSON | Routing engine (preview) |
| `records` | `links_status` | longtext JSON | Routing engine (preview) |
| `routes` | `links` | longtext JSON | RouteController::store (stations) |

Patch usado: `/tmp/missing-vps/patch-fluent-cols.sql` no Mac local.

### 10. `init-databases.sql` mismatch
- Criava `fluent_engine` (não usado) em vez de `fluent_express`
- Corrigido no repo `enquire-infra` (commit `846f097`)
- Não afeta clones futuros, mas worth noting

---

## 🟢 Baixa prioridade (cosméticos / code hygiene)

### 11. `ai-helpbot.test` URL hardcoded
- [resources/js/Components/AI/ChatBot.vue:35](fluent/resources/js/Components/AI/ChatBot.vue#L35):
  ```js
  const AI_HELPBOT_BASE_URL = import.meta.env.VITE_AI_HELPBOT_URL || 'http://ai-helpbot.test';
  ```
- Console erra `ERR_NAME_NOT_RESOLVED` mas não bloqueia
- Solução: setar `VITE_AI_HELPBOT_URL` no `.env` + rebuild Fluent

### 12. WKOBMRU folder
- [fluent/public/WKOBMRU/](fluent/public/WKOBMRU/) com `email_templates.html`, `personas.json`, `index.php` — security-by-obscurity
- Decidir: mover para `storage/app/private/` e servir via rota autenticada, ou manter

### 13. Vue 2 EOL no ACT
- ACT usa Vue 2 (EOL desde dez 2023)
- Eventual upgrade para Vue 3

### 14. PSR-4 case mismatch (ACT)
- `act_express/act/app/Http/Controllers/API/AiExecutionController.php` (pasta `API/`)
- Namespace declarado `App\Http\Controllers\Api\` (com "i" minúsculo)
- Composer warn "does not comply with psr-4 autoloading standard. Skipping"
- Solução: renomear pasta para `Api/`

### 15. Naming inconsistente: `is_exempt_from_subscription` vs `is_exempted_from_subscription`
- Coluna real: `is_exempt_from_subscription` (sem "ed")
- Accessor `getIsExemptedFromSubscriptionAttribute` em [fluent/app/Models/User.php:276](fluent/app/Models/User.php#L276) retorna `role==='root' || $this->is_exempt_from_subscription`
- Middleware `Subscription.php:17` lê `is_exempted_from_subscription` (com "ed") — funciona via accessor mas confuso
- Solução: padronizar nome

### 16. `fluent:make-local-admin --force` flag
- Comando refusa rodar com `APP_ENV!=local`
- Hoje precisamos flip temporário do .env para criar admin
- Solução: adicionar flag `--force` que bypassa o check

### 17. `getUserPermissions` nullable implícito (PHP 8.4 deprecation)
- [act_express/act/app/Helpers.php:339](act_express/act/app/Helpers.php#L339)
- PHP 8.5 vai breakar
- Solução: tipar explicitamente como `?Survey $main_survey = null`

### 18. Resíduos legados do Laravel Mix no Express
- `act_express/express/public/js/app.js` (8 MB), `public/css/app.css`, `mix-manifest.json`
- Vite migrou para `public/build/`, mas Mix legacy ficou em disco (ignored no .gitignore)
- Solução: deletar do disco com `rm public/js/app.js public/css/{app,custom}.css public/mix-manifest.json`

### 19. Swagger gerado em storage/api-docs
- ACT/Express geram `storage/api-docs/api-docs.json` (gitignored)
- Decidir: regenerar no deploy ou servir via rota dedicada

### 20. `fluent.test` legacy URL
- `act_express/express/.env.example` ainda referencia `http://fluent.test` no `APP_FLUENT_URL`
- Solução: limpar e padronizar para placeholder genérico

### 21. Symlinks `fluent-storage` removidos
- Existiam em `fluent/public/fluent-storage` e `act_express/express/public/fluent-storage` apontando para `/home/cj/ssr/...` (servidor antigo)
- Removidos durante setup multi-repo
- Verificar se o app referencia URLs `/fluent-storage/...` (provavelmente não, mas grep para ter certeza)

### 22. `surveys.folder_id` tipo errado (bigint em vez de char(26))
- `folders.id` é `char(26)` (ULID), `surveys.folder_id` era `bigint(20) unsigned` → mismatch
- Bug latente: NUNCA foi testado criar survey dentro de folder localmente (sempre criavam no root)
- VPS expôs ao primeiro teste real (`SQLSTATE[01000] Data truncated for column 'folder_id'`)
- Fix aplicado tanto no VPS quanto no local: `ALTER TABLE surveys MODIFY COLUMN folder_id CHAR(26) NULL DEFAULT NULL`
- Solução proper: criar migration `add_folder_id_as_ulid_to_surveys_table` que faça essa mudança

### 23. Teams criados via SQL precisam `config={"status":"active"}`
- [resources/js/Pages/Projects/Index.vue:536](fluent/resources/js/Pages/Projects/Index.vue#L536) lê `project.config.status` SEM optional chaining
- Se um team é criado direto via SQL (sem default), `config IS NULL` → frontend quebra com `Cannot read properties of null (reading 'status')` ao listar Projects
- Sempre criar team com: `INSERT INTO teams (..., config) VALUES (..., '{"status":"active"}')`
- Solução proper: mudar para `project.config?.status` (optional chaining) em Index.vue:536 e :537

---

## Workarounds adicionais (no código novo, não no produto)

### A. `App\Console\Commands\ServeCommand`
- Arquivo: [fluent/app/Console/Commands/ServeCommand.php](fluent/app/Console/Commands/ServeCommand.php)
- Estende `Illuminate\Foundation\Console\ServeCommand`
- Override de `getRequestPortFromLine` + `getDateFromLine` em try/catch (silencia exceções de linhas non-standard como curl debug headers)
- Registrado em [AppServiceProvider::boot()](fluent/app/Providers/AppServiceProvider.php) via `$this->app->extend(...)` (não `bind()` em `register()`, porque ConsoleSupportServiceProvider é deferred)
- **Pode ser removido se migrar para php-fpm**

### B. Drivers `file`/`sync` em vez de `database`
- `.env` do Fluent (VPS): `SESSION_DRIVER=file`, `CACHE_DRIVER=file`, `QUEUE_CONNECTION=sync`
- Bypassa as tabelas `sessions`/`cache`/`jobs` que não existem
- Reverter quando criar as migrations padrão

### C. PHP_CLI_SERVER_WORKERS=4 + --no-reload nos systemd units
- 4 services Laravel rodam com `PHP_CLI_SERVER_WORKERS=4` e `php artisan serve --no-reload`
- Workers necessários para múltiplas requests paralelas (POST /components + GET /assets)
- `--no-reload` necessário para `PHP_CLI_SERVER_WORKERS` ser respeitado
- Trocar com php-fpm

### D. Containers Docker bind em 127.0.0.1
- `docker-compose.infra.yml`: `ports: ["127.0.0.1:3306:3306"]` (não `"3306:3306"`)
- Hardening pós-ransomware. Manter sempre assim.
