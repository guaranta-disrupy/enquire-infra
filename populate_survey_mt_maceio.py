#!/usr/bin/env python3
"""
populate_survey_mt_maceio.py
-----------------------------
Popula automaticamente a survey "MCZ TESTE" (ID=1) no Fluent com todos os
componentes, perguntas, choices, primes e targets da pesquisa MT Maceió –
JHC e Rodrigo (Prefeito de Maceió).

Pré-requisitos:
  - Fluent   rodando em http://127.0.0.1:8000
  - Express  rodando em http://127.0.0.1:8003
  - ACT      rodando em http://127.0.0.1:8004
  - MariaDB  rodando via Docker (porta 3306)

Uso:
  python3 populate_survey_mt_maceio.py
  python3 populate_survey_mt_maceio.py --fresh   # apaga componentes existentes primeiro
"""

import requests
import json
import random
import string
import sys
import time
import argparse
from urllib.parse import unquote

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURAÇÃO
# ─────────────────────────────────────────────────────────────────────────────
FLUENT_URL  = "http://127.0.0.1:8000"
EXPRESS_URL = "http://127.0.0.1:8003"
ACT_URL     = "http://127.0.0.1:8004"

EMAIL    = "admin@local.test"
PASSWORD = "admin123"   # ajuste se a senha for diferente

SURVEY_ID   = 1   # ID interno (para queries de DB)
SURVEY_UUID = "c1a10f5f-d916-4841-9d95-159d586713a0"  # route key do Fluent

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS GERAIS
# ─────────────────────────────────────────────────────────────────────────────
def cuuid(n=7):
    """Gera um ID curto aleatório para choices do Express."""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=n))

def log(msg, level=0):
    indent = "  " * level
    print(f"{indent}{msg}")

def die(msg):
    print(f"\n[ERRO] {msg}", file=sys.stderr)
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# AUTENTICAÇÃO (sessão + CSRF para cada serviço)
# ─────────────────────────────────────────────────────────────────────────────
def login(base_url: str, email: str, password: str) -> requests.Session:
    s = requests.Session()
    try:
        s.get(f"{base_url}/sanctum/csrf-cookie", timeout=10)
    except requests.exceptions.ConnectionError:
        die(f"Não foi possível conectar a {base_url}. O serviço está rodando?")
    xsrf = unquote(s.cookies.get("XSRF-TOKEN", ""))
    r = s.post(
        f"{base_url}/login",
        json={"email": email, "password": password},
        headers={
            "X-XSRF-TOKEN": xsrf,
            "Accept": "application/json",
            "Referer": base_url,
        },
        timeout=15,
    )
    if r.status_code not in (200, 204):
        die(f"Login falhou em {base_url}: {r.status_code}\n{r.text[:300]}")
    log(f"✓ Login OK → {base_url}", 1)
    return s

def hdrs(session: requests.Session, base_url: str) -> dict:
    """Headers para requisições autenticadas (POST/PUT)."""
    xsrf = unquote(session.cookies.get("XSRF-TOKEN", ""))
    return {
        "X-XSRF-TOKEN": xsrf,
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": base_url,
    }

# ─────────────────────────────────────────────────────────────────────────────
# OPERAÇÕES NO FLUENT
# ─────────────────────────────────────────────────────────────────────────────
def get_components(fluent_s: requests.Session) -> list:
    r = fluent_s.get(
        f"{FLUENT_URL}/api/surveys/{SURVEY_ID}/components_list"
            if False  # endpoint alternativo não encontrado
        else f"{FLUENT_URL}/surveys/{SURVEY_UUID}",
        headers={"Accept": "application/json"},
        timeout=15,
    )
    if r.status_code == 200:
        data = r.json()
        return data.get("components", data.get("survey", {}).get("components", []))
    return []

def create_component(fluent_s: requests.Session, name: str, comp_type: str, variable: str) -> dict:
    r = fluent_s.post(
        f"{FLUENT_URL}/surveys/{SURVEY_UUID}/components",
        json={
            "name": name,
            "type": comp_type,
            "type_id": 1,
            "variable": variable,
            "details": name,
        },
        headers=hdrs(fluent_s, FLUENT_URL),
        timeout=30,
    )
    if r.status_code not in (200, 201):
        die(f"Erro ao criar componente '{name}': {r.status_code}\n{r.text[:400]}")
    data = r.json()
    model_id = (data.get("component", data).get("config", {}) or {}).get("model", {}).get("id", "?")
    log(f"✓ Componente '{name}' ({comp_type}) criado — model.id={model_id}", 2)
    return data

def delete_component(fluent_s: requests.Session, comp_id: int):
    r = fluent_s.delete(
        f"{FLUENT_URL}/surveys/{SURVEY_UUID}/components/{comp_id}",
        headers=hdrs(fluent_s, FLUENT_URL),
        timeout=15,
    )
    if r.status_code not in (200, 204):
        log(f"⚠ Não foi possível apagar componente {comp_id}: {r.status_code}", 2)

# ─────────────────────────────────────────────────────────────────────────────
# OPERAÇÕES DE STATIONS (Routes) NO FLUENT
# ─────────────────────────────────────────────────────────────────────────────
ENGINE_URLS = {
    "express": "http://127.0.0.1:7878/?code=",
    "act":     "http://127.0.0.1:8001/preview/act/",
    "fast":    "http://127.0.0.1:8001/",
    "impress": "http://127.0.0.1:8001/",
}

def station_link(comp_type: str, model_id, label: str) -> dict:
    base = ENGINE_URLS.get(comp_type, "")
    url  = f"{base}{model_id}&" if base and model_id else ""
    return {
        "label":         label,
        "link":          url,
        "platform":      comp_type,
        "external":      False,
        "check":         {"enabled": False, "apiLink": ""},
        "variables":     [],
        "selected_part": None,
    }

def station_link_bridge(survey_code: str, script_key: int, label: str = "Bridge Station") -> dict:
    """Bridge link: hits ScriptController::mini, executando o script (1-based key) do survey."""
    return {
        "label":         label,
        "link":          f"{FLUENT_URL}/script/{survey_code}/{script_key}?",
        "platform":      "custom",
        "external":      False,
        "check":         {"enabled": False, "apiLink": ""},
        "variables":     [],
        "selected_part": None,
    }

def station_config(title: str, station_type: str = "default",
                   to_group_cells: list = None) -> dict:
    """
    station_type: 'default' | 'bridge'
    to_group_cells: lista de {"name": "group_name", "index": cell_index_1_based}
                    se preenchido, só respondentes naquela(s) cell(s) passam por aqui
    """
    cfg = {
        "title": title,
        "random": {"enabled": False, "take": "all", "count": 1},
        "toGroup": {
            "enabled": bool(to_group_cells),
            "groups":  to_group_cells or [],
        },
        "receivedURI": {"save": True, "appendBack": True},
        "appendVars": {
            "position":  "append_first",
            # prac_switch=1 → mostrar trials de prática; dummy_switch=1 → mostrar descritivos
            # Para produção real, mudar para "prac_switch=0&dummy_switch=0&"
            "variables": "prac_switch=1&dummy_switch=1&",
            "enabled":   True,
        },
        "generateVars": {"enabled": False, "variables": []},
    }
    if station_type == "bridge":
        cfg["type"] = "bridge"
    return cfg

def create_station(fluent_s: requests.Session, title: str, comp_type: str, model_id, label: str = None) -> dict:
    payload = {
        "config": station_config(title),
        "links":  [station_link(comp_type, model_id, label or title)],
    }
    r = fluent_s.post(
        f"{FLUENT_URL}/surveys/{SURVEY_UUID}/stations/store",
        json=payload,
        headers=hdrs(fluent_s, FLUENT_URL),
        timeout=20,
    )
    if r.status_code not in (200, 201):
        die(f"Erro ao criar station '{title}': {r.status_code}\n{r.text[:400]}")
    log(f"✓ Station criada: {title}", 2)
    return r.json()

