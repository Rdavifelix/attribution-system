# Attribution System v2
### GHL × Meta Ads × Planilha CRM → Dashboard de Atribuição de Funil

> Responde: **"qual anúncio gerou essa call e essa venda?"**

---

## Visão Geral

```
      GHL (UTM/ad_id)          Planilha de Leads (CRM)        Meta Ads (custo)
            │                           │                            │
            └───────────────────────────┼────────────────────────────┘
                                        ▼
                              [Backend Python/FastAPI]
                          ┌──────────────────────────────┐
                          │  1. Normaliza email/telefone  │
                          │  2. UPSERT leads              │
                          │  3. Unpivot → calls (1 e 2)  │
                          │  4. Aplica de-para            │
                          │  5. Deriva flags booleanas    │
                          │  6. Motor lead ↔ anúncio      │
                          └──────────────┬───────────────┘
                                         ▼
                                   [Supabase/Postgres]
                                         │
                                         ▼
                              [Dashboard Next.js]
                          Ranking · Funil · Time · Qualidade
```

---

## Estrutura

```
attribution-system/
├── backend/
│   ├── db/          schema.sql, client.py
│   ├── config/      settings.py, depara.py
│   ├── ingest/      sheets_sync.py, meta_sync.py, ghl_webhook.py, ghl_reconcile.py
│   ├── engine/      normalizer.py, deriver.py, match.py
│   ├── api/         main.py, routes/dashboard.py, routes/health.py
│   └── tests/       test_normalizer.py, test_deriver.py
└── frontend/
    └── src/
        ├── app/     page.tsx, funnel/, team/, quality/
        ├── components/  GlobalFilters, RankingTable, FunnelChart, KpiCard, QualityPanel
        └── lib/     api.ts
```

---

## Configuração Rápida

### 1. Supabase
1. Crie um projeto em [supabase.com](https://supabase.com)
2. Copie `SUPABASE_URL` e `SUPABASE_SERVICE_KEY` (Settings → API)
3. Abra o **SQL Editor** e cole o conteúdo de `backend/db/schema.sql`
4. Execute — tabelas, índices, view e seed do de-para são criados

### 2. Backend Python

```bash
cd attribution-system/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp ../.env.example ../.env
# Edite .env com suas credenciais

# Rodar localmente
uvicorn backend.api.main:app --reload --port 8000
```

Acesse `http://localhost:8000/docs` para ver todos os endpoints.

### 3. Rodar testes

```bash
cd attribution-system
python -m pytest backend/tests/ -v
```

### 4. Frontend Next.js

```bash
cd attribution-system/frontend
cp .env.local.example .env.local
# Ajuste NEXT_PUBLIC_API_URL se necessário

npm install
npm run dev
# Abre em http://localhost:3000
```

---

## Variáveis de Ambiente (`.env`)

| Variável | Obrigatória | Descrição |
|---|---|---|
| `SUPABASE_URL` | ✅ | URL do projeto Supabase |
| `SUPABASE_SERVICE_KEY` | ✅ | Service key (acesso total ao banco) |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | ✅ | JSON da service account (Google Sheets) |
| `SHEET_ID` | ✅ | ID da planilha de Leads (da URL) |
| `META_SYSTEM_USER_TOKEN` | ✅ | Token do System User do Meta |
| `META_AD_ACCOUNT_ID` | ✅ | ID da conta de anúncios (sem `act_`) |
| `GHL_PRIVATE_TOKEN` | Rec. | Token de integração privada do GHL |
| `GHL_LOCATION_ID` | Rec. | ID da sub-account do GHL |
| `DEFAULT_FUNNEL_ID` | — | ID do funil padrão no banco (default: 1) |

---

## Primeiros Dados — Passo a Passo

```bash
# 1. Inserir o primeiro funil no banco
# (via Supabase Studio → Table Editor → funnels)
# ou via SQL:
INSERT INTO funnels (nome, utm_funnel_code, planilha_id)
VALUES ('Meu Funil', 'PAA', 'SEU_SHEET_ID');

# 2. Forçar a primeira importação da planilha
curl -X POST http://localhost:8000/admin/sync-sheets

# 3. Forçar a primeira importação do Meta
curl -X POST http://localhost:8000/admin/sync-meta

# 4. Rodar o motor de cruzamento
curl -X POST http://localhost:8000/admin/run-match

# 5. Checar a cobertura
curl http://localhost:8000/api/dashboard/quality?funnel_id=1
```

---

## Deploy

### Backend → Railway

1. Crie um novo projeto no Railway a partir deste repo
2. Configure as variáveis de ambiente (copie do `.env`)
3. Railway detecta `requirements.txt` → usa Python buildpack automaticamente
4. Start command: `uvicorn backend.api.main:app --host 0.0.0.0 --port $PORT`

### Frontend → Vercel

1. Conecte o repo no [vercel.com](https://vercel.com)
2. Root Directory: `attribution-system/frontend`
3. Adicione `NEXT_PUBLIC_API_URL` apontando para a URL do Railway

---

## Adicionar Novo Funil

**Não toca em código** — só configuração:

```sql
-- 1. Inserir no banco
INSERT INTO funnels (nome, ghl_location_id, ghl_tag, meta_ad_account_id,
                     utm_funnel_code, planilha_id)
VALUES ('Novo Funil', 'xxx', 'novo-funil', 'act_xxx', 'NFF', 'SHEET_ID');
```

```
-- 2. GHL: criar Workflow com gatilho na tag → POST /ingest/ghl?funnel_id=<id>
-- 3. Meta: aplicar convenção [NFF] nas campanhas
-- 4. Planilha: usar o mesmo template (mesmas colunas)
```

---

## Ajustar De-Para (sem redeploy)

Quando surgir um valor novo na planilha que não é reconhecido:

```sql
-- Via Supabase Studio ou SQL:
INSERT INTO depara_status (campo, valor_raw, valor_norm)
VALUES ('status_call', 'NOVO VALOR', 'REALIZADA_COM_VENDA');
```

Após o próximo startup do backend (ou restart), o novo mapeamento é carregado automaticamente.

---

## Verificação End-to-End

| Passo | Como verificar |
|---|---|
| Planilha → banco | `SELECT COUNT(*) FROM leads; SELECT COUNT(*) FROM calls;` — bater com contagem manual |
| Derivação | `SELECT call_realizada, houve_venda, houve_noshow FROM calls LIMIT 20;` |
| Motor | `SELECT COUNT(*) FROM lead_ad_match WHERE match_confidence = 'alta';` |
| API | `GET /api/dashboard/ranking?funnel_id=1` retorna JSON com métricas |
| Dashboard | Ranking com CPL/CAC/ROAS visíveis e coerentes |
| Idempotência | Re-importar planilha → `SELECT COUNT(*) FROM calls;` não muda |

---

## Regras de Negócio Críticas

### `call_realizada`
```
STATUS CALL = REALIZADA_COM_VENDA              → TRUE
STATUS CALL ∈ {NAO_REALIZADA, CANCELADA}       → FALSE
STATUS CALL = REAGENDADA                        → FALSE
STATUS CALL vazio + STATUS VENDA = PERDIDA/FOLLOW_UP → TRUE  ← confirmado pelo usuário
STATUS CALL vazio + data_call preenchida        → TRUE
Caso contrário                                  → FALSE
```

### Receita
- `cash_collected` = **SOMA** das calls (cada call traz parcela diferente)
- `valor_total` = **MÁXIMO** entre as calls (mesmo contrato — somar dobraria)
