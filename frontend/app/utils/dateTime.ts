const pad = (value: number) => String(value).padStart(2, '0')

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
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return fallback
  const time = `${pad(date.getHours())}:${pad(date.getMinutes())}${options.seconds ? `:${pad(date.getSeconds())}` : ''}`
  return `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()} ${time}`
}
