function plural(n: number, unit: string): string {
  return `${n} ${unit}${n === 1 ? '' : 's'}`
}

/** "45 segundos", "2 minutos", "1 hora": espera legible (se redondea hacia arriba). */
export function formatWait(seconds: number): string {
  if (seconds < 60) return plural(Math.max(1, Math.ceil(seconds)), 'segundo')
  if (seconds < 3600) return plural(Math.ceil(seconds / 60), 'minuto')
  return plural(Math.ceil(seconds / 3600), 'hora')
}
