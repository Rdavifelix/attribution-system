import { Suspense }        from "react";
import { apiFunnel, apiFunnels, type Filters } from "@/lib/api";
import { GlobalFilters }   from "@/components/GlobalFilters";
import { FunnelChart }     from "@/components/FunnelChart";

interface PageProps { searchParams: Filters & { funnel_id?: string } }

export default async function FunnelPage({ searchParams }: PageProps) {
  const [{ funnels }, { steps, periodo }] = await Promise.all([
    apiFunnels(),
    apiFunnel({
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
          Funil Completo
          <span className="ml-2 text-sm font-normal text-gray-400">
            {periodo.start} → {periodo.end}
          </span>
        </h1>
        <FunnelChart steps={steps} />
      </div>
    </div>
  );
}
