"use client";
import { FunnelStep, fmt } from "@/lib/api";

interface Props {
  steps: FunnelStep[];
}

export function FunnelChart({ steps }: Props) {
  const max = Math.max(...steps.map((s) => s.valor), 1);

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6">
      <h2 className="text-base font-semibold text-gray-700 mb-6">Funil Completo</h2>
      <div className="flex flex-col gap-2">
        {steps.map((step, i) => {
          const pct = (step.valor / max) * 100;
          return (
            <div key={step.etapa} className="flex items-center gap-4">
              {/* Label */}
              <div className="w-40 text-sm text-gray-600 text-right shrink-0">
                {step.etapa}
              </div>
              {/* Barra */}
              <div className="flex-1 relative">
                <div
                  className="h-9 rounded-lg bg-blue-500 flex items-center pl-3 text-white text-sm font-semibold transition-all duration-500"
                  style={{ width: `${Math.max(pct, 2)}%` }}
                >
                  {step.valor >= 1000 ? fmt.n(step.valor) : step.valor}
                </div>
              </div>
              {/* Taxa de conversão */}
              {i > 0 && step.taxa != null && (
                <div className="text-xs text-gray-400 w-14 text-right shrink-0">
                  {fmt.pct(step.taxa)}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
