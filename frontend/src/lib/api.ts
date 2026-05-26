/**
 * Helpers para chamar a FastAPI do backend.
 * A URL base vem da variável de ambiente NEXT_PUBLIC_API_URL.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface Filters {
  funnel_id?: number;
  period_start?: string;
  period_end?: string;
  campaign_id?: string;
  produto?: string;
  sdr?: string;
  closer?: string;
}

function buildParams(filters: Filters): URLSearchParams {
  const p = new URLSearchParams();
  Object.entries(filters).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") {
      p.set(k, String(v));
    }
  });
  return p;
}

async function get<T>(path: string, params?: URLSearchParams): Promise<T> {
  const url = `${API_BASE}${path}${params?.toString() ? `?${params}` : ""}`;
  const res = await fetch(url, { next: { revalidate: 60 } }); // cache 60s
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
  return res.json();
}

// ─── Tipos ──────────────────────────────────────────────────────────────────

export interface AdRanking {
  ad_id: string;
  ad_name: string;
  adset_name: string;
  campaign_name: string;
  investido: number;
  impressoes: number;
  cliques: number;
  leads: number;
  mqls: number;
  calls_agendadas: number;
  calls_realizadas: number;
  noshows: number;
  vendas: number;
  vendas_brutas: number;
  vendas_revertidas: number;
  cash_collected: number;
  valor_total: number;
  // indicadores
  cpl: number | null;
  custo_por_call: number | null;
  cac: number | null;
  roas_cash: number | null;
  roas_contratado: number | null;
  taxa_show: number | null;
  taxa_fechamento: number | null;
}

export interface FunnelStep {
  etapa: string;
  valor: number;
  taxa?: number | null;
}

export interface TeamMember {
  nome: string;
  calls_agendadas: number;
  calls_realizadas: number;
  noshows: number;
  vendas: number;
  cash_collected: number;
  taxa_show: number | null;
  taxa_fechamento: number | null;
}

export interface QualityData {
  total_leads: number;
  leads_com_match: number;
  cobertura_atribuicao: number;
  leads_so_planilha: number;
  calls_status_desconhecido: number;
  calls_sem_data: number;
  alertas: { tipo: string; ativo: boolean; mensagem: string }[];
}

export interface Funnel {
  id: number;
  nome: string;
  ativo: boolean;
  utm_funnel_code: string;
}

// ─── Chamadas ───────────────────────────────────────────────────────────────

export const apiRanking = (f: Filters) =>
  get<{ data: AdRanking[]; periodo: { start: string; end: string } }>(
    "/api/dashboard/ranking",
    buildParams(f)
  );

export const apiFunnel = (f: Filters) =>
  get<{ steps: FunnelStep[]; periodo: { start: string; end: string } }>(
    "/api/dashboard/funnel",
    buildParams(f)
  );

export const apiTeam = (f: Filters) =>
  get<{ sdrs: TeamMember[]; closers: TeamMember[]; periodo: { start: string; end: string } }>(
    "/api/dashboard/team",
    buildParams(f)
  );

export const apiQuality = (funnel_id: number) =>
  get<QualityData>("/api/dashboard/quality", buildParams({ funnel_id }));

export const apiFunnels = () =>
  get<{ funnels: Funnel[] }>("/api/dashboard/funnels");

// ─── Meta OAuth ───────────────────────────────────────────────────────────────
export async function fetchMetaStatus() {
  const res = await fetch(`${API_BASE}/auth/meta/status`);
  return res.json();
}

export async function fetchMetaAccounts() {
  const res = await fetch(`${API_BASE}/auth/meta/accounts`);
  if (!res.ok) throw new Error("Erro ao buscar contas Meta");
  return res.json();
}

export async function selectMetaAccount(accountId: string, funnelId = 1) {
  const res = await fetch(`${API_BASE}/auth/meta/account`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ account_id: accountId, funnel_id: funnelId }),
  });
  return res.json();
}

export async function disconnectMeta() {
  const res = await fetch(`${API_BASE}/auth/meta`, { method: "DELETE" });
  return res.json();
}

export function getMetaAuthUrl() {
  return `${API_BASE}/auth/meta`;
}

// ─── Helpers de formatação ──────────────────────────────────────────────────

export const fmt = {
  brl: (v: number | null | undefined) =>
    v == null ? "—" : v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" }),

  pct: (v: number | null | undefined) =>
    v == null ? "—" : `${(v * 100).toFixed(1)}%`,

  n: (v: number | null | undefined) =>
    v == null ? "—" : v.toLocaleString("pt-BR"),

  x: (v: number | null | undefined) =>
    v == null ? "—" : `${v.toFixed(2)}x`,
};
