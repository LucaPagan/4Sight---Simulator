import type {ReactNode} from "react";

// Campo blu pieno con tre forme piatte: l'unico gesto decorativo dell'app, in tema con i segni delle creatività.
export function Hero({title, lead, children}: {title: ReactNode; lead?: ReactNode; children?: ReactNode}) {
  return (
    <header className="hero">
      <div className="hero-copy">
        <h1>{title}</h1>
        {lead && <p className="lead">{lead}</p>}
        {children}
      </div>
      <svg className="hero-shapes" viewBox="0 0 220 160" aria-hidden="true" focusable="false">
        <circle cx="62" cy="62" r="52" fill="#F0A300" />
        <rect x="98" y="34" width="96" height="96" fill="#FFFFFF" />
        <polygon points="62,152 118,64 174,152" fill="#6FD3A8" />
      </svg>
    </header>
  );
}
