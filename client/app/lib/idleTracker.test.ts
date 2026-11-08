import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createIdleTracker } from './idleTracker'
import type { IdleChannel, IdleMessage, IdleTrackerOptions } from './idleTracker'

const MIN = 60_000
const TIMEOUT = 30 * MIN
const WARN = 60_000

/** Canal en memoria que imita BroadcastChannel: entrega a las demás pestañas, no a sí misma. */
function channelHub() {
  const members = new Set<{ deliver: (message: IdleMessage) => void }>()
  return () => {
    let listener: ((message: IdleMessage) => void) | null = null
    const member = { deliver: (message: IdleMessage) => listener?.(message) }
    members.add(member)
    const channel: IdleChannel = {
      post: (message) => { for (const other of members) if (other !== member) other.deliver(message) },
      subscribe: (callback) => { listener = callback; return () => { listener = null } },
      close: () => { members.delete(member) }
    }
    return channel
  }
}

function setup(overrides: Partial<IdleTrackerOptions> = {}) {
  const callbacks = {
    heartbeat: vi.fn(async () => {}),
    onWarn: vi.fn(),
    onActive: vi.fn(),
    onExpire: vi.fn(),
    onRemoteLogout: vi.fn()
  }
  const tracker = createIdleTracker({
    timeoutMs: TIMEOUT,
    warnBeforeMs: WARN,
    heartbeatIntervalMs: MIN,
    throttleMs: 1000,
    ...callbacks,
    ...overrides
  })
  return { tracker, ...callbacks }
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-10-19T10:00:00Z'))
})
afterEach(() => vi.useRealTimers())

describe('createIdleTracker', () => {
  it('avisa 60 s antes del vencimiento y cierra la sesión al cumplirse el tiempo sin actividad', () => {
    const { tracker, onWarn, onExpire } = setup()
    tracker.start()

    vi.advanceTimersByTime(TIMEOUT - WARN - 1)
    expect(onWarn).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1)
    expect(onWarn).toHaveBeenCalledTimes(1)
    expect(onWarn).toHaveBeenCalledWith(Date.now() + WARN)
    expect(onExpire).not.toHaveBeenCalled()

    vi.advanceTimersByTime(WARN)
    expect(onExpire).toHaveBeenCalledTimes(1)
    expect(onExpire).toHaveBeenCalledWith('idle')
  })

  it('la actividad reinicia la ventana de inactividad', () => {
    const { tracker, onWarn, onExpire } = setup()
    tracker.start()
    vi.advanceTimersByTime(20 * MIN)
    tracker.activity()
    vi.advanceTimersByTime(20 * MIN)
    expect(onWarn).not.toHaveBeenCalled()
    vi.advanceTimersByTime(10 * MIN)
    expect(onExpire).toHaveBeenCalledTimes(1)
  })

  it('la actividad durante el aviso lo cierra (onActive) y aplaza el cierre', () => {
    const { tracker, onActive, onExpire } = setup()
    tracker.start()
    vi.advanceTimersByTime(TIMEOUT - 30_000)
    expect(tracker.warning).toBe(true)
    tracker.activity()
    expect(onActive).toHaveBeenCalledTimes(1)
    expect(tracker.warning).toBe(false)
    vi.advanceTimersByTime(TIMEOUT - WARN - 1)
    expect(onExpire).not.toHaveBeenCalled()
  })

  it('"seguir conectado" envía un heartbeat inmediato aunque no haya pasado el intervalo', () => {
    const { tracker, heartbeat, onActive } = setup()
    tracker.start()
    vi.advanceTimersByTime(TIMEOUT - 10_000)
    tracker.stayConnected()
    expect(onActive).toHaveBeenCalledTimes(1)
    expect(heartbeat).toHaveBeenCalledTimes(1)
  })

  it('agrupa la actividad (throttle) y manda como máximo un heartbeat por minuto, más uno final si hubo actividad', () => {
    const { tracker, heartbeat } = setup()
    tracker.start() // la sesión acaba de validarse: cuenta como heartbeat
    for (let i = 0; i < 50; i++) {
      tracker.activity()
      vi.advanceTimersByTime(100)
    }
    expect(heartbeat).not.toHaveBeenCalled()
    vi.advanceTimersByTime(MIN) // vence el intervalo: heartbeat final por la actividad pendiente
    expect(heartbeat).toHaveBeenCalledTimes(1)

    vi.advanceTimersByTime(5 * MIN) // sin actividad: no hay más heartbeats
    expect(heartbeat).toHaveBeenCalledTimes(1)

    tracker.activity() // pasó más de un minuto: heartbeat inmediato
    expect(heartbeat).toHaveBeenCalledTimes(2)
  })

  it('no revive una sesión ya vencida si llega actividad tarde (timers suspendidos)', () => {
    const { tracker, onExpire, heartbeat } = setup()
    tracker.start()
    // Simula una pestaña en segundo plano: el reloj avanza sin que corran los timers.
    vi.setSystemTime(Date.now() + TIMEOUT + 5_000)
    tracker.activity()
    expect(onExpire).toHaveBeenCalledWith('idle')
    expect(heartbeat).not.toHaveBeenCalled()
  })

  it('check() cierra la sesión si ya venció (al volver a la pestaña)', () => {
    const { tracker, onExpire } = setup()
    tracker.start()
    vi.setSystemTime(Date.now() + TIMEOUT)
    tracker.check()
    expect(onExpire).toHaveBeenCalledTimes(1)
  })

  it('stop() cancela los timers', () => {
    const { tracker, onWarn, onExpire } = setup()
    tracker.start()
    tracker.stop()
    vi.advanceTimersByTime(2 * TIMEOUT)
    expect(onWarn).not.toHaveBeenCalled()
    expect(onExpire).not.toHaveBeenCalled()
  })
})

