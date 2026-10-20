/**
 * Las acciones de evento (auditoría) las registra la semilla y no son permisos
 * asignables: su descripción empieza así. Lo usan `applications` (insignia,
 * sin edición) y `roles` (no se ofrecen al asignar).
 */
export const EVENT_PREFIX = 'Evento:'

export function isEventAction(description: string | null | undefined): boolean {
  return typeof description === 'string' && description.trimStart().startsWith(EVENT_PREFIX)
}