def create_station_multi(fluent_s: requests.Session, title: str, links: list,
                         to_group_cells: list = None, station_type: str = "default") -> dict:
    """
    Cria uma station que agrega MÚLTIPLOS links (multi-component) e/ou aplica filtro toGroup.
    links: lista de dicts já no formato esperado (use station_link / station_link_bridge)
    """
    payload = {
        "config": station_config(title, station_type=station_type, to_group_cells=to_group_cells),
        "links":  links,
    }
    r = fluent_s.post(
        f"{FLUENT_URL}/surveys/{SURVEY_UUID}/stations/store",
        json=payload,
        headers=hdrs(fluent_s, FLUENT_URL),
        timeout=20,
    )
    if r.status_code not in (200, 201):
        die(f"Erro ao criar station '{title}': {r.status_code}\n{r.text[:400]}")
    ncomps = len(links)
    extra = ""
    if station_type == "bridge":
        extra = " [BRIDGE]"
    if to_group_cells:
        extra += f" filtro={to_group_cells}"
    log(f"✓ Station criada: {title} ({ncomps} link(s)){extra}", 2)
    return r.json()

def delete_station(fluent_s: requests.Session, station_id: int):
    r = fluent_s.delete(
        f"{FLUENT_URL}/surveys/{SURVEY_UUID}/stations/destroy/{station_id}",
        headers=hdrs(fluent_s, FLUENT_URL),
        timeout=15,
    )
    if r.status_code not in (200, 204):
        log(f"⚠ Não foi possível apagar station {station_id}: {r.status_code}", 2)

def get_components_from_db_via_api(fluent_s: requests.Session) -> list:
    """Quando rodando em modo --stations-only, obtém componentes via routes do Fluent."""
    r = fluent_s.get(
        f"{FLUENT_URL}/surveys/{SURVEY_UUID}/stations/create",
        headers={"Accept": "application/json"},
        timeout=15,
    )
    if r.status_code == 200:
        data = r.json()
        return data.get("components", [])
    return []

# ─────────────────────────────────────────────────────────────────────────────
# OPERAÇÕES DE GROUPS (Breakout Groups) NO FLUENT
# ─────────────────────────────────────────────────────────────────────────────
def mk_criterion(label: str, quota: int, conditions="none") -> dict:
    return {"label": label, "quota": int(quota), "conditions": conditions}

def create_group(fluent_s: requests.Session, name: str, criteria: list,
                 total_quota: int = 0, is_for_analysis: bool = True) -> dict:
    """
    name deve ser alpha_dash (letras, números, _ e -)
    is_for_analysis: True → aparece no wizard de Analysis como breakout
                     False → group de fluxo (ex.: politician-awareness)
    """
    payload = {
        "name": name,
        "config": {
            "part":             1,
            "quota":            total_quota or sum(c.get("quota", 0) for c in criteria),
            "disqualify":       "disabled",
            "private":          False,
            "criteria":         criteria,
            "multiple":         "first",
            "is_for_analysis":  is_for_analysis,
            "multiple_config": {
                "min": 1, "max": 2,
                "max_priorities": 0,
                "priorities": [],
            },
        },
        "criteria": {},
    }
    r = fluent_s.post(
        f"{FLUENT_URL}/surveys/{SURVEY_UUID}/groups/store",
        json=payload,
        headers=hdrs(fluent_s, FLUENT_URL),
        timeout=20,
    )
    if r.status_code not in (200, 201):
        die(f"Erro ao criar group '{name}': {r.status_code}\n{r.text[:400]}")
    log(f"✓ Group criado: {name} ({len(criteria)} cells, quota={payload['config']['quota']})", 2)
    return r.json()

# ─────────────────────────────────────────────────────────────────────────────
# OPERAÇÕES DE PANELS (Redirects) NO FLUENT
# ─────────────────────────────────────────────────────────────────────────────
def create_panel(fluent_s: requests.Session, name: str,
                 complete_url: str, screen_out_url: str,
                 quota_full_url: str, quality_control_url: str) -> dict:
    payload = {
        "name":       name,
        "complete":   complete_url,
        "screen_out": screen_out_url,
        "quota_full": quota_full_url,
        "quality_control": quality_control_url,
        "appendSystemVariables": False,
        "config": {
            "type": "third_party",
            "appendSystemVariables": False,
            "messages": {
                "cp": "Obrigado por participar da pesquisa!",
                "so": "Obrigado pelo interesse. Infelizmente você não qualifica para esta pesquisa.",
                "qf": "Obrigado pelo interesse. A quota desta pesquisa já foi atingida.",
                "qc": "Detectamos um problema com as suas respostas. Obrigado pela participação.",
                "out_of_codes": "Todos os códigos de recompensa foram utilizados.",
            },
            "enableSendingEmailReward": False,
            "banner_image": "",
            "color_theme":  "rose",
        },
    }
    r = fluent_s.post(
        f"{FLUENT_URL}/surveys/{SURVEY_UUID}/redirects/store",
        json=payload,
        headers=hdrs(fluent_s, FLUENT_URL),
        timeout=20,
    )
    if r.status_code not in (200, 201):
        die(f"Erro ao criar panel '{name}': {r.status_code}\n{r.text[:400]}")
    log(f"✓ Panel criado: {name}", 2)
    return r.json()

# ─────────────────────────────────────────────────────────────────────────────
# OPERAÇÕES NO EXPRESS
# ─────────────────────────────────────────────────────────────────────────────
def create_question(express_s: requests.Session, q_code: str, q: dict) -> dict:
    r = express_s.post(
        f"{EXPRESS_URL}/survey/{q_code}/questions/store",
        json=q,
        headers=hdrs(express_s, EXPRESS_URL),
        timeout=20,
    )
    if r.status_code not in (200, 201):
        die(f"Erro ao criar questão em {q_code}: {r.status_code}\n{r.text[:400]}")
    label = q.get("question", "")[:60].replace("<p>", "").replace("</p>", "")
    log(f"  + Questão: {label}", 3)
    time.sleep(0.15)
    return r.json()

# ─────────────────────────────────────────────────────────────────────────────
# OPERAÇÕES NO ACT
# ─────────────────────────────────────────────────────────────────────────────
def create_test(act_s: requests.Session, survey_id: int, test: dict) -> dict:
    r = act_s.post(
        f"{ACT_URL}/tests/{survey_id}/store",
        json=test,
        headers=hdrs(act_s, ACT_URL),
        timeout=20,
    )
    if r.status_code not in (200, 201):
        die(f"Erro ao criar test ACT (survey={survey_id}): {r.status_code}\n{r.text[:400]}")
    title = test.get("config", {}).get("title", "test")
    log(f"  + Test ACT: {title or '(sem título)'}", 3)
    time.sleep(0.15)
    return r.json()

# ─────────────────────────────────────────────────────────────────────────────
# BUILDERS: setups e choices
# ─────────────────────────────────────────────────────────────────────────────
def setup_descriptive():
    return {
        "layout": 1,
        "layout_img": {"src": None, "width": "40vmin", "height": "40vmin",
                       "image_dimension_enabler": False},
        "layout_border_enabler": False,
        "btn_delay": 0, "btn_autoNext": 0,
        "btn_delay_enabled": False, "btn_autoNext_enabled": False,
        "advanceSkiplogic": {"enter": [], "leave": []},
        "advanceSkiplogic2": {"enter": [], "leave": []},
        "boxStyle": {"size": "md", "max-width": "70vmin",
                     "max-width-tab": "100%", "max-width-mobile": "100%",
                     "max-width_enabler": False},
        "dataType": [], "questionName": "",
    }

