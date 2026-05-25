"use client";
/**
 * Filtros globais — persistidos como URL params.
 * Todos os componentes de dados leem os filtros daqui.
 */
import { useRouter, useSearchParams, usePathname } from "next/navigation";
import { useCallback } from "react";
import { Funnel } from "@/lib/api";

interface Props {
  funnels: Funnel[];
}

function today() {
  return new Date().toISOString().slice(0, 10);
}
function daysAgo(n: number) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

export function GlobalFilters({ funnels }: Props) {
  const router      = useRouter();
  const pathname    = usePathname();
  const searchParams= useSearchParams();

  const get = (key: string, fallback = "") =>
    searchParams.get(key) ?? fallback;

  const set = useCallback(
    (key: string, value: string) => {
      const params = new URLSearchParams(searchParams.toString());
      if (value) params.set(key, value);
      else params.delete(key);
      router.replace(`${pathname}?${params.toString()}`);
    },
    [router, pathname, searchParams]
  );

  return (
    <div className="flex flex-wrap gap-3 items-end p-4 bg-white border-b border-gray-200">
      {/* Funil */}
      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">Funil</label>
        <select
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white min-w-[140px] focus:outline-none focus:ring-2 focus:ring-blue-500"
          value={get("funnel_id", "1")}
          onChange={(e) => set("funnel_id", e.target.value)}
        >
          {funnels.map((f) => (
            <option key={f.id} value={String(f.id)}>
              {f.nome}
            </option>
          ))}
        </select>
      </div>

      {/* Período */}
      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">De</label>
        <input
          type="date"
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          value={get("period_start", daysAgo(30))}
          onChange={(e) => set("period_start", e.target.value)}
        />
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">Até</label>
        <input
          type="date"
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          value={get("period_end", today())}
          onChange={(e) => set("period_end", e.target.value)}
        />
      </div>

      {/* Atalhos de período */}
      <div className="flex gap-1 self-end mb-0.5">
        {[
          { label: "7d",  days: 7  },
          { label: "30d", days: 30 },
          { label: "90d", days: 90 },
        ].map(({ label, days }) => (
          <button
            key={label}
            onClick={() => {
              const params = new URLSearchParams(searchParams.toString());
              params.set("period_start", daysAgo(days));
              params.set("period_end", today());
              router.replace(`${pathname}?${params.toString()}`);
            }}
            className="px-3 py-2 text-xs border border-gray-300 rounded-lg hover:bg-blue-50 hover:border-blue-400 transition-colors"
          >
            {label}
          </button>
        ))}
      </div>

      {/* Produto */}
      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">Produto</label>
        <select
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white min-w-[100px] focus:outline-none focus:ring-2 focus:ring-blue-500"
          value={get("produto")}
          onChange={(e) => set("produto", e.target.value)}
        >
          <option value="">Todos</option>
          <option value="MFA">MFA</option>
          <option value="PAA">PAA</option>
        </select>
      </div>
    </div>
  );
}

/** Hook para ler os filtros atuais como objeto tipado. */
export function useFilters() {
  const searchParams = useSearchParams();
  return {
    funnel_id:    Number(searchParams.get("funnel_id") ?? 1),
    period_start: searchParams.get("period_start") ?? daysAgo(30),
    period_end:   searchParams.get("period_end")   ?? today(),
    campaign_id:  searchParams.get("campaign_id")  ?? undefined,
    produto:      searchParams.get("produto")       ?? undefined,
    sdr:          searchParams.get("sdr")           ?? undefined,
    closer:       searchParams.get("closer")        ?? undefined,
  };
}
