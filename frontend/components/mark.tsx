// Ogni creatività ha un segno geometrico fisso, usato in modulo, grafico, verdetto ed elenco.
// La forma, non solo il colore, distingue A da B: leggibile anche in scala di grigi.

const MARKS = [
  {name: "cerchio", color: "var(--mark-a)"},
  {name: "quadrato", color: "var(--mark-b)"},
  {name: "triangolo", color: "var(--mark-c)"},
  {name: "rombo", color: "var(--mark-d)"}
] as const;

export const markColor = (index: number) => MARKS[index % MARKS.length].color;
export const markLetter = (index: number) => String.fromCharCode(65 + index);

// Sul campo blu il cerchio blu sparirebbe: lì i segni usano la loro versione chiara.
const ON_DARK = ["#FFFFFF", "#F0A300", "#6FD3A8", "#FFFFFF"];

export function Mark({index, size = 18, onDark = false}: {index: number; size?: number; onDark?: boolean}) {
  const m = onDark ? {color: ON_DARK[index % MARKS.length]} : MARKS[index % MARKS.length];
  return (
    <svg className="mark" width={size} height={size} viewBox="0 0 20 20" aria-hidden="true" focusable="false">
      {index % 4 === 0 && <circle cx="10" cy="10" r="9" fill={m.color} />}
      {index % 4 === 1 && <rect x="1.5" y="1.5" width="17" height="17" fill={m.color} />}
      {index % 4 === 2 && <polygon points="10,1 19,18 1,18" fill={m.color} />}
      {index % 4 === 3 && <polygon points="10,1 19,10 10,19 1,10" fill={m.color} />}
    </svg>
  );
}

export function MarkLabel({index, text}: {index: number; text?: string}) {
  return (
    <span className="mark-label">
      <Mark index={index} />
      <span>{text ?? `Creatività ${markLetter(index)}`}</span>
    </span>
  );
}