def setup_text_selection(multiple=False):
    return {
        "textSelection": {"layout_switch": 0, "grid": 1, "grid_tab": 1, "grid_mobile": 1,
                          "multiSelect_type": 1, "multiSelect_max": None, "multiSelect_min": None},
        "selectMultiple": 1 if multiple else 0,
        "randomChoices": [], "unSelectAll": [], "selectAll": [],
        "isDropdown": 0, "grid": 1, "grid_tab": 1, "grid_mobile": 1,
        "validate": {"required": 1, "min": 0, "max": 0,
                     "errorMsg": "Esta pergunta precisa de uma resposta"},
        "skiplogic": [], "customSkiplogic": {"enter": None, "leave": None},
        "advanceSkiplogic": {"enter": [], "leave": []},
        "advanceSkiplogic2": {"enter": [], "leave": []},
        "boxStyle": {"size": "md", "max-width": "70vmin",
                     "max-width-tab": "100%", "max-width-mobile": "100%"},
        "dataType": [], "questionName": "",
    }

def setup_single_textbox():
    return {
        "textBox": {"layout_switch": 0, "layout_desktop": 1,
                    "layout_mobile": 1, "layout_tab": 1},
        "validate": {"required": 1, "min": 16, "max": 120,
                     "errorMsg": "Por favor, informe sua idade (entre 16 e 120)"},
        "skiplogic": [], "customSkiplogic": {"enter": None, "leave": None},
        "advanceSkiplogic": {"enter": [], "leave": []},
        "advanceSkiplogic2": {"enter": [], "leave": []},
        "boxStyle": {"size": "md", "max-width": "30vmin",
                     "max-width-tab": "100%", "max-width-mobile": "100%"},
        "dataType": [], "questionName": "",
    }

def setup_segmentation(stmt_a: str, stmt_b: str):
    return {
        "labels": {
            "statementA": f"<p>{stmt_a}</p>",
            "statementB": f"<p>{stmt_b}</p>",
        },
        "default": 3,
        "randomItems": [],
        "validate": {"required": 1, "errorMsg": "Esta pergunta precisa de uma resposta"},
        "skiplogic": [], "customSkiplogic": {"enter": None, "leave": None},
        "advanceSkiplogic": {"enter": [], "leave": []},
        "advanceSkiplogic2": {"enter": [], "leave": []},
        "boxStyle": {"max-width_enabler": 0, "size": "md", "max-width": "100%",
                     "max-width-tab": "100%", "max-width-mobile": "100%"},
        "dataType": [], "questionName": "",
    }

def mk_choice(name: str, score: int = 0, index: int = 1, equivalent: str = "") -> dict:
    return {
        "name": f"<p>{name}</p>",
        "equivalent": equivalent or name,
        "enable_wr": 0,
        "CUUID": cuuid(),
        "index": index,
        "score": score,
        "points": 0,
        "locked": False,
        "checkboxScore": {"active": 1, "inactive": 0},
    }

def mk_choices(opts: list) -> list:
    """opts = [(name, score)] ou [(name, score, equivalent)]"""
    result = []
    for i, opt in enumerate(opts, 1):
        name, score = opt[0], opt[1]
        equiv = opt[2] if len(opt) > 2 else name
        result.append(mk_choice(name, score, i, equiv))
    return result

def q_express(question_pt: str, q_type_id: int, setup: dict,
              choices=None, items=None, rows=None, columns=None, values=None) -> dict:
    return {
        "question": f"<p>{question_pt}</p>",
        "question_type_id": q_type_id,
        "setup": setup,
        "choices": choices or [],
        "items":   items   or [],
        "rows":    rows    or [],
        "columns": columns or [],
        "values":  values  or [],
    }

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS ACT
# ─────────────────────────────────────────────────────────────────────────────
def mk_target(text: str, idx: int, batch: int = 1) -> dict:
    return {
        "target":        f"<p>{text}</p>",
        "equivalent":    text,
        "index":         idx,
        "batch":         batch,
        "can_unselect":  False,
        "value":         1,
        "colors":        {"normal": "", "hover": "", "active": ""},
        "properties":    {"bg": ""},
        "rawTargetElement": text,
    }

def mk_prime(text: str, idx: int = 1) -> dict:
    return {
        "prime":      f"<p>{text}</p>",
        "equivalent": text,
        "index":      idx,
        "display":    True,
        "config":     {"conditions": []},
    }

def act_config(title="", main_trial=True, practice_trial=False, dummy_trial=False,
               main_header="", prime_header="", display_by=4, random=True,
               single_select=False, auto_next=False) -> dict:
    return {
        "title":                title,
        "main_trial":           main_trial,
        "practice_trial":       practice_trial,
        "dummy_trial":          dummy_trial,
        "main_header":          main_header,
        "main_header_timeout":  0,
        "prime_header":         prime_header,
        "random":               random,
        "random_prime":         False,
        "random_prime_subsets": False,
        "prime_as_next":        False,
        "display_by":            display_by,
        "single_select":        single_select,
        "auto_next":            auto_next,
        "limit":                0,
        "bottom_text":          "",
        "empty_selection":      "Selecione pelo menos uma opção",
        "conditions":           [],
        "macros":               [],
        "trial_unselect":       False,
        "trial_unselect_label": "",
        "type":                 "trial" if (main_trial or practice_trial) else "descriptive",
        "theme":                1,
        "css":                  "",
        "js":                   "",
        "styles":               {},
    }

def act_test(config: dict, primes: list, targets: list) -> dict:
    return {"config": config, "primes": primes, "targets": targets}

# ─────────────────────────────────────────────────────────────────────────────
# DADOS DA PESQUISA — PART A (EXPRESS) Screener + Demographics
# ─────────────────────────────────────────────────────────────────────────────
BAIRROS = [
    # (nome, adm_zone)
    ("Jatiúca", 1), ("Pajuçara", 1), ("Poço", 1), ("Ponta da Terra", 1), ("Ponta Verde", 1),
    ("Centro", 2), ("Levada", 2), ("Mangabeiras", 2), ("Ponta Grossa", 2),
    ("Pontal da Barra", 2), ("Prado", 2), ("Trapiche da Barra", 2), ("Vergel do Lago", 2),
    ("Canaã", 3), ("Farol", 3), ("Gruta de Lourdes", 3), ("Jardim Petrópolis", 3),
    ("Ouro Preto", 3), ("Pinheiro", 3), ("Pitanguinha", 3),
    ("Bom Parto", 4), ("Chã da Jaqueira", 4), ("Chã de Bebedouro", 4),
    ("Fernão Velho", 4), ("Petrópolis", 4), ("Rio Novo", 4), ("Santa Amélia", 4),
    ("Barro Duro", 5), ("Feitosa", 5), ("Jacintinho", 5), ("São Jorge", 5), ("Serraria", 5),
    ("Antares", 6), ("Benedito Bentes", 6),
    ("Cidade Universitária", 7), ("Clima Bom", 7), ("Santa Lúcia", 7),
    ("Santos Dumont", 7), ("Tabuleiro do Martins", 7),
    ("Cruz das Almas", 8), ("Garça Torta", 8), ("Guaxuma", 8),
    ("Ipioca", 8), ("Jacarecica", 8), ("Pescaria", 8), ("Riacho Doce", 8),
]

