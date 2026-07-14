import type { Zone } from "../types";

interface BlueprintProps {
  zones: Zone[];
}

const PADDING = 18;

export function Blueprint({ zones }: BlueprintProps) {
  if (zones.length === 0) {
    return <p className="empty-state">No canonical zones are available.</p>;
  }

  const maxX = Math.max(...zones.map((zone) => zone.boundary[0] + zone.boundary[2]));
  const maxY = Math.max(...zones.map((zone) => zone.boundary[1] + zone.boundary[3]));
  const viewBox = `${-PADDING} ${-PADDING} ${maxX + PADDING * 2} ${maxY + PADDING * 2}`;

  return (
    <div className="blueprint-shell">
      <svg
        className="blueprint"
        viewBox={viewBox}
        role="img"
        aria-labelledby="blueprint-title blueprint-description"
      >
        <title id="blueprint-title">Canonical housefile zone blueprint</title>
        <desc id="blueprint-description">
          Owner view of canonical rectangular zones. No-go zones use red hatching and
          restricted zones use amber dashed borders.
        </desc>
        <defs>
          <pattern id="no-go-hatch" width="9" height="9" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1="0" x2="0" y1="0" y2="9" className="hatch-line" />
          </pattern>
        </defs>
        {zones.map((zone) => {
          const [x, y, width, height] = zone.boundary;
          return (
            <g key={zone.id} className={`zone zone-${zone.access}`}>
              <rect
                x={x + 3}
                y={y + 3}
                width={Math.max(width - 6, 1)}
                height={Math.max(height - 6, 1)}
                rx="2"
              />
              <text x={x + 12} y={y + 21} className="zone-name">
                {zone.name}
              </text>
              <text x={x + 12} y={y + Math.max(height - 11, 35)} className="zone-state">
                {zone.outdoor ? "OUTDOOR · " : ""}{zone.access.toUpperCase()}
              </text>
            </g>
          );
        })}
      </svg>
      <ul className="legend" aria-label="Blueprint access legend">
        <li><span className="legend-mark open" />Open</li>
        <li><span className="legend-mark restricted" />Restricted</li>
        <li><span className="legend-mark no-go" />No-go</li>
      </ul>
    </div>
  );
}
