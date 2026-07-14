import { useId } from "react";
import type { Zone } from "../types";

interface BlueprintProps {
  zones: Zone[];
}

const PADDING = 18;
const LABEL_INSET = 12;
const NAME_CHARACTER_WIDTH = 7.25;
const STATE_CHARACTER_WIDTH = 5.1;

function ellipsize(value: string, maxCharacters: number): string {
  if (value.length <= maxCharacters) return value;
  if (maxCharacters <= 1) return "…";
  return `${value.slice(0, maxCharacters - 1)}…`;
}

export function fitLabelLines(
  value: string,
  availableWidth: number,
  characterWidth: number,
): string[] {
  const normalized = value.trim().replace(/\s+/g, " ");
  if (!normalized) return [""];

  const maxCharacters = Math.max(3, Math.floor(availableWidth / characterWidth));
  if (normalized.length <= maxCharacters) return [normalized];

  const words = normalized.split(" ");
  if (words.length === 1) return [ellipsize(normalized, maxCharacters)];

  let splitAt = 1;
  let firstLine = words[0];
  while (
    splitAt < words.length
    && `${firstLine} ${words[splitAt]}`.length <= maxCharacters
  ) {
    firstLine = `${firstLine} ${words[splitAt]}`;
    splitAt += 1;
  }

  const secondLine = words.slice(splitAt).join(" ");
  if (!secondLine) return [ellipsize(firstLine, maxCharacters)];
  return [
    ellipsize(firstLine, maxCharacters),
    ellipsize(secondLine, maxCharacters),
  ];
}

export function Blueprint({ zones }: BlueprintProps) {
  const blueprintId = useId().replace(/:/g, "");
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
          {zones.map((zone, index) => {
            const [x, y, width, height] = zone.boundary;
            return (
              <clipPath
                id={`${blueprintId}-zone-label-${index}`}
                key={zone.id}
                clipPathUnits="userSpaceOnUse"
              >
                <rect
                  x={x + 6}
                  y={y + 6}
                  width={Math.max(width - 12, 1)}
                  height={Math.max(height - 12, 1)}
                />
              </clipPath>
            );
          })}
        </defs>
        {zones.map((zone, index) => {
          const [x, y, width, height] = zone.boundary;
          const availableWidth = Math.max(width - LABEL_INSET * 2, 1);
          const state = `${zone.outdoor ? "OUTDOOR · " : ""}${zone.access.toUpperCase()}`;
          const nameLines = fitLabelLines(zone.name, availableWidth, NAME_CHARACTER_WIDTH);
          const stateLines = fitLabelLines(state, availableWidth, STATE_CHARACTER_WIDTH);
          const stateY = y + Math.max(height - 11, 35) - ((stateLines.length - 1) * 9);
          const labelClip = `url(#${blueprintId}-zone-label-${index})`;
          return (
            <g key={zone.id} className={`zone zone-${zone.access}`}>
              <title>{zone.name} — {state}</title>
              <rect
                x={x + 3}
                y={y + 3}
                width={Math.max(width - 6, 1)}
                height={Math.max(height - 6, 1)}
                rx="2"
              />
              <text x={x + LABEL_INSET} y={y + 21} className="zone-name" clipPath={labelClip}>
                {nameLines.map((line, lineIndex) => (
                  <tspan
                    x={x + LABEL_INSET}
                    dy={lineIndex === 0 ? 0 : 13}
                    key={`${line}-${lineIndex}`}
                  >
                    {line}
                  </tspan>
                ))}
              </text>
              <text x={x + LABEL_INSET} y={stateY} className="zone-state" clipPath={labelClip}>
                {stateLines.map((line, lineIndex) => (
                  <tspan
                    x={x + LABEL_INSET}
                    dy={lineIndex === 0 ? 0 : 9}
                    key={`${line}-${lineIndex}`}
                  >
                    {line}
                  </tspan>
                ))}
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
