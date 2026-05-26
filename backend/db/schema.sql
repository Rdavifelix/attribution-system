-- ============================================================
--  attribution-system — Schema v2
--  Rodar no SQL Editor do Supabase (uma vez, em ordem)
-- ============================================================

-- Extensão necessária para gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ─── De-para de canonicalização ─────────────────────────────
-- Editável via Supabase Studio sem mexer em código
CREATE TABLE IF NOT EXISTS depara_status (
  id          SERIAL PRIMARY KEY,
  campo       TEXT NOT NULL,   -- 'status_call' | 'status_venda'
  valor_raw   TEXT NOT NULL,   -- valor exato vindo da planilha
  valor_norm  TEXT NOT NULL,   -- valor canônico usado nas queries
  UNIQUE(campo, valor_raw)
);

-- Seed inicial — espelha config/depara.py
INSERT INTO depara_status (campo, valor_raw, valor_norm) VALUES
  -- STATUS CALL
  ('status_call', 'VENDA - EM CALL',       'REALIZADA_COM_VENDA'),
  ('status_call', 'CALL REALIZADA',        'REALIZADA'),
  ('status_call', 'CALL NÃO REALIZADA',    'NAO_REALIZADA'),
  ('status_call', 'NÃO COMPARECEU',        'NAO_REALIZADA'),
  ('status_call', 'NAO COMPARECEU',        'NAO_REALIZADA'),
  ('status_call', 'CALL REAGENDADA',       'REAGENDADA'),
  ('status_call', 'CALL CANCELADA',        'CANCELADA'),
  ('status_call', '',                      'VAZIO'),
  -- STATUS VENDA
  ('status_venda', 'VENDA - EM CALL',      'VENDA_EM_CALL'),
  ('status_venda', 'VENDA - SINAL',        'VENDA_SINAL'),
  ('status_venda', 'VENDA',               'VENDA_EM_CALL'),
  ('status_venda', 'Vendido',             'VENDA_EM_CALL'),
  ('status_venda', 'SINAL RECEBIDO',       'SINAL_RECEBIDO'),
  ('status_venda', 'REEMBOLSADA',          'REEMBOLSADA'),
  ('status_venda', 'Follow UP',            'FOLLOW_UP'),
  ('status_venda', 'Follow UP ',           'FOLLOW_UP'),
  ('status_venda', 'follow up',            'FOLLOW_UP'),
  ('status_venda', 'FOLLOW UP',            'FOLLOW_UP'),
  ('status_venda', '2a reunião agendada',  'SEGUNDA_REUNIAO'),
  ('status_venda', '2a reunbião agendada', 'SEGUNDA_REUNIAO'),
  ('status_venda', '2ª REUNIÃO',           'SEGUNDA_REUNIAO'),
  ('status_venda', 'REAGENDADA',           'REAGENDADA'),
  ('status_venda', 'PERDIDA',              'PERDIDA'),
  ('status_venda', 'TESTE SYNC',           'VAZIO'),
  ('status_venda', '',                     'VAZIO')
ON CONFLICT (campo, valor_raw) DO NOTHING;

