"use client";
import { AdRanking, fmt } from "@/lib/api";
import { useState } from "react";

type SortKey = keyof AdRanking;

interface Props {
  data: AdRanking[];
}

const COLS: { key: SortKey; label: string; format: (v: AdRanking) => string; tip?: string }[] = [
  { key: "ad_name",          label: "Anúncio",          format: (r) => r.ad_name || r.ad_id },
  { key: "campaign_name",    label: "Campanha",          format: (r) => r.campaign_name },
  { key: "investido",        label: "Investido",         format: (r) => fmt.brl(r.investido) },
  { key: "leads",            label: "Leads",             format: (r) => fmt.n(r.leads) },
  { key: "calls_agendadas",  label: "Calls Ag.",         format: (r) => fmt.n(r.calls_agendadas) },
  { key: "calls_realizadas", label: "Calls Realiz.",     format: (r) => fmt.n(r.calls_realizadas) },
  { key: "noshows",          label: "No-Shows",          format: (r) => fmt.n(r.noshows) },
  { key: "taxa_show",        label: "% Show",            format: (r) => fmt.pct(r.taxa_show), tip: "Calls realizadas / agendadas" },
  { key: "vendas",           label: "Vendas",            format: (r) => fmt.n(r.vendas) },
  { key: "taxa_fechamento",  label: "% Fecha.",          format: (r) => fmt.pct(r.taxa_fechamento), tip: "Vendas / calls realizadas" },
  { key: "cash_collected",   label: "Cash",              format: (r) => fmt.brl(r.cash_collected) },
  { key: "cpl",              label: "CPL",               format: (r) => fmt.brl(r.cpl), tip: "Custo por lead" },
  { key: "custo_por_call",   label: "R$/Call",           format: (r) => fmt.brl(r.custo_por_call), tip: "Custo por call realizada" },
  { key: "cac",              label: "CAC",               format: (r) => fmt.brl(r.cac), tip: "Custo por cliente" },
  { key: "roas_cash",        label: "ROAS (cash)",       format: (r) => fmt.x(r.roas_cash) },
];

export function RankingTable({ data }: Props) {
  const [sortKey, setSortKey]   = useState<SortKey>("investido");
  const [sortAsc, setSortAsc]   = useState(false);

  const sorted = [...data].sort((a, b) => {
    const va = a[sortKey] as number ?? -Infinity;
    const vb = b[sortKey] as number ?? -Infinity;
    return sortAsc ? va - vb : vb - va;
  });

  const handleSort = (key: SortKey) => {
    if (key === sortKey) setSortAsc(!sortAsc);
    else { setSortKey(key); setSortAsc(false); }
  };

  if (!data.length) {
    return (
      <div className="text-center py-16 text-gray-400">
        Nenhum dado encontrado para o período e filtros selecionados.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-gray-200">
      <table className="min-w-full divide-y divide-gray-200 text-sm">
        <thead className="bg-gray-50">
          <tr>
            {COLS.map((col) => (
              <th
                key={col.key}
                title={col.tip}
                onClick={() => handleSort(col.key)}
                className="px-3 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider cursor-pointer select-none hover:text-gray-700 whitespace-nowrap"
              >
                {col.label}
                {sortKey === col.key && (sortAsc ? " ↑" : " ↓")}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-100">
          {sorted.map((row) => (
            <tr key={row.ad_id} className="hover:bg-blue-50 transition-colors">
              {COLS.map((col) => (
                <td key={col.key} className="px-3 py-3 whitespace-nowrap text-gray-700">
                  {col.format(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
