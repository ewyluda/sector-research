/**
 * Typed builders for the financial-model cell-path wire format.
 *
 * The backend (backend/app/models/cell_path.py) parses these strings and
 * validates against its registries. Keep this in sync with the Python module:
 * if the wire format changes, both sides + the round-trip test must change.
 */

export type Statement = "income_statement" | "balance_sheet" | "cash_flow";

export type CellPath =
  | { kind: "driver"; period: string; key: string }
  | { kind: "statement"; statement: Statement; line: string; period: string }
  | { kind: "assumption"; key: string };

export const driverPath = (period: string, key: string): CellPath => ({
  kind: "driver",
  period,
  key,
});

export const statementPath = (
  statement: Statement,
  line: string,
  period: string,
): CellPath => ({ kind: "statement", statement, line, period });

export const assumptionPath = (key: string): CellPath => ({
  kind: "assumption",
  key,
});

export function toWire(p: CellPath): string {
  switch (p.kind) {
    case "driver":
      return `drivers.${p.period}.${p.key}`;
    case "statement":
      return `${p.statement}.${p.line}.${p.period}`;
    case "assumption":
      return `assumptions.${p.key}`;
  }
}