def part_a_questions():
    qs = []
    # A1 - Welcome
    qs.append(q_express(
        "Obrigado por concordar em participar desta pesquisa, que durará cerca de 10 minutos. "
        "Todas as perguntas marcadas com * são obrigatórias. Você está pronto para continuar?",
        2, setup_text_selection(),
        choices=mk_choices([("Sim", 1, "Yes"), ("Não", 0, "No")])
    ))
    # A2 - Bairro
    qs.append(q_express(
        "Em qual bairro de Maceió você mora?",
        2, setup_text_selection(),
        choices=mk_choices([(b, z, b) for b, z in BAIRROS])
    ))
    # A3 - Sexo
    qs.append(q_express(
        "Qual era o seu sexo atribuído ao nascer (de acordo com a certidão de nascimento)?",
        2, setup_text_selection(),
        choices=mk_choices([
            ("Masculino", 1, "Male"),
            ("Feminino", 2, "Female"),
            ("Outro / Prefiro não responder", 0, "Other"),
        ])
    ))
    # A4 - Idade
    qs.append(q_express(
        "Por favor, digite a sua idade. [___] anos",
        4, setup_single_textbox()
    ))
    # A5 - Ocupação
    qs.append(q_express(
        "Você trabalha em qual tipo de ocupação hoje?",
        2, setup_text_selection(),
        choices=mk_choices([
            ("Trabalho em órgão público (prefeitura, estado ou governo federal)", 1, "Public sector"),
            ("Trabalho registrado em empresa privada", 2, "Private sector employed"),
            ("Trabalho por conta própria ou como freelancer", 3, "Self-employed/Freelancer"),
            ("Sou dono(a) de negócio ou gerente", 4, "Business owner/Manager"),
            ("Trabalho informal (ex: ambulante, bico, feira)", 5, "Informal worker"),
            ("Estudo (sou estudante)", 6, "Student"),
            ("Estou desempregado(a)", 7, "Unemployed"),
            ("Sou aposentado(a)", 8, "Retired"),
            ("Cuido da casa (sem salário)", 9, "Homemaker"),
            ("Prefiro não responder", 0, "Prefer not to say"),
        ])
    ))
    # A6 - Religião
    qs.append(q_express(
        "Qual é a sua religião?",
        2, setup_text_selection(),
        choices=mk_choices([
            ("Católico(a)", 1, "Catholic"),
            ("Evangélico(a) (Assembleia de Deus, Batista ou outras)", 2, "Evangelical"),
            ("Espírita (Kardecista)", 3, "Spiritist"),
            ("Umbanda / Candomblé / Religiões afro-brasileiras", 4, "Afro-Brazilian"),
            ("Ateu / Agnóstico / Não tem religião", 5, "Atheist/Agnostic"),
            ("Outra religião", 6, "Other religion"),
            ("Prefiro não responder", 0, "Prefer not to say"),
        ])
    ))
    return qs

# ─────────────────────────────────────────────────────────────────────────────
# PART B (EXPRESS) – Status Social (Critério Brasil)
# ─────────────────────────────────────────────────────────────────────────────
def part_b_questions():
    qs = []
    scoring_goods = [
        ("banheiros de uso exclusivo da família", "banheiros"),
        ("empregados domésticos mensalistas", "empregados domésticos"),
        ("carros de passeio disponíveis para uso da família", "carros"),
        ("notebooks ou computadores de mesa", "computadores"),
        ("máquinas de lavar roupa", "máquinas de lavar"),
        ("geladeiras", "geladeiras"),
        ("freezers (independentes da geladeira)", "freezers"),
        ("fornos de micro-ondas", "micro-ondas"),
        ("lava-louças", "lava-louças"),
        ("motocicletas (não usadas exclusivamente para trabalho)", "motos"),
        ("secadoras de roupa", "secadoras"),
        ("aparelhos de DVD", "DVDs"),
    ]
    scores_table = [
        [0, 3, 7, 10, 14],   # B1 banheiros
        [0, 3, 7, 10, 13],   # B2 empregados
        [0, 3, 5, 8, 11],    # B3 carros
        [0, 3, 6, 8, 11],    # B4 computadores
        [0, 2, 4, 6, 6],     # B5 máq. lavar
        [0, 2, 3, 5, 5],     # B6 geladeiras
        [0, 2, 4, 6, 6],     # B7 freezers
        [0, 2, 4, 4, 4],     # B8 micro-ondas
        [0, 3, 6, 6, 6],     # B9 lava-louças
        [0, 1, 3, 3, 3],     # B10 motos
        [0, 2, 2, 2, 2],     # B11 secadoras
        [0, 1, 3, 4, 6],     # B12 DVDs
    ]
    count_opts = ["0 (nenhum)", "1", "2", "3", "4 ou mais"]
    for i, (desc, label) in enumerate(scoring_goods):
        sc = scores_table[i]
        qs.append(q_express(
            f"Quantos(as) {desc} há em sua residência?",
            2, setup_text_selection(),
            choices=mk_choices([(count_opts[j], sc[j], count_opts[j]) for j in range(5)])
        ))

    # B13 – Rua asfaltada
    qs.append(q_express(
        "A rua onde você mora é pavimentada (asfaltada)?",
        2, setup_text_selection(),
        choices=mk_choices([("Não", 0, "No"), ("Sim", 2, "Yes")])
    ))
    # B14 – Água encanada
    qs.append(q_express(
        "Onde você mora possui abastecimento de água encanada?",
        2, setup_text_selection(),
        choices=mk_choices([("Não", 0, "No"), ("Sim", 4, "Yes")])
    ))
    # B15 – Escolaridade do chefe da família
    qs.append(q_express(
        "Qual é o nível de escolaridade mais alto do chefe da família?",
        2, setup_text_selection(),
        choices=mk_choices([
            ("Ensino Fundamental (incompleto)", 0, "Primary incomplete"),
            ("Ensino Fundamental (completo)", 1, "Primary complete"),
            ("Ensino Médio (incompleto)", 2, "Secondary incomplete"),
            ("Ensino Médio (completo)", 4, "Secondary complete"),
            ("Ensino Superior (incompleto)", 4, "Higher incomplete"),
            ("Ensino Superior (completo)", 7, "Higher complete"),
            ("Pós-graduação ou mais", 7, "Postgraduate+"),
        ])
    ))
    # B16 – Lateralidade (necessário para instrução do ACT)
    qs.append(q_express(
        "A partir de agora você vai responder perguntas rápidas. "
        "Antes de continuar: você é canhoto(a) ou destro(a)?",
        2, setup_text_selection(),
        choices=mk_choices([("Sou canhoto(a)", 1, "Left-handed"), ("Sou destro(a)", 2, "Right-handed")])
    ))
    return qs

# ─────────────────────────────────────────────────────────────────────────────
# PART C (ACT) – Supermodelo de Personalidade do político ideal
# ─────────────────────────────────────────────────────────────────────────────
PERSONALITY_DIMS = [
    ("Cuidado",      ["Atencioso", "Guardião", "Protetor", "Cuidadoso"]),
    ("Confiança",    ["Transparente", "Honesto", "Confiável", "Honrado"]),
    ("Carisma",      ["Carismático", "Simpático", "Envolvente", "Elegante"]),
    ("Influência",   ["Influente", "Confiante", "Respeitado", "Visionário"]),
    ("Proximidade",  ["Humilde", "Acessível", "Simples", "Solidário"]),
    ("Competência",  ["Experiente", "Trabalhador", "Inteligente", "Responsável"]),
    ("Coragem",      ["Corajoso", "Persistente", "Guerreiro", "Provocador"]),
    ("Firmeza",      ["Firme", "Resolvedor", "Decidido", "Defensor"]),
]
PRIME_IDEAL_PERSONALITY = "Para mim, o prefeito ideal deve ser…"

