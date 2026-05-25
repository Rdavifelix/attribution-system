interface Props {
  label: string;
  value: string;
  sub?: string;
  color?: "default" | "green" | "red" | "blue";
}

const colors = {
  default: "bg-white border-gray-200",
  green:   "bg-green-50 border-green-200",
  red:     "bg-red-50 border-red-200",
  blue:    "bg-blue-50 border-blue-200",
};

export function KpiCard({ label, value, sub, color = "default" }: Props) {
  return (
    <div className={`rounded-xl border p-4 flex flex-col gap-1 ${colors[color]}`}>
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</p>
      <p className="text-2xl font-bold text-gray-900">{value}</p>
      {sub && <p className="text-xs text-gray-400">{sub}</p>}
    </div>
  );
}
