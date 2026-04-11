/**
 * Circular score indicator — used on conviction score and combined signal score.
 */

interface Props {
  score: number; // 0–100
  size?: number;
  label?: string;
}

function scoreColor(score: number) {
  if (score >= 70) return "#437A22";
  if (score >= 45) return "#01696F";
  if (score >= 25) return "#964219";
  return "#A12C7B";
}

export default function ScoreRing({ score, size = 44, label }: Props) {
  const r = (size - 6) / 2;
  const circ = 2 * Math.PI * r;
  const dash = (score / 100) * circ;
  const color = scoreColor(score);

  return (
    <div className="flex flex-col items-center gap-0.5">
      <svg width={size} height={size}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#D4D1CA" strokeWidth={3} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={3}
          strokeDasharray={`${dash} ${circ - dash}`}
          strokeLinecap="round"
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
        <text
          x="50%"
          y="50%"
          dominantBaseline="middle"
          textAnchor="middle"
          fontSize={size < 40 ? 10 : 12}
          fontWeight="600"
          fill={color}
        >
          {Math.round(score)}
        </text>
      </svg>
      {label && (
        <span className="text-[10px] text-[var(--text-faint)]">{label}</span>
      )}
    </div>
  );
}