def build_personality_tests(prime_text: str) -> list:
    tests = []
    # Instrução descritiva
    tests.append(act_test(
        act_config(
            title="Instrução",
            main_trial=False, dummy_trial=True,
            main_header=(
                "Nesta parte, queremos que você imagine seu político ideal — "
                "especialmente as qualidades pessoais que ele deveria ter. "
                "Você fará algumas rodadas de treino e em seguida 8 rodadas valendo. "
                "Responda rápido e de forma espontânea."
            ),
        ),
        primes=[], targets=[]
    ))
    # Treino (prática com 4 atributos misturados)
    practice_targets = [
        mk_target(t, i+1, 1)
        for i, t in enumerate(["Honesto", "Corajoso", "Simpático", "Trabalhador"])
    ]
    tests.append(act_test(
        act_config(
            title="Treino",
            main_trial=False, practice_trial=True,
            main_header="Complete a frase com o que você acha que o prefeito ideal deveria ser. Selecione quantas opções quiser.",
            prime_header=prime_text,
            display_by=4, random=False,
        ),
        primes=[mk_prime(prime_text)],
        targets=practice_targets,
    ))
    # 8 rounds principais (1 por dimensão)
    for dim_name, attributes in PERSONALITY_DIMS:
        targets = [mk_target(a, i+1, 1) for i, a in enumerate(attributes)]
        tests.append(act_test(
            act_config(
                title=f"Dimensão: {dim_name}",
                main_trial=True, practice_trial=False,
                main_header="Complete a frase com o que você acha que o prefeito ideal deveria ser. Selecione quantas opções quiser.",
                prime_header=prime_text,
                display_by=4, random=True,
            ),
            primes=[mk_prime(prime_text)],
            targets=targets,
        ))
    return tests

# ─────────────────────────────────────────────────────────────────────────────
# PART D (EXPRESS) – Supermodelo de Moral
# ─────────────────────────────────────────────────────────────────────────────
MORAL_DIMS = [
    # (titulo, stmt_A_pt, stmt_B_pt)
    ("Cuidado x Firmeza",
     "Se preocupa em proteger as pessoas mostrando cuidado e empatia.",
     "Acredita que para proteger a população é preciso ser firme e aplicar punições mais duras."),
    ("Igualdade vs Mérito",
     "Acredita que as regras devem ser seguidas, mesmo que atrapalhe às vezes o bem de todos.",
     "Acredita que as regras nem sempre precisam ser seguidas ao pé da letra, se for para o bem de todos."),
    ("Tradição vs Diversidade",
     "Toma decisões alinhadas ao seu grupo (eleitores, partido ou aliados), seguindo o que eles defendem.",
     "Toma decisões por conta própria, mesmo quando não refletem totalmente a posição do grupo."),
    ("Ordem vs Questionamento",
     "Acredita que respeitar regras e autoridades garante ordem.",
     "Acredita que questionar autoridades pode trazer mudanças boas."),
    ("Moral vs Liberdade",
     "Valoriza costumes culturais, religiosos e morais.",
     "Defende que cada pessoa viva como quiser."),
    ("Liberdade vs Igualdade",
     "Defende mais liberdade individual e menos interferência do governo.",
     "Defende que o governo deve ter papel forte para proteger os cidadãos."),
    ("Propriedade vs Redistribuição",
     "Defende que empresas privadas cuidem dos serviços públicos.",
     "Defende que o governo participe e regule os serviços públicos."),
    ("Transparência vs Pragmatismo",
     "Prefere ser direto e transparente, mesmo quando isso pode desagradar.",
     "Prefere ser mais cuidadoso ao falar, evitando situações que possam gerar desconforto."),
]

def part_d_questions(candidate_a="Político A", candidate_b="Político B"):
    qs = []
    # D0 – Intro descritiva
    qs.append(q_express(
        "Nesta parte queremos que você pense nos valores morais que um político deveria ter. "
        "Leia as frases do Político A e do Político B e escolha qual deles você apoiaria mais.",
        1, setup_descriptive()
    ))
    # D1–D8
    for title, stmt_a, stmt_b in MORAL_DIMS:
        qs.append(q_express(
            "Qual desses políticos você apoiaria para Prefeito de Maceió?",
            16,
            setup_segmentation(
                f"<strong>{candidate_a}</strong><br>{stmt_a}",
                f"<strong>{candidate_b}</strong><br>{stmt_b}",
            ),
        ))
    return qs

# ─────────────────────────────────────────────────────────────────────────────
# PART E (ACT) – Supermodelo de Políticas Públicas
# ─────────────────────────────────────────────────────────────────────────────
POLICY_GROUPS = [
    ("Mobilidade e Infraestrutura", [
        "Baixar o preço das passagens de ônibus",
        "Colocar mais ônibus circulando na cidade",
        "Tapar os buracos das ruas",
        "Resolver o esgoto que corre nas ruas",
        "Melhorar a iluminação das ruas e praças",
        "Melhorar o trânsito",
        "Abrir mais vias ligando os bairros da parte alta à praia",
        "Melhorar o atendimento e os serviços da prefeitura",
    ]),
    ("Meio Ambiente e Lazer", [
        "Deixar a cidade mais limpa",
        "Limpar e cuidar do riacho Salgadinho",
        "Reformar e construir mais praças e parques",
        "Deixar a orla bonita e moderna",
        "Cuidar mais das praias da cidade",
        "Cuidar das grotas e comunidades carentes",
        "Construir campinhos de futebol (areninha)",
        "Aumentar a segurança nas ruas e bairros",
    ]),
    ("Saúde, Educação e Emprego", [
        "Construir postos de saúde e hospitais",
        "Garantir remédio gratuito para quem precisa",
        "Melhorar o atendimento nos postos de saúde",
        "Mais consultas e exames",
        "Melhorar as escolas",
        "Garantir merenda boa nas escolas",
        "Construir mais creches",
        "Criar mais empregos",
    ]),
]
PRIME_IDEAL_POLICY = "Para mim, o prefeito ideal deveria trabalhar para…"

def build_policy_tests(prime_text: str) -> list:
    tests = []
    # Instrução
    tests.append(act_test(
        act_config(
            title="Instrução",
            main_trial=False, dummy_trial=True,
            main_header=(
                "Nesta parte, queremos que você pense no que o prefeito ideal deveria fazer "
                "para melhorar a vida das pessoas em Maceió. "
                "Responda rápido e de forma espontânea."
            ),
        ),
        primes=[], targets=[]
    ))
    # Treino
    practice_tgts = [mk_target(t, i+1, 1) for i, t in enumerate([
        "Melhorar as escolas", "Criar mais empregos",
        "Melhorar o trânsito", "Cuidar mais das praias",
    ])]
    tests.append(act_test(
        act_config(
            title="Treino",
            main_trial=False, practice_trial=True,
            main_header="O que o prefeito ideal deveria fazer? Selecione quantas opções quiser.",
            prime_header=prime_text,
            display_by=4, random=False,
        ),
        primes=[mk_prime(prime_text)],
        targets=practice_tgts,
    ))
    # 3 rounds (1 por grupo temático)
    for group_name, policies in POLICY_GROUPS:
        targets = [mk_target(p, i+1, 1) for i, p in enumerate(policies)]
        tests.append(act_test(
            act_config(
                title=f"Políticas: {group_name}",
                main_trial=True,
                main_header="O que o prefeito ideal deveria fazer? Selecione quantas opções quiser.",
                prime_header=prime_text,
                display_by=4, random=True,
            ),
            primes=[mk_prime(prime_text)],
            targets=targets,
        ))
    return tests

# ─────────────────────────────────────────────────────────────────────────────
# PART F (EXPRESS) – Percepção do prefeito atual + awareness
# ─────────────────────────────────────────────────────────────────────────────
POLITICIANS = [
    ("JHC — João Henrique Caldas (Prefeito de Maceió)", "JHC"),
    ("Rodrigo Cunha (Senador)", "Rodrigo Cunha"),
    ("Paulo Dantas (Governador de Alagoas)", "Paulo Dantas"),
    ("Renan Calheiros (Senador)", "Renan Calheiros"),
    ("Renan Filho (Senador)", "Renan Filho"),
    ("Arthur Lira (Ex-presidente da Câmara)", "Arthur Lira"),
    ("Lula (Presidente da República)", "Lula"),
    ("Bolsonaro (Ex-presidente)", "Bolsonaro"),
]

