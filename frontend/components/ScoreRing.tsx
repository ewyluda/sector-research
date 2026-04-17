/**
 * Circular score indicator — used on conviction score and combined signal score.
 */

interface Props {
  score: number; // 0–100
  size?: number;
  label?: string;
}

function scoreColor(score: number) {
  if (score >= 70) return "var(--score-strong)";
  if (score >= 55) return "var(--score-neutral)";
  if (score >= 40) return "var(--score-caution)";
  return "var(--score-weak)";
}

export default function ScoreRing({ score, size = 44, label }: Props) {
  const stroke = Math.max(3, Math.round(size / 18));
  const r = (size - stroke * 2) / 2;
  const circ = 2 * Math.PI * r;
  const dash = (score / 100) * circ;
  const color = scoreColor(score);
  const fontSize = Math.max(10, Math.round(size * 0.32));

  return (
    <div className="flex flex-col items-center gap-1 tabular-nums">
      <svg width={size} height={size} role="img" aria-label={`Score: ${Math.round(score)} out of 100${label ? `, ${label}` : ""}`}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--border)" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeDasharray={`${dash} ${circ - dash}`}
          strokeLinecap="round"
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
        <text
          x="50%"
          y="50%"
          dominantBaseline="middle"
          textAnchor="middle"
          fontSize={fontSize}
          fontWeight="700"
          fill={color}
        >
          {Math.round(score)}
        </text>
      </svg>
      {label && (
        <span className="text-[10px] text-[var(--text-faint)] uppercase tracking-wider">{label}</span>
      )}
    </div>
  );
}
