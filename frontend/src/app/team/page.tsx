import { Suspense }      from "react";
import { apiTeam, apiFunnels, fmt, type Filters } from "@/lib/api";
import { GlobalFilters } from "@/components/GlobalFilters";

interface PageProps { searchParams: Filters & { funnel_id?: string } }

function TeamTable({ title, members }: { title: string; members: ReturnType<typeof apiTeam> extends Promise<{ sdrs: infer T }> ? T : never[] }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200">
      <div className="px-5 py-4 border-b border-gray-100">
        <h2 className="text-sm font-semibold text-gray-700">{title}</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-100 text-sm">
          <thead className="bg-gray-50">
            <tr>
              {["Nome","Calls Ag.","Calls Realiz.","No-Shows","% Show","Vendas","% Fecha.","Cash"].map(h => (
                <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {(members as any[]).map((m: any) => (
              <tr key={m.nome} className="hover:bg-blue-50">
                <td className="px-4 py-3 font-medium text-gray-800">{m.nome}</td>
                <td className="px-4 py-3">{fmt.n(m.calls_agendadas)}</td>
                <td className="px-4 py-3">{fmt.n(m.calls_realizadas)}</td>
                <td className="px-4 py-3">{fmt.n(m.noshows)}</td>
                <td className="px-4 py-3">{fmt.pct(m.taxa_show)}</td>
                <td className="px-4 py-3 font-semibold">{fmt.n(m.vendas)}</td>
                <td className="px-4 py-3">{fmt.pct(m.taxa_fechamento)}</td>
                <td className="px-4 py-3">{fmt.brl(m.cash_collected)}</td>
              </tr>
            ))}
            {(members as any[]).length === 0 && (
              <tr><td colSpan={8} className="px-4 py-8 text-center text-gray-400">Nenhum dado</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default async function TeamPage({ searchParams }: PageProps) {
  const [{ funnels }, teamData] = await Promise.all([
    apiFunnels(),
    apiTeam({
      funnel_id:    Number(searchParams.funnel_id ?? 1),
      period_start: searchParams.period_start,
      period_end:   searchParams.period_end,
    }),
  ]);

  return (
    <div className="flex flex-col h-full">
      <Suspense>
        <GlobalFilters funnels={funnels} />
      </Suspense>
      <div className="flex-1 p-6 flex flex-col gap-6">
        <h1 className="text-lg font-semibold text-gray-800">
          Performance do Time
          <span className="ml-2 text-sm font-normal text-gray-400">
            {teamData.periodo.start} → {teamData.periodo.end}
          </span>
        </h1>
        <TeamTable title="SDRs" members={teamData.sdrs as any} />
        <TeamTable title="Closers" members={teamData.closers as any} />
      </div>
    </div>
  );
}
