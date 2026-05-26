import type { StatementSpec } from "./statementRows";
import { fmtMoney, fmtNum, fmtPct, type Unit } from "./fmtFinancial";

interface Props {
  periods: string[];
  data: Record<string, (number | null)[]>;
  spec: StatementSpec;
  unit: Unit;
  pctChg: boolean;
  commonSize: boolean;
}

function pctChange(curr: number | null, prev: number | null): number | null {
  if (curr == null || prev == null || prev === 0) return null;
  return (curr - prev) / Math.abs(prev);
}

export function StatementTable({ periods, data, spec, unit, pctChg, commonSize }: Props) {
  if (periods.length === 0) {
    return <div className="p-6 text-sm text-[var(--text-muted)]">No statement data available.</div>;
  }
  const base = spec.baseKey ? data[spec.baseKey] : null;
  const useCommonSize = commonSize && !!base;

  return (
    <div className="overflow-x-auto rounded-lg border border-[var(--border)]">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-[var(--border)] bg-[var(--surface)]">
            <th className="sticky left-0 z-10 bg-[var(--surface)] px-3 py-2 text-left text-xs font-semibold text-[var(--text-muted)]">
              {useCommonSize ? "% of base" : `Units: ${unit}`}
            </th>
            {periods.map((p, i) => (
              <th key={i} className="px-3 py-2 text-right text-xs font-semibold text-[var(--text-muted)] whitespace-nowrap">
                {p}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {spec.rows.map((row) => (
            <RowGroup
              key={row.key}
              label={row.label}
              bold={row.bold}
              kind={row.kind}
              values={data[row.key] ?? []}
              periodsLen={periods.length}
              unit={unit}
              pctChg={pctChg}
              useCommonSize={useCommonSize && row.kind === "money"}
              base={base}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RowGroup(props: {
  label: string;
  bold?: boolean;
  kind: "money" | "num";
  values: (number | null)[];
  periodsLen: number;
  unit: Unit;
  pctChg: boolean;
  useCommonSize: boolean;
  base: (number | null)[] | null;
}) {
  const { label, bold, kind, values, periodsLen, unit, pctChg, useCommonSize, base } = props;
  const idx = Array.from({ length: periodsLen }, (_, i) => i);

  function cell(i: number): string {
    const v = values[i] ?? null;
    if (useCommonSize && base) {
      const b = base[i] ?? null;
      if (v == null || b == null || b === 0) return "—";
      return fmtPct(v / b);
    }
    return kind === "money" ? fmtMoney(v, unit) : fmtNum(v);
  }

  return (
    <>
      <tr className="border-b border-[var(--border)]/40 hover:bg-[var(--surface-alt)]">
        <td className={`sticky left-0 z-10 bg-[var(--surface)] px-3 py-1.5 text-left ${bold ? "font-semibold text-[var(--text)]" : "text-[var(--text-muted)]"}`}>
          {label}
        </td>
        {idx.map((i) => (
          <td key={i} className={`px-3 py-1.5 text-right font-mono tabular-nums ${bold ? "font-semibold text-[var(--text)]" : "text-[var(--text)]"}`}>
            {cell(i)}
          </td>
        ))}
      </tr>
      {pctChg && kind === "money" && !useCommonSize && (
        <tr className="border-b border-[var(--border)]/40 text-[var(--text-muted)]">
          <td className="sticky left-0 z-10 bg-[var(--surface)] px-3 py-1 pl-6 text-left text-xs italic">% Chg</td>
          {idx.map((i) => {
            const chg = pctChange(values[i] ?? null, values[i + 1] ?? null);
            return (
              <td key={i} className="px-3 py-1 text-right font-mono text-xs italic tabular-nums">
                {chg == null ? "—" : `${chg >= 0 ? "+" : ""}${(chg * 100).toFixed(1)}%`}
              </td>
            );
          })}
        </tr>
      )}
    </>
  );
}