-- ─── Funis ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS funnels (
  id                  SERIAL PRIMARY KEY,
  nome                TEXT NOT NULL,
  ativo               BOOLEAN DEFAULT TRUE,
  ghl_location_id     TEXT,
  ghl_tag             TEXT,
  meta_ad_account_id  TEXT,
  utm_funnel_code     TEXT,  -- ex: 'PAA', 'MFA'
  planilha_id         TEXT,  -- Google Sheet ID
  created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Leads ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS leads (
  id                UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  funnel_id         INTEGER REFERENCES funnels(id) ON DELETE SET NULL,
  ghl_contact_id    TEXT UNIQUE,

  -- Identidade / chaves de cruzamento
  email_norm        TEXT,
  telefone_norm     TEXT,
  nome              TEXT,

  -- Atribuição (vem do GHL)
  utm_source        TEXT,
  utm_medium        TEXT,
  utm_campaign      TEXT,
  utm_content       TEXT,
  utm_term          TEXT,
  fbclid            TEXT,
  fb_campaign_id    TEXT,
  fb_adset_id       TEXT,
  fb_ad_id          TEXT,
  attribution_first JSONB,
  attribution_last  JSONB,

  -- Qualificação (vem da planilha)
  origem_planilha   TEXT,
  instagram         TEXT,
  faturamento       TEXT,
  profissao         TEXT,
  mql               TEXT,
  tem_socio         TEXT,
  lead_scoring      TEXT,
  data_cadastro     DATE,
  data_contato      DATE,

  -- Flags derivadas (calculadas pelo motor)
  tem_call_agendada  BOOLEAN DEFAULT FALSE,
  tem_call_realizada BOOLEAN DEFAULT FALSE,
  virou_venda        BOOLEAN DEFAULT FALSE,

  -- Rastreabilidade
  origem_registro   TEXT DEFAULT 'ghl',  -- 'ghl' | 'planilha' | 'ambos'
  raw_ghl           JSONB,
  raw_planilha      JSONB,

  created_at        TIMESTAMPTZ DEFAULT NOW(),
  updated_at        TIMESTAMPTZ DEFAULT NOW()
);

-- Chaves de unicidade compostas (por funil)
CREATE UNIQUE INDEX IF NOT EXISTS uq_leads_email
  ON leads(funnel_id, email_norm)
  WHERE email_norm IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_leads_telefone
  ON leads(funnel_id, telefone_norm)
  WHERE telefone_norm IS NOT NULL;

-- ─── Calls ──────────────────────────────────────────────────
-- 1 linha por call (resultado do unpivot da planilha larga)
CREATE TABLE IF NOT EXISTS calls (
  id                UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  lead_id           UUID REFERENCES leads(id) ON DELETE CASCADE,
  funnel_id         INTEGER REFERENCES funnels(id) ON DELETE SET NULL,
  numero_call       INTEGER NOT NULL,  -- 1 ou 2

  -- Datas e horários
  data_agendamento  DATE,
  data_call         DATE,
  hora_call         TEXT,
  data_venda        DATE,

  -- Pessoas envolvidas
  sdr               TEXT,
  closer            TEXT,

  -- Status (bruto da planilha + normalizado via de-para)
  status_call_raw   TEXT,
  status_call_norm  TEXT,
  status_venda_raw  TEXT,
  status_venda_norm TEXT,
  motivo_noshow     TEXT,
  razao_perda       TEXT,

  -- Financeiro
  cash_collected    NUMERIC(12,2),
  valor_total       NUMERIC(12,2),
  valor             NUMERIC(12,2),
  produto           TEXT,  -- MFA | PAA

  -- Flags derivadas
  call_realizada    BOOLEAN DEFAULT FALSE,
  houve_venda       BOOLEAN DEFAULT FALSE,
  venda_revertida   BOOLEAN DEFAULT FALSE,
  houve_noshow      BOOLEAN DEFAULT FALSE,

  -- Extras
  link_reuniao      TEXT,
  observacoes       TEXT,

  created_at        TIMESTAMPTZ DEFAULT NOW(),
  updated_at        TIMESTAMPTZ DEFAULT NOW(),

  UNIQUE(lead_id, numero_call)
);

-- ─── Ad Performance ─────────────────────────────────────────
-- Snapshot diário vindo do Meta Ads (nível de anúncio)
CREATE TABLE IF NOT EXISTS ad_performance (
  id            UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  funnel_id     INTEGER REFERENCES funnels(id) ON DELETE SET NULL,
  data          DATE NOT NULL,
  campaign_id   TEXT,
  campaign_name TEXT,
  adset_id      TEXT,
  adset_name    TEXT,
  ad_id         TEXT NOT NULL,
  ad_name       TEXT,
  spend         NUMERIC(12,2),
  impressions   INTEGER,
  clicks        INTEGER,
  ctr           NUMERIC(8,4),
  cpc           NUMERIC(10,4),
  cpm           NUMERIC(10,4),
  actions       JSONB,  -- conversões e outros eventos do Meta
  created_at    TIMESTAMPTZ DEFAULT NOW(),

  UNIQUE(funnel_id, data, ad_id)
);

-- ─── Lead ↔ Anúncio ─────────────────────────────────────────
-- Liga cada lead ao anúncio que o originou
CREATE TABLE IF NOT EXISTS lead_ad_match (
  id               UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  lead_id          UUID REFERENCES leads(id) ON DELETE CASCADE,
  ad_id            TEXT NOT NULL,
  match_method     TEXT,  -- 'fb_ad_id' | 'utm_content' | 'utm_campaign'
  match_confidence TEXT,  -- 'alta' | 'media' | 'baixa'
  created_at       TIMESTAMPTZ DEFAULT NOW(),

  UNIQUE(lead_id)  -- cada lead tem no máximo 1 match (o melhor)
);

-- ─── Índices de performance ──────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_calls_lead_id      ON calls(lead_id);
CREATE INDEX IF NOT EXISTS idx_calls_funnel_id    ON calls(funnel_id);
CREATE INDEX IF NOT EXISTS idx_calls_data_call    ON calls(data_call);
CREATE INDEX IF NOT EXISTS idx_calls_data_agend   ON calls(data_agendamento);
CREATE INDEX IF NOT EXISTS idx_lam_ad_id          ON lead_ad_match(ad_id);
CREATE INDEX IF NOT EXISTS idx_adperf_funnel_data ON ad_performance(funnel_id, data);
CREATE INDEX IF NOT EXISTS idx_leads_funnel       ON leads(funnel_id);
CREATE INDEX IF NOT EXISTS idx_leads_email        ON leads(email_norm);
CREATE INDEX IF NOT EXISTS idx_leads_telefone     ON leads(telefone_norm);
CREATE INDEX IF NOT EXISTS idx_leads_fb_ad_id     ON leads(fb_ad_id);

-- ─── Trigger: updated_at automático ─────────────────────────
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_leads_updated_at
  BEFORE UPDATE ON leads
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_calls_updated_at
  BEFORE UPDATE ON calls
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ─── View: ranking por anúncio ───────────────────────────────
-- Usada diretamente pelo endpoint /api/dashboard/ranking
CREATE OR REPLACE VIEW v_ranking_ad AS
SELECT
  ap.funnel_id,
  ap.data,
  ap.ad_id,
  ap.ad_name,
  ap.adset_id,
  ap.adset_name,
  ap.campaign_id,
  ap.campaign_name,
  ap.spend,
  ap.impressions,
  ap.clicks,
  l.id                                                        AS lead_id,
  l.mql,
  l.lead_scoring,
  l.faturamento,
  c.id                                                        AS call_id,
  c.numero_call,
  c.data_agendamento,
  c.data_call,
  c.sdr,
  c.closer,
  c.produto,
  c.call_realizada,
  c.houve_venda,
  c.venda_revertida,
  c.houve_noshow,
  c.cash_collected,
  c.valor_total
FROM ad_performance ap
JOIN lead_ad_match lam  ON lam.ad_id   = ap.ad_id
JOIN leads l            ON l.id        = lam.lead_id
                       AND l.funnel_id = ap.funnel_id
LEFT JOIN calls c       ON c.lead_id   = l.id;
