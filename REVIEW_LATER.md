# Pendências para revisão futura

Itens identificados durante a preparação para multi-repo (2026-05-28). Não bloqueiam o primeiro push, mas requerem decisão depois do sistema estabilizar.

---

## 1. Pasta `fluent/public/WKOBMRU/`

**O que é:** Pasta com nome aleatório dentro de `fluent/public/`, contendo:
- `email_templates.html` (122 KB)
- `personas.json` (139 KB)
- `index.php` (29 KB)
- `generate_emails.py`
- `img/`

**Padrão:** Parece "endpoint público com URL obscuro" (security through obscurity).

**A decidir:**
- É intencional manter a pasta acessível por essa URL?
- Mover para fora do `public/` (ex.: `storage/app/private/email_templates/`) e servir via rota autenticada?
- Manter como está?

**Estado actual:** Será commitada como está no repo `enquire-fluent`.

---

## 2. Refatoração geral do Swagger (ACT + Express)

**O que é:** Ambos os apps geram `storage/api-docs/api-docs.json` (36 KB + 132 KB).

**Estado actual:** Adicionado a `/storage/api-docs` no `.gitignore` de cada um. Será **regenerado no VPS** com o comando de build do Swagger (ver `composer.json` de cada app — provavelmente `php artisan l5-swagger:generate`).

**A decidir depois:**
- Inserir geração do Swagger no fluxo de deploy (artisan command + persistir num CDN ou rota autenticada).
- Decidir se a doc deve ser pública ou só interna.

**Prioridade:** Baixa — pode esperar o sistema estabilizar.

---

## 3. Resíduos legados do Laravel Mix em `act_express/express/public/`

**O que é:** Após migração para Vite, ficaram em disco:
- `public/js/app.js` (8 MB — bundle webpack/Mix antigo)
- `public/css/app.css` + `public/css/custom.css`
- `public/mix-manifest.json`

**Estado actual:** Adicionados ao `.gitignore` — não vão para o repo. Continuam em disco localmente, mas não são usados pelo Vite (`vite.config.js`).

**A decidir:**
- Deletar fisicamente do disco local (`rm public/js/app.js public/css/* public/mix-manifest.json`) e confirmar que nada referencia esses caminhos antigos.

**Verificação rápida sugerida:** `grep -rn "mix-manifest\|public/js/app.js" act_express/express/{app,resources,routes}/`

---

## 4. Symlinks `fluent-storage` removidos

**O que era:** Em `fluent/public/fluent-storage` e `act_express/express/public/fluent-storage` havia symlinks para `/home/cj/ssr/fluent/storage/app/public` — path do servidor antigo, broken localmente.

**Acção tomada:** Ambos deletados.

**A decidir/verificar:**
- Se o app referencia URLs `/fluent-storage/...` em código (blade, vue, etc.), precisamos recriar o symlink no VPS novo (`ln -s ../../fluent/storage/app/public fluent-storage` — ajustar relativo ao layout final).
- Provavelmente NÃO é necessário — o standard Laravel é `public/storage` (criado por `php artisan storage:link`), que é diferente.

**Verificação sugerida:** `grep -rn "fluent-storage" fluent/ act_express/express/ --include="*.php" --include="*.vue" --include="*.blade.php"`

---

## 5. Inconsistência docs vs script

[INICIALIZACAO_LOCAL.md:76](INICIALIZACAO_LOCAL.md#L76) cria admin `admin@local.dev` / `admin123`.
[populate_survey_mt_maceio.py:36](populate_survey_mt_maceio.py#L36) tenta logar com `admin@local.test` / `admin123`.

**Acção:** Alinhar um dos dois.
