import { Suspense }      from "react";
import { apiQuality, apiFunnels, type Filters } from "@/lib/api";
import { GlobalFilters } from "@/components/GlobalFilters";
import { QualityPanel }  from "@/components/QualityPanel";

interface PageProps { searchParams: Filters & { funnel_id?: string } }

export default async function QualityPage({ searchParams }: PageProps) {
  const funnel_id = Number(searchParams.funnel_id ?? 1);
  const [{ funnels }, quality] = await Promise.all([
    apiFunnels(),
    apiQuality(funnel_id),
  ]);

  return (
    <div className="flex flex-col h-full">
      <Suspense>
        <GlobalFilters funnels={funnels} />
      </Suspense>
      <div className="flex-1 p-6 flex flex-col gap-4">
        <h1 className="text-lg font-semibold text-gray-800">Qualidade de Dados & Atribuição</h1>
        <QualityPanel data={quality} />
      </div>
    </div>
  );
}
