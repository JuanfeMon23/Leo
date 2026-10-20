/**
 * Reloj de inactividad de la sesión (ventana deslizante), sin DOM ni Vue:
 * quien lo usa le pasa la actividad (mouse, teclado, scroll, toque,
 * visibilidad) y reacciona a sus eventos. Se prueba con timers falsos.
 *
 * - `activity()`: actividad local (con throttle). Reinicia la ventana, cierra
 *   el aviso si estaba abierto, la comunica a las demás pestañas y manda un
 *   heartbeat al servidor como máximo cada `heartbeatIntervalMs` (más uno
 *   final si hubo actividad después del último, para que el servidor —la
 *   fuente de verdad— nunca quede atrás del cliente).
 * - `warnBeforeMs` antes de vencer → `onWarn(deadline)`.
 * - Al vencer → `onExpire('idle')` y avisa a las demás pestañas
 *   (`onRemoteLogout` en ellas).
 * - Actividad que llega con la ventana ya vencida (timers suspendidos en una
 *   pestaña de fondo) no revive la sesión: cierra.
 */

export type IdleLogoutReason = 'idle' | 'manual' | 'expired'

export type IdleMessage =
  | { type: 'activity', at: number }
  | { type: 'heartbeat', at: number }
  | { type: 'logout', reason: IdleLogoutReason }

/** Canal entre pestañas del mismo origen (BroadcastChannel en el navegador). */
export interface IdleChannel {
  post(message: IdleMessage): void
  subscribe(listener: (message: IdleMessage) => void): () => void
  close(): void
}

export interface IdleTrackerOptions {
  timeoutMs: number
  warnBeforeMs: number
  heartbeatIntervalMs: number
  /** Actividad local más seguida que esto se ignora (por defecto 1 s). */
  throttleMs?: number
  channel?: IdleChannel
  /** Avisa al servidor de la actividad (`POST /auth/activity` o el BFF). */
  heartbeat: () => Promise<unknown>
  onWarn: (deadline: number) => void
  /** Se cerró el aviso porque hubo actividad. */
  onActive: () => void
  onExpire: (reason: 'idle') => void
  /** Otra pestaña cerró la sesión. */
  onRemoteLogout: (reason: IdleLogoutReason) => void
}

export interface IdleTracker {
  start(): void
  stop(): void
  activity(): void
  stayConnected(): void
  /** Cierra si la ventana ya venció (p. ej. al volver a la pestaña). */
  check(): void
  /** Cierra la sesión en las demás pestañas y detiene este reloj. */
  broadcastLogout(reason: IdleLogoutReason): void
  readonly warning: boolean
  readonly lastActivity: number
}

export function createIdleTracker(options: IdleTrackerOptions): IdleTracker {
  const throttleMs = options.throttleMs ?? 1000
  const now = () => Date.now()

  let running = false
  let lastActivity = 0
  let lastLocalActivity = 0
  let lastHeartbeat = 0
  let warning = false
  let timer: ReturnType<typeof setTimeout> | undefined
  let trailingHeartbeat: ReturnType<typeof setTimeout> | undefined
  let unsubscribe: (() => void) | undefined

  const deadline = () => lastActivity + options.timeoutMs

  function clearTimers() {
    if (timer !== undefined) clearTimeout(timer)
    if (trailingHeartbeat !== undefined) clearTimeout(trailingHeartbeat)
    timer = undefined
    trailingHeartbeat = undefined
  }

  function schedule() {
    if (timer !== undefined) clearTimeout(timer)
    if (!running) return
    const warnAt = deadline() - options.warnBeforeMs
    const at = !warning && now() < warnAt ? warnAt : deadline()
    timer = setTimeout(tick, Math.max(0, at - now()))
  }

  function tick() {
    timer = undefined
    if (!running) return
    if (now() >= deadline()) return expire()
    if (!warning && now() >= deadline() - options.warnBeforeMs) {
      warning = true
      options.onWarn(deadline())
    }
    schedule()
  }

  function expire() {
    stop()
    options.channel?.post({ type: 'logout', reason: 'idle' })
    options.onExpire('idle')
  }

  function sendHeartbeat() {
    if (trailingHeartbeat !== undefined) clearTimeout(trailingHeartbeat)
    trailingHeartbeat = undefined
    lastHeartbeat = now()
    options.channel?.post({ type: 'heartbeat', at: lastHeartbeat })
    // Un 401 lo maneja el transporte (redirige a login); aquí no se reintenta.
    options.heartbeat().catch(() => {})
  }

  function maybeHeartbeat(force: boolean) {
    if (force || now() - lastHeartbeat >= options.heartbeatIntervalMs) return sendHeartbeat()
    trailingHeartbeat ??= setTimeout(() => {
      trailingHeartbeat = undefined
      if (running && lastActivity > lastHeartbeat) sendHeartbeat()
    }, lastHeartbeat + options.heartbeatIntervalMs - now())
  }

  function touch(at: number) {
    lastActivity = Math.max(lastActivity, at)
    if (warning) {
      warning = false
      options.onActive()
    }
    schedule()
  }

  function onMessage(message: IdleMessage) {
    if (!running) return
    if (message.type === 'activity') touch(message.at)
    else if (message.type === 'heartbeat') lastHeartbeat = Math.max(lastHeartbeat, message.at)
    else {
      stop()
      options.onRemoteLogout(message.reason)
    }
  }

  function localActivity(force: boolean) {
    if (!running) return
    const at = now()
    if (at >= deadline()) return expire()
    if (!force && !warning && at - lastLocalActivity < throttleMs) return
    lastLocalActivity = at
    touch(at)
    options.channel?.post({ type: 'activity', at })
    maybeHeartbeat(force)
  }

  function stop() {
    running = false
    warning = false
    clearTimers()
    unsubscribe?.()
    unsubscribe = undefined
  }

  return {
    start() {
      if (running) return
      running = true
      const at = now()
      lastActivity = at
      lastLocalActivity = at
      // La sesión se acaba de validar contra el servidor (/me): cuenta como heartbeat.
      lastHeartbeat = at
      unsubscribe = options.channel?.subscribe(onMessage)
      options.channel?.post({ type: 'activity', at })
      schedule()
    },
    stop,
    activity: () => localActivity(false),
    stayConnected: () => localActivity(true),
    check() {
      if (running && now() >= deadline()) expire()
    },
    broadcastLogout(reason) {
      stop()
      options.channel?.post({ type: 'logout', reason })
    },
    get warning() {
      return warning
    },
    get lastActivity() {
      return lastActivity
    }
  }
}

/** Canal real entre pestañas; sin BroadcastChannel (navegador antiguo), no sincroniza. */
export function broadcastIdleChannel(name = 'leo-client:session'): IdleChannel | undefined {
  if (typeof BroadcastChannel === 'undefined') return undefined
  const channel = new BroadcastChannel(name)
  return {
    post: message => channel.postMessage(message),
    subscribe(listener) {
      const handler = (event: MessageEvent<IdleMessage>) => listener(event.data)
      channel.addEventListener('message', handler)
      return () => channel.removeEventListener('message', handler)
    },
    close: () => channel.close()
  }
}