def part_f_questions():
    qs = []
    # F1 – Awareness (múltipla escolha múltipla)
    setup_f1 = setup_text_selection(multiple=True)
    setup_f1["selectMultiple"] = 1
    qs.append(q_express(
        "Quais dos seguintes políticos você conhece, mesmo que apenas de nome? "
        "Selecione todos os que conhecer.",
        2, setup_f1,
        choices=mk_choices([(name, i+1, code) for i, (name, code) in enumerate(POLITICIANS)])
    ))
    # F2 – Aprovação JHC
    qs.append(q_express(
        "De forma geral, como você avalia o desempenho de JHC como Prefeito de Maceió?",
        2, setup_text_selection(),
        choices=mk_choices([
            ("Muito bom", 5, "Very good"), ("Bom", 4, "Good"),
            ("Regular", 3, "Fair"), ("Ruim", 2, "Poor"),
            ("Muito ruim", 1, "Very poor"), ("Não sei / Não tenho opinião", 0, "Don't know"),
        ])
    ))
    # F3 – Reeleição JHC
    qs.append(q_express(
        "JHC deveria se candidatar à reeleição como Prefeito de Maceió?",
        2, setup_text_selection(),
        choices=mk_choices([
            ("Sim, com certeza", 3, "Definitely yes"),
            ("Sim, talvez", 2, "Maybe yes"),
            ("Não", 1, "No"),
            ("Não sei", 0, "Don't know"),
        ])
    ))
    # F4 – Aprovação Rodrigo Cunha
    qs.append(q_express(
        "Como você avalia o desempenho de Rodrigo Cunha como Senador?",
        2, setup_text_selection(),
        choices=mk_choices([
            ("Muito bom", 5, "Very good"), ("Bom", 4, "Good"),
            ("Regular", 3, "Fair"), ("Ruim", 2, "Poor"),
            ("Muito ruim", 1, "Very poor"), ("Não sei / Não tenho opinião", 0, "Don't know"),
        ])
    ))
    # F5 – Candidatura Rodrigo para Prefeito
    qs.append(q_express(
        "Rodrigo Cunha deveria se candidatar a Prefeito de Maceió?",
        2, setup_text_selection(),
        choices=mk_choices([
            ("Sim, com certeza", 3, "Definitely yes"),
            ("Sim, talvez", 2, "Maybe yes"),
            ("Não", 1, "No"),
            ("Não sei", 0, "Don't know"),
        ])
    ))
    return qs

# ─────────────────────────────────────────────────────────────────────────────
# PART G (EXPRESS) – Comportamento de voto
# ─────────────────────────────────────────────────────────────────────────────
def part_g_questions():
    qs = []
    # G1 – Intenção de voto para Prefeito
    qs.append(q_express(
        "Se as eleições para Prefeito de Maceió fossem hoje e os candidatos fossem "
        "JHC e Rodrigo Cunha, em quem você votaria?",
        2, setup_text_selection(),
        choices=mk_choices([
            ("JHC", 1, "JHC"),
            ("Rodrigo Cunha", 2, "Rodrigo Cunha"),
            ("Votaria em branco / Nulo", 3, "Blank/Null"),
            ("Não votaria", 4, "Would not vote"),
            ("Não sei ainda", 0, "Don't know yet"),
        ])
    ))
    # G2 – Voto passado (2024)
    qs.append(q_express(
        "Nas últimas eleições municipais de 2024, em quem você votou para Prefeito de Maceió?",
        2, setup_text_selection(),
        choices=mk_choices([
            ("JHC — João Henrique Caldas", 1, "JHC"),
            ("Outro candidato", 2, "Other"),
            ("Votei em branco / Nulo", 3, "Blank/Null"),
            ("Não votei", 4, "Did not vote"),
            ("Não lembro / Prefiro não dizer", 0, "Don't remember"),
        ])
    ))
    # G3 – Fator decisivo de voto
    qs.append(q_express(
        "O que mais influencia o seu voto na escolha do Prefeito?",
        2, setup_text_selection(),
        choices=mk_choices([
            ("O histórico de realizações do candidato", 1, "Track record"),
            ("As propostas e planos do candidato", 2, "Proposals"),
            ("A personalidade e caráter do candidato", 3, "Character"),
            ("A indicação de pessoas de confiança", 4, "Recommendation"),
            ("O partido político do candidato", 5, "Party"),
            ("Outros motivos", 0, "Other"),
        ])
    ))
    return qs

# ─────────────────────────────────────────────────────────────────────────────
# PARTS H/K (ACT) – Capital Político: Personalidade dos candidatos
# ─────────────────────────────────────────────────────────────────────────────
def build_candidate_personality_tests(candidate_name: str) -> list:
    prime_text = f"{candidate_name} é um político que pode ser descrito como…"
    return build_personality_tests(prime_text)

# ─────────────────────────────────────────────────────────────────────────────
# PARTS I/L (EXPRESS) – Capital Político: Moral dos candidatos
# ─────────────────────────────────────────────────────────────────────────────
def part_moral_candidate_questions(candidate_name: str):
    return part_d_questions(
        candidate_a=f"{candidate_name} — Posição A",
        candidate_b=f"{candidate_name} — Posição B",
    )

# ─────────────────────────────────────────────────────────────────────────────
# PARTS J/M (ACT) – Capital Político: Políticas dos candidatos
# ─────────────────────────────────────────────────────────────────────────────
def build_candidate_policy_tests(candidate_name: str) -> list:
    prime_text = f"{candidate_name} se preocupa em…"
    return build_policy_tests(prime_text)

# ─────────────────────────────────────────────────────────────────────────────
# PART N (EXPRESS) – Feedback do questionário
# ─────────────────────────────────────────────────────────────────────────────
def part_n_questions():
    qs = []
    qs.append(q_express(
        "Com que facilidade você conseguiu completar esta pesquisa?",
        2, setup_text_selection(),
        choices=mk_choices([
            ("Muito fácil", 5, "Very easy"), ("Fácil", 4, "Easy"),
            ("Nem fácil nem difícil", 3, "Neutral"),
            ("Difícil", 2, "Difficult"), ("Muito difícil", 1, "Very difficult"),
        ])
    ))
    qs.append(q_express(
        "As perguntas foram claras e fáceis de entender?",
        2, setup_text_selection(),
        choices=mk_choices([
            ("Sim, todas foram claras", 3, "All clear"),
            ("A maioria foi clara", 2, "Most clear"),
            ("Algumas foram confusas", 1, "Some confusing"),
            ("Muitas foram confusas", 0, "Many confusing"),
        ])
    ))
    qs.append(q_express(
        "Você ficaria disponível para participar de pesquisas futuras?",
        2, setup_text_selection(),
        choices=mk_choices([
            ("Sim, com certeza", 3, "Definitely yes"),
            ("Talvez", 2, "Maybe"),
            ("Não", 1, "No"),
        ])
    ))
    return qs

# ─────────────────────────────────────────────────────────────────────────────
# BREAKOUT GROUPS (quotas demográficas do script MT Maceió)
# ─────────────────────────────────────────────────────────────────────────────
# Nomes precisam ser alpha_dash (sem espaços, sem acentos, sem barras)

