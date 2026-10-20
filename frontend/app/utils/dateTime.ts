const pad = (n: number) => String(n).padStart(2, '0')

export interface FormatLocalDateTimeOptions {
  /** Incluir segundos (`HH:MM:SS`). */
  seconds?: boolean
  /** Texto cuando no hay fecha o es inválida (por defecto «—»). */
  fallback?: string
}

/** `DD/MM/AAAA HH:MM` (o con segundos) en hora local del navegador. */
export function formatLocalDateTime(iso: string | null | undefined, options: FormatLocalDateTimeOptions = {}): string {
  const fallback = options.fallback ?? '—'
  if (!iso) return fallback
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return fallback
  const time = `${pad(d.getHours())}:${pad(d.getMinutes())}${options.seconds ? `:${pad(d.getSeconds())}` : ''}`
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} ${time}`
}