describe('sincronización entre pestañas', () => {
  it('la actividad en una pestaña mantiene viva la sesión en las otras', () => {
    const open = channelHub()
    const firstTab = setup({ channel: open() })
    const secondTab = setup({ channel: open() })
    firstTab.tracker.start()
    secondTab.tracker.start()

    vi.advanceTimersByTime(25 * MIN)
    firstTab.tracker.activity()
    vi.advanceTimersByTime(25 * MIN)

    expect(firstTab.onExpire).not.toHaveBeenCalled()
    expect(secondTab.onExpire).not.toHaveBeenCalled()
    expect(secondTab.onWarn).not.toHaveBeenCalled()
  })

  it('la actividad en otra pestaña cierra el aviso de esta', () => {
    const open = channelHub()
    const firstTab = setup({ channel: open() })
    const secondTab = setup({ channel: open() })
    firstTab.tracker.start()
    secondTab.tracker.start()
    vi.advanceTimersByTime(TIMEOUT - 30_000)
    expect(secondTab.tracker.warning).toBe(true)
    firstTab.tracker.stayConnected()
    expect(secondTab.onActive).toHaveBeenCalledTimes(1)
    expect(secondTab.tracker.warning).toBe(false)
  })

  it('el heartbeat de una pestaña evita heartbeats repetidos en las otras', () => {
    const open = channelHub()
    const firstTab = setup({ channel: open() })
    const secondTab = setup({ channel: open() })
    firstTab.tracker.start()
    secondTab.tracker.start()
    vi.advanceTimersByTime(2 * MIN)
    firstTab.tracker.activity()
    expect(firstTab.heartbeat).toHaveBeenCalledTimes(1)
    vi.advanceTimersByTime(1000)
    secondTab.tracker.activity()
    expect(secondTab.heartbeat).not.toHaveBeenCalled()
  })

  it('cerrar sesión en una pestaña cierra todas', () => {
    const open = channelHub()
    const firstTab = setup({ channel: open() })
    const secondTab = setup({ channel: open() })
    const thirdTab = setup({ channel: open() })
    firstTab.tracker.start()
    secondTab.tracker.start()
    thirdTab.tracker.start()

    firstTab.tracker.broadcastLogout('manual')

    expect(secondTab.onRemoteLogout).toHaveBeenCalledWith('manual')
    expect(thirdTab.onRemoteLogout).toHaveBeenCalledWith('manual')
    expect(firstTab.onRemoteLogout).not.toHaveBeenCalled()
    // Las otras dejan de contar: no vuelven a cerrar por inactividad.
    vi.advanceTimersByTime(2 * TIMEOUT)
    expect(secondTab.onExpire).not.toHaveBeenCalled()
  })

  it('el cierre por inactividad de una pestaña se propaga a las demás', () => {
    const open = channelHub()
    const firstTab = setup({ channel: open() })
    const secondTab = setup({ channel: open() })
    firstTab.tracker.start()
    secondTab.tracker.start()
    vi.advanceTimersByTime(TIMEOUT)
    // Vence primero la de `a` (su timer se registró antes); `b` se entera por el canal.
    expect(firstTab.onExpire).toHaveBeenCalledWith('idle')
    expect(secondTab.onRemoteLogout).toHaveBeenCalledWith('idle')
    expect(secondTab.onExpire).not.toHaveBeenCalled()
  })

  it('abrir una pestaña nueva cuenta como actividad para las demás', () => {
    const open = channelHub()
    const firstTab = setup({ channel: open() })
    const secondTab = setup({ channel: open() })
    firstTab.tracker.start()
    vi.advanceTimersByTime(20 * MIN)
    secondTab.tracker.start()
    vi.advanceTimersByTime(20 * MIN)
    expect(firstTab.onExpire).not.toHaveBeenCalled()
    expect(firstTab.onWarn).not.toHaveBeenCalled()
  })
})