GROUPS_DATA = [
    {
        "name": "Gender",
        "is_for_analysis": True,
        "criteria": [
            mk_criterion("Female",  902),
            mk_criterion("Male",    738),
            mk_criterion("Others",  0),   # catch-all
        ],
    },
    {
        "name": "Age",
        "is_for_analysis": True,
        "criteria": [
            mk_criterion("16-24", 216),
            mk_criterion("25-34", 338),
            mk_criterion("35-44", 341),
            mk_criterion("45-59", 435),
            mk_criterion("60+",   310),
            mk_criterion("Others", 0),
        ],
    },
    {
        "name": "Region",
        "is_for_analysis": True,
        "criteria": [
            mk_criterion("Adm-Zone-1", 172),
            mk_criterion("Adm-Zone-2", 179),
            mk_criterion("Adm-Zone-3", 102),
            mk_criterion("Adm-Zone-4", 143),
            mk_criterion("Adm-Zone-5", 261),
            mk_criterion("Adm-Zone-6", 241),
            mk_criterion("Adm-Zone-7", 461),
            mk_criterion("Adm-Zone-8",  80),
            mk_criterion("Others",       0),
        ],
    },
    {
        # Critério Brasil → classes socioeconômicas (quotas estimadas)
        "name": "Social-Class",
        "is_for_analysis": True,
        "criteria": [
            mk_criterion("Class-A",   80),
            mk_criterion("Class-B1", 200),
            mk_criterion("Class-B2", 400),
            mk_criterion("Class-C1", 450),
            mk_criterion("Class-C2", 350),
            mk_criterion("Class-D-E",160),
            mk_criterion("Others",     0),
        ],
    },
    {
        # Awareness política — alimentado pela Bridge após a Part F (Q F1)
        # Index 1=JHC, 2=Rodrigo, 3=Both, 4=None
        # Stations 6 e 7 filtram por este grupo
        # is_for_analysis=False → não aparece como breakout no wizard de Analysis
        "name": "politician-awareness",
        "is_for_analysis": False,
        "criteria": [
            mk_criterion("JHC",            0),
            mk_criterion("Rodrigo-Cunha",  0),
            mk_criterion("Both",           0),
            mk_criterion("None",           0),
        ],
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# REDIRECTS (Panel padrão)
# Para teste local, usa URLs simples. Em produção, trocar pelas reais (SSR/Samplicio).
# ─────────────────────────────────────────────────────────────────────────────
PANEL_DEFAULT = {
    "name":                "SSR",
    "complete_url":        "http://127.0.0.1:8000/display/complete/?survey_code=RiqNil&id=$id",
    "screen_out_url":      "http://127.0.0.1:8000/display/screenOut/?survey_code=RiqNil&id=$id",
    "quota_full_url":      "http://127.0.0.1:8000/display/quotaFull/?survey_code=RiqNil&id=$id",
    "quality_control_url": "http://127.0.0.1:8000/display/qualityControl/?survey_code=RiqNil&id=$id",
}

# ─────────────────────────────────────────────────────────────────────────────
# DEFINIÇÃO COMPLETA DAS 14 PARTES
# ─────────────────────────────────────────────────────────────────────────────
PARTS = [
    {"name": "Part A - Screener & Demographics", "variable": "A",
     "type": "express", "questions": part_a_questions()},

    {"name": "Part B - Social Status (Critério Brasil)", "variable": "B",
     "type": "express", "questions": part_b_questions()},

    {"name": "Part C - Personality Supermodel", "variable": "C",
     "type": "act",     "tests": build_personality_tests(PRIME_IDEAL_PERSONALITY)},

    {"name": "Part D - Morals Supermodel", "variable": "D",
     "type": "express", "questions": part_d_questions()},

    {"name": "Part E - Policy Platform Supermodel", "variable": "E",
     "type": "act",     "tests": build_policy_tests(PRIME_IDEAL_POLICY)},

    {"name": "Part F - Perception of Current Mayor", "variable": "F",
     "type": "express", "questions": part_f_questions()},

    {"name": "Part G - Vote Behavior", "variable": "G",
     "type": "express", "questions": part_g_questions()},

    {"name": "Part H - JHC Personality Capital", "variable": "H",
     "type": "act",     "tests": build_candidate_personality_tests("JHC")},

    {"name": "Part I - JHC Morals Capital", "variable": "I",
     "type": "express", "questions": part_moral_candidate_questions("JHC")},

    {"name": "Part J - JHC Policy Capital", "variable": "J",
     "type": "act",     "tests": build_candidate_policy_tests("JHC")},

    {"name": "Part K - Rodrigo Cunha Personality Capital", "variable": "K",
     "type": "act",     "tests": build_candidate_personality_tests("Rodrigo Cunha")},

    {"name": "Part L - Rodrigo Cunha Morals Capital", "variable": "L",
     "type": "express", "questions": part_moral_candidate_questions("Rodrigo Cunha")},

    {"name": "Part M - Rodrigo Cunha Policy Capital", "variable": "M",
     "type": "act",     "tests": build_candidate_policy_tests("Rodrigo Cunha")},

    {"name": "Part N - Survey Feedback", "variable": "N",
     "type": "express", "questions": part_n_questions()},
]

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# REFACTOR DE STATIONS — espelha estrutura do sistema-irmão (8 stations)
# ─────────────────────────────────────────────────────────────────────────────
SURVEY_CODE = "RiqNil"   # code da survey no Fluent (URL do bridge usa isto)

def refactor_stations(fluent_s: requests.Session):
    """
    Apaga stations existentes e cria a estrutura de 8 stations:
      #1 Default → Part A
      #2 Default → Part B
      #3 Bridge  → script 1 (classificar demographics)
      #4 Default → Part C, D, E, F, G
      #5 Bridge  → script 2 (classificar awareness política)
      #6 Default → Part H, I, J   (filtro: politician-awareness ∈ {JHC, Both})
      #7 Default → Part K, L, M   (filtro: politician-awareness ∈ {Rodrigo-Cunha, Both})
      #8 Default → Part N
    """
    # 1. Apagar stations existentes (caller deve limpar via SQL antes — ver flag --refactor-stations)
    log("Pré-condição: stations existentes devem ter sido removidas via SQL pelo caller.", 1)

    # 2. Recolher componentes existentes (para extrair model.id de cada part)
    comps = get_components_from_db_via_api(fluent_s)
    if not comps:
        die("Nenhum componente encontrado. Crie os componentes primeiro.")

    by_var = {}
    for c in comps:
        cfg = c.get("config") or {}
        model = cfg.get("model") or {}
        mid = model.get("id") if isinstance(model, dict) else None
        by_var[c.get("variable")] = {"type": c.get("type"), "model_id": mid, "name": c.get("name")}

    def L(var, label_override=None):
        """Helper: cria station_link para a part `var`."""
        info = by_var.get(var)
        if not info or not info["model_id"]:
            die(f"Component '{var}' não encontrado ou sem model_id")
        return station_link(info["type"], info["model_id"], label_override or f"Part {var}")

    # Cells do grupo politician-awareness (1-based)
    # Index 1=JHC, 2=Rodrigo-Cunha, 3=Both, 4=None
    PA = "politician-awareness"

    # 3. Criar 8 stations
    log("Criando estrutura de 8 stations...", 1)

    # #1 — Part A
    create_station_multi(fluent_s, "Station 1 — Demographics", [L("A")])

    # #2 — Part B
    create_station_multi(fluent_s, "Station 2 — Social Status", [L("B")])

    # #3 — Bridge (classify demographics/class)
    create_station_multi(fluent_s, "Bridge 3 — Demo+Class classifier",
                         [station_link_bridge(SURVEY_CODE, 1, "Bridge: classify demo")],
                         station_type="bridge")

    # #4 — Parts C, D, E, F, G (ideal + perception + vote)
    create_station_multi(fluent_s, "Station 4 — Ideal + Perception",
                         [L("C"), L("D"), L("E"), L("F"), L("G")])

    # #5 — Bridge (classify politician-awareness from F1)
    create_station_multi(fluent_s, "Bridge 5 — Awareness classifier",
                         [station_link_bridge(SURVEY_CODE, 2, "Bridge: classify awareness")],
                         station_type="bridge")

    # #6 — Parts H, I, J — só para quem conhece JHC (cells 1 e 3 do PA: JHC e Both)
    create_station_multi(fluent_s, "Station 6 — JHC Capital",
                         [L("H"), L("I"), L("J")],
                         to_group_cells=[{"name": PA, "index": 1}, {"name": PA, "index": 3}])

    # #7 — Parts K, L, M — só para quem conhece Rodrigo (cells 2 e 3: Rodrigo e Both)
    create_station_multi(fluent_s, "Station 7 — Rodrigo Capital",
                         [L("K"), L("L"), L("M")],
                         to_group_cells=[{"name": PA, "index": 2}, {"name": PA, "index": 3}])

    # #8 — Part N (feedback final, todos)
    create_station_multi(fluent_s, "Station 8 — Feedback", [L("N")])

    log("✓ Refactor de stations completo.", 1)

def main():
    parser = argparse.ArgumentParser(description="Popula survey MT Maceió no Fluent")
    parser.add_argument("--fresh", action="store_true",
                        help="Apaga componentes existentes na survey antes de criar novos")
    parser.add_argument("--dry-run", action="store_true",
                        help="Apenas mostra o que seria criado, sem fazer chamadas reais")
    parser.add_argument("--no-stations", action="store_true",
                        help="Não cria stations após os componentes")
    parser.add_argument("--stations-only", action="store_true",
                        help="Cria apenas as stations para componentes já existentes")
    parser.add_argument("--no-extras", action="store_true",
                        help="Não cria groups/panels")
    parser.add_argument("--extras-only", action="store_true",
                        help="Cria apenas groups (quotas) e panels (redirects)")
    parser.add_argument("--refactor-stations", action="store_true",
                        help="Apaga stations atuais e cria a estrutura de 8 stations (com bridges + filtros)")
    args = parser.parse_args()

    print("\n══════════════════════════════════════════════════════════════")
    print("  MT Maceió – JHC e Rodrigo — Populador de Survey")
    print("══════════════════════════════════════════════════════════════\n")

    if args.dry_run:
        print("[DRY RUN] Listando o que seria criado:\n")
        for p in PARTS:
            tipo = p["type"].upper()
            items = len(p.get("questions", p.get("tests", [])))
            print(f"  {p['variable']}. {p['name']} ({tipo}) — {items} item(s)")
        print(f"\nTotal: {len(PARTS)} componentes")
        return

    # ── Login em todos os serviços ──────────────────────────────────────────
    print("1. Autenticando nos serviços...")
    fluent_s  = login(FLUENT_URL,  EMAIL, PASSWORD)
    express_s = login(EXPRESS_URL, EMAIL, PASSWORD)
    act_s     = login(ACT_URL,     EMAIL, PASSWORD)

    # ── Limpar componentes existentes (--fresh) ─────────────────────────────
    if args.fresh:
        print("\n2. Removendo componentes existentes (--fresh)...")
        existing = get_components(fluent_s)
        for comp in existing:
            cid = comp.get("id")
            cname = comp.get("name", "?")
            if cid:
                delete_component(fluent_s, cid)
                log(f"Removido: {cname} (id={cid})", 2)
        time.sleep(1)

    # ── Modo --refactor-stations: re-cria estrutura de 8 stations ───────────
    if args.refactor_stations:
        print("\n3. Refatorando stations para estrutura de 8 (multi-component + bridges + filtros)...\n")
        refactor_stations(fluent_s)
        print("\n✓ Refactor concluído.\n")
        return

    # ── Modo --extras-only: apenas groups + panels ──────────────────────────
    if args.extras_only:
        print("\n3. Criando Breakout Groups (quotas)...\n")
        for g in GROUPS_DATA:
            log(f"[Group] {g['name']}", 1)
            create_group(fluent_s, g["name"], g["criteria"],
                         is_for_analysis=g.get("is_for_analysis", True))
        print("\n4. Criando Panel (redirects)...\n")
        log(f"[Panel] {PANEL_DEFAULT['name']}", 1)
        create_panel(fluent_s, **PANEL_DEFAULT)
        print("\n✓ Groups e Panel criados.\n")
        return

    # ── Modo --stations-only: apenas cria stations para componentes existentes ─
    if args.stations_only:
        print("\n3. Criando stations para componentes já existentes...\n")
        comps = get_components_from_db_via_api(fluent_s)
        if not comps:
            die("Nenhum componente encontrado para criar stations. Crie os componentes primeiro.")
        # Ordena por 'part' para preservar a sequência A→N
        comps.sort(key=lambda c: c.get("part", 9999))
        for c in comps:
            ctype    = c.get("type", "")
            cname    = c.get("name", "?")
            cfg      = c.get("config") or {}
            model    = cfg.get("model") or {}
            mid      = model.get("id") if isinstance(model, dict) else None
            if not mid:
                log(f"⚠ Componente '{cname}' sem model.id — pulando", 1)
                continue
            log(f"[{c.get('variable','?')}] {cname}", 1)
            create_station(fluent_s, cname, ctype, mid, label=cname)
        print("\n✓ Stations criadas.\n")
        return

    # ── Criar componentes e popular ─────────────────────────────────────────
    print("\n3. Criando componentes e populando...\n")

    created_for_stations = []  # [(name, type, model_id), ...]

    for part in PARTS:
        pname    = part["name"]
        variable = part["variable"]
        ptype    = part["type"]
        log(f"[{variable}] {pname}", 1)

        # Criar componente no Fluent (Fluent chama Express/ACT internamente)
        comp_data = create_component(fluent_s, pname, ptype, variable)

        # Extrair o model.id (código do questionnaire Express ou ID do survey ACT)
        comp_obj  = comp_data.get("data", comp_data.get("component", comp_data))
        config    = comp_obj.get("config", {}) or {}
        model     = config.get("model") or {}
        model_id  = model.get("id") if isinstance(model, dict) else None

        if not model_id:
            log(f"⚠ model.id não encontrado na resposta. Resposta: {json.dumps(comp_data)[:300]}", 2)
            log("Pulando população deste componente.", 2)
            continue

        # Popular Express com perguntas
        if ptype == "express":
            q_code = str(model_id)
            questions = part.get("questions", [])
            log(f"Adicionando {len(questions)} questão(ões) ao questionnaire {q_code}...", 2)
            for q in questions:
                create_question(express_s, q_code, q)

        # Popular ACT com tests
        elif ptype == "act":
            act_survey_id = int(model_id)
            tests = part.get("tests", [])
            log(f"Adicionando {len(tests)} test(s) ao survey ACT {act_survey_id}...", 2)
            for t in tests:
                create_test(act_s, act_survey_id, t)

        created_for_stations.append((pname, ptype, model_id))
        log(f"✓ {pname} concluído\n", 1)
        time.sleep(0.3)

    # ── Criar stations para cada componente (na ordem) ──────────────────────
    if not args.no_stations:
        print("\n4. Criando stations (fluxo do respondente)...\n")
        for pname, ptype, mid in created_for_stations:
            create_station(fluent_s, pname, ptype, mid, label=pname)
            time.sleep(0.1)

    # ── Criar Breakout Groups (quotas) e Panel (redirects) ──────────────────
    if not args.no_extras:
        print("\n5. Criando Breakout Groups (quotas)...\n")
        for g in GROUPS_DATA:
            log(f"[Group] {g['name']}", 1)
            create_group(fluent_s, g["name"], g["criteria"],
                         is_for_analysis=g.get("is_for_analysis", True))

        print("\n6. Criando Panel (redirects)...\n")
        log(f"[Panel] {PANEL_DEFAULT['name']}", 1)
        create_panel(fluent_s, **PANEL_DEFAULT)

    print("\n══════════════════════════════════════════════════════════════")
    print("  ✓ Survey MT Maceió populada com sucesso!")
    print(f"  Acesse: {FLUENT_URL}/surveys/{SURVEY_ID}")
    print("══════════════════════════════════════════════════════════════\n")


if __name__ == "__main__":
    main()
