/**
 * Página principal — Ranking de Anúncios
 *
 * Server Component: busca os dados no servidor, passa para o cliente.
 * Os filtros vêm dos URL search params.
 */
import { Suspense } from "react";
import { apiRanking, apiFunnels, fmt, type Filters } from "@/lib/api";
import { GlobalFilters } from "@/components/GlobalFilters";
import { RankingTable }  from "@/components/RankingTable";
import { KpiCard }       from "@/components/KpiCard";

interface PageProps {
  searchParams: Filters & { funnel_id?: string };
}

export default async function HomePage({ searchParams }: PageProps) {
  const [{ funnels }, ranking] = await Promise.all([
    apiFunnels(),
    apiRanking({
      funnel_id:    Number(searchParams.funnel_id ?? 1),
      period_start: searchParams.period_start,
      period_end:   searchParams.period_end,
      produto:      searchParams.produto,
    }),
  ]);

  const data = ranking.data;

  // KPIs consolidados (soma de todos os anúncios)
  const total = data.reduce(
    (acc, r) => ({
      investido:        acc.investido        + r.investido,
      leads:            acc.leads            + r.leads,
      calls_realizadas: acc.calls_realizadas + r.calls_realizadas,
      vendas:           acc.vendas           + r.vendas,
      cash_collected:   acc.cash_collected   + r.cash_collected,
    }),
    { investido: 0, leads: 0, calls_realizadas: 0, vendas: 0, cash_collected: 0 }
  );

  const cac_total  = total.vendas   ? total.investido / total.vendas   : null;
  const roas_total = total.investido ? total.cash_collected / total.investido : null;

  return (
    <div className="flex flex-col h-full">
      {/* Filtros */}
      <Suspense>
        <GlobalFilters funnels={funnels} />
      </Suspense>

      <div className="flex-1 p-6 flex flex-col gap-6">
        {/* KPI Cards */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          <KpiCard label="Investido"       value={fmt.brl(total.investido)} />
          <KpiCard label="Leads"           value={fmt.n(total.leads)} />
          <KpiCard label="Calls Realiz."   value={fmt.n(total.calls_realizadas)} />
          <KpiCard label="Vendas"          value={fmt.n(total.vendas)} color="green" />
          <KpiCard label="Cash Collected"  value={fmt.brl(total.cash_collected)} color="green" />
          <KpiCard
            label="CAC"
            value={fmt.brl(cac_total)}
            sub={`ROAS ${fmt.x(roas_total)}`}
            color={roas_total && roas_total >= 1 ? "green" : "red"}
          />
        </div>

        {/* Tabela de ranking */}
        <div>
          <h1 className="text-lg font-semibold text-gray-800 mb-3">
            Ranking de Anúncios
            <span className="ml-2 text-sm font-normal text-gray-400">
              {ranking.periodo.start} → {ranking.periodo.end}
            </span>
          </h1>
          <RankingTable data={data} />
        </div>
      </div>
    </div>
  );
}
