import { toUserMessage } from '#andromeda/utils/userMessage'

/**
 * Error tipado de la API de Leo (formato único `{code, message, details}` con
 * `message` en español). Compatible con las utilidades de Andromeda:
 * `toUserMessage` lee `status`/`data` y `mapApiErrorToForm` lee `data`.
 */
export class LeoApiError extends Error {
  override name = 'LeoApiError'
  /** Cuerpo en la forma que entiende `mapApiErrorToForm` de Andromeda. */
  readonly data: unknown

  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details: unknown = null,
    readonly retryAfterSeconds: number | null = null
  ) {
    super(message)
    this.data = toFormData(code, message, details)
  }

  static async fromResponse(response: Response): Promise<LeoApiError> {
    type Body = { code?: unknown, message?: unknown, details?: unknown, detail?: unknown }
    let body: Body | null = null
    try {
      const parsed: unknown = await response.json()
      if (parsed && typeof parsed === 'object') body = parsed as Body
    } catch {
      body = null // HTML de un proxy, cuerpo vacío…: no se muestra nunca
    }
    if (response.status === 422 && Array.isArray(body?.detail)) return fromFastApiValidation(response, body.detail)
    const code = typeof body?.code === 'string' ? body.code : 'http_error'
    const message = typeof body?.message === 'string' ? body.message : ''
    const details = body?.details ?? null
    return new LeoApiError(response.status, code, message, details, retryAfter(details, response))
  }
}

/** 422 de FastAPI (`{detail: [{loc, msg}]}`, sin el formato de Leo) → `validation_error` por campo. */
function fromFastApiValidation(response: Response, detail: unknown[]): LeoApiError {
  const details = detail.flatMap((d) => {
    const { loc, msg } = (d ?? {}) as { loc?: unknown, msg?: unknown }
    if (!Array.isArray(loc) || typeof msg !== 'string') return []
    const path = loc[0] === 'body' || loc[0] === 'query' || loc[0] === 'path' ? loc.slice(1) : loc
    return [{ field: path.join('.'), message: msg }]
  })
  return new LeoApiError(422, 'validation_error', 'Algunos datos no son válidos. Revisa los campos marcados.', details, retryAfter(details, response))
}

function retryAfter(details: unknown, response: Response): number | null {
  const fromDetails = (details as { retry_after_seconds?: unknown } | null)?.retry_after_seconds
  if (typeof fromDetails === 'number' && fromDetails > 0) return fromDetails
  const header = Number(response.headers.get('Retry-After'))
  return Number.isFinite(header) && header > 0 ? header : null
}

/**
 * 422 de schema: el backend manda `details: [{field, message}]`; Andromeda
 * mapea a campos la forma de FastAPI (`detail: [{loc, msg}]`).
 */
function toFormData(code: string, message: string, details: unknown): unknown {
  if (code === 'validation_error' && Array.isArray(details)) {
    return {
      detail: details
        .filter((d): d is { field: string, message: string } =>
          Boolean(d) && typeof d.field === 'string' && typeof d.message === 'string')
        .map(d => ({ loc: d.field.split('.'), msg: d.message }))
    }
  }
  return { code, message, details }
}

/** 401 que significan "no hay sesión válida": ir a login conservando a dónde volver. */
const SESSION_CODES = new Set(['not_authenticated', 'session_expired', 'invalid_dpop_proof'])

export function isSessionError(err: unknown): err is LeoApiError {
  return err instanceof LeoApiError && err.status === 401 && SESSION_CODES.has(err.code)
}

/**
 * Mensaje legible para el usuario. Los mensajes del backend de Leo ya están
 * en español y pensados para el usuario final (incluidos 401/403: "Usuario o
 * contraseña incorrectos.", "No tienes acceso a «X»…"), así que se muestran
 * salvo que parezcan técnicos; 5xx, red y lo desconocido van por
 * `toUserMessage` de Andromeda.
 */
export function leoErrorMessage(err: unknown): string {
  if (err instanceof LeoApiError) {
    const pageSize = pageSizeMessage(err)
    if (pageSize) return pageSize
  }
  if (err instanceof LeoApiError && err.status < 500 && err.message) {
    return toUserMessage({ code: err.code, message: err.message })
  }
  return toUserMessage(err)
}

/**
 * 422 de `page_size` (tope configurable en el backend, `pagination.max_page_size`).
 * Dos formas: `details: {field:'page_size', max}` con `message` ya legible
 * (Incubus), o `details: [{field:'page_size', message, max?}]` con un resumen
 * genérico (Leo/Vladimir), donde el máximo se toma de `max` o del final del texto.
 */
function pageSizeMessage(err: LeoApiError): string | null {
  if (err.status !== 422 || err.code !== 'validation_error') return null
  type Detail = { field?: unknown, message?: unknown, max?: unknown }
  const isObject = !Array.isArray(err.details) && err.details && typeof err.details === 'object'
  const hit = (Array.isArray(err.details) ? (err.details as Detail[]).find(d => d?.field === 'page_size') : null)
    ?? (isObject && (err.details as Detail).field === 'page_size' ? (err.details as Detail) : null)
  if (!hit) return null
  if (isObject && err.message) return err.message
  const text = typeof hit.message === 'string' ? /(\d+)\.?\s*$/.exec(hit.message)?.[1] : undefined
  const max = Number(hit.max ?? text)
  return Number.isFinite(max) && max > 0
    ? `Se pidieron demasiados registros por página: el máximo permitido es ${max}.`
    : 'Se pidieron demasiados registros por página.'
}
