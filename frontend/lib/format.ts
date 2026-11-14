export const BANDS = ["18–24", "25–34", "35–44", "45–54", "55–64", "65+"];

export const fmt = (value: number, digits = 0) =>
  new Intl.NumberFormat("it-IT", {maximumFractionDigits: digits, minimumFractionDigits: digits}).format(value);

export const euros = (value: number, digits = 2) =>
  new Intl.NumberFormat("it-IT", {style: "currency", currency: "EUR", maximumFractionDigits: digits}).format(value);

export const percent = (value: number, digits = 2) => `${fmt(value, digits)}%`;

export const dateTime = (iso?: string | null) =>
  iso ? new Intl.DateTimeFormat("it-IT", {day: "numeric", month: "short", hour: "2-digit", minute: "2-digit"}).format(new Date(iso)) : "";

export const shortDate = (day: string) =>
  day ? new Intl.DateTimeFormat("it-IT", {day: "numeric", month: "long", year: "numeric"}).format(new Date(`${day}T12:00:00`)) : "";

export const minutes = (seconds: number | null) =>
  seconds === null ? null : seconds < 90 ? "circa 1 minuto" : `circa ${fmt(Math.round(seconds / 60))} minuti`;
