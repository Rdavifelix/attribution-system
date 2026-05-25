"use client";
import { QualityData, fmt } from "@/lib/api";

interface Props {
  data: QualityData;
}

export function QualityPanel({ data }: Props) {
  const coveragePct = data.cobertura_atribuicao * 100;
  const coverageColor =
    coveragePct >= 80 ? "text-green-600" :
    coveragePct >= 50 ? "text-yellow-600" :
    "text-red-600";

  return (
    <div className="flex flex-col gap-6">
      {/* Alertas */}
      {data.alertas.filter((a) => a.ativo).length > 0 && (
        <div className="flex flex-col gap-2">
          {data.alertas.filter((a) => a.ativo).map((a) => (
            <div
              key={a.tipo}
              className="flex items-start gap-3 bg-yellow-50 border border-yellow-200 rounded-xl p-4"
            >
              <span className="text-yellow-500 text-lg">⚠️</span>
              <p className="text-sm text-yellow-800">{a.mensagem}</p>
            </div>
          ))}
        </div>
      )}

      {/* Cartões de métricas */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        <Metric label="Total de Leads"          value={fmt.n(data.total_leads)} />
        <Metric label="Leads com Match"         value={fmt.n(data.leads_com_match)} />
        <Metric
          label="Cobertura de Atribuição"
          value={`${coveragePct.toFixed(1)}%`}
          valueClass={coverageColor}
        />
        <Metric label="Leads só na Planilha"   value={fmt.n(data.leads_so_planilha)}
                sub="Sem registro no GHL" />
        <Metric label="Status Desconhecidos"   value={fmt.n(data.calls_status_desconhecido)}
                sub="Atualizar depara_status" />
        <Metric label="Calls sem Data"         value={fmt.n(data.calls_sem_data)} />
      </div>

      {/* Barra de cobertura */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <p className="text-sm font-medium text-gray-600 mb-3">Cobertura de Atribuição</p>
        <div className="w-full bg-gray-100 rounded-full h-4">
          <div
            className={`h-4 rounded-full transition-all duration-700 ${
              coveragePct >= 80 ? "bg-green-500" :
              coveragePct >= 50 ? "bg-yellow-400" : "bg-red-500"
            }`}
            style={{ width: `${Math.min(coveragePct, 100)}%` }}
          />
        </div>
        <div className="flex justify-between text-xs text-gray-400 mt-1">
          <span>0%</span>
          <span className={`font-semibold ${coverageColor}`}>
            {coveragePct.toFixed(1)}% dos leads têm anúncio atribuído
          </span>
          <span>100%</span>
        </div>
      </div>
    </div>
  );
}

function Metric({
  label,
  value,
  sub,
  valueClass = "text-gray-900",
}: {
  label: string;
  value: string;
  sub?: string;
  valueClass?: string;
}) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <p className="text-xs text-gray-500 font-medium uppercase tracking-wide mb-1">{label}</p>
      <p className={`text-2xl font-bold ${valueClass}`}>{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
    </div>
  );
}
