"use client";

export interface RadarDataPoint {
  label: string;
  valueA: number;
  valueB: number;
}

interface RadarChartProps {
  data: RadarDataPoint[];
  nameA: string;
  nameB: string;
}

const COLOR_A = "#3b82f6";
const COLOR_B = "#8b5cf6";
const FILL_OPACITY = 0.2;
const SIZE = 280;
const CENTER = SIZE / 2;
const MAX_R = CENTER - 50;

export default function RadarChart({ data, nameA, nameB }: RadarChartProps) {
  if (!data || data.length < 3) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-500 text-sm">
        Need at least 3 dimensions to display
      </div>
    );
  }

  const levels = 5;
  const angleStep = (2 * Math.PI) / data.length;
  const levelStep = MAX_R / levels;

  const toPoint = (angle: number, r: number) => {
    const x = CENTER + r * Math.sin(angle);
    const y = CENTER - r * Math.cos(angle);
    return { x, y };
  };

  const valueToRadius = (value: number) => {
    const clamped = Math.max(0, Math.min(1, value));
    return (clamped * MAX_R * 0.9) + levelStep;
  };

  const gridLevels = Array.from({ length: levels }, (_, i) => i + 1);
  const labelOffset = 1.15;

  return (
    <div className="flex flex-col items-center gap-4">
      <svg
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        className="w-full max-w-[320px] h-auto"
        preserveAspectRatio="xMidYMid meet"
      >
        {/* Grid: concentric polygons */}
        {gridLevels.map((level) => {
          const r = level * levelStep;
          const points = data
            .map((_, i) => {
              const angle = i * angleStep - Math.PI / 2;
              const p = toPoint(angle, r);
              return `${p.x},${p.y}`;
            })
            .join(" ");
          return (
            <polygon
              key={level}
              points={points}
              fill="none"
              stroke="rgba(255,255,255,0.1)"
              strokeWidth="0.5"
            />
          );
        })}

        {/* Axis lines */}
        {data.map((_, i) => {
          const angle = i * angleStep - Math.PI / 2;
          const end = toPoint(angle, MAX_R);
          return (
            <line
              key={`axis-${i}`}
              x1={CENTER}
              y1={CENTER}
              x2={end.x}
              y2={end.y}
              stroke="rgba(255,255,255,0.15)"
              strokeWidth="0.5"
            />
          );
        })}

        {/* Person A polygon */}
        <polygon
          points={data
            .map((d, i) => {
              const angle = i * angleStep - Math.PI / 2;
              const r = valueToRadius(d.valueA);
              const p = toPoint(angle, r);
              return `${p.x},${p.y}`;
            })
            .join(" ")}
          fill={COLOR_A}
          fillOpacity={FILL_OPACITY}
          stroke={COLOR_A}
          strokeWidth="2"
        />

        {/* Person B polygon */}
        <polygon
          points={data
            .map((d, i) => {
              const angle = i * angleStep - Math.PI / 2;
              const r = valueToRadius(d.valueB);
              const p = toPoint(angle, r);
              return `${p.x},${p.y}`;
            })
            .join(" ")}
          fill={COLOR_B}
          fillOpacity={FILL_OPACITY}
          stroke={COLOR_B}
          strokeWidth="2"
        />

        {/* Axis labels and value labels */}
        {data.map((d, i) => {
          const angle = i * angleStep - Math.PI / 2;
          const labelPos = toPoint(angle, MAX_R * labelOffset);
          const valuePos = toPoint(angle, MAX_R * 0.5);
          const isLeft = labelPos.x < CENTER;

          return (
            <g key={`label-${i}`}>
              <text
                x={labelPos.x}
                y={labelPos.y}
                textAnchor={isLeft ? "end" : "start"}
                fill="#9ca3af"
                fontSize="10"
                fontWeight="500"
              >
                {d.label}
              </text>
              <text
                x={valuePos.x}
                y={valuePos.y - 4}
                textAnchor="middle"
                fill={COLOR_A}
                fontSize="8"
              >
                {Math.round(d.valueA * 100)}%
              </text>
              <text
                x={valuePos.x}
                y={valuePos.y + 4}
                textAnchor="middle"
                fill={COLOR_B}
                fontSize="8"
              >
                {Math.round(d.valueB * 100)}%
              </text>
            </g>
          );
        })}
      </svg>

      {/* Legend */}
      <div className="flex gap-6 text-sm">
        <div className="flex items-center gap-2">
          <div
            className="w-3 h-3 rounded-sm"
            style={{ backgroundColor: COLOR_A, opacity: 0.8 }}
          />
          <span className="text-gray-300">{nameA}</span>
        </div>
        <div className="flex items-center gap-2">
          <div
            className="w-3 h-3 rounded-sm"
            style={{ backgroundColor: COLOR_B, opacity: 0.8 }}
          />
          <span className="text-gray-300">{nameB}</span>
        </div>
      </div>
    </div>
  );
}
