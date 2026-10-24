import { describe, expect, it, vi } from 'vitest'
import { createDpopSigner, memoryDpopKeyStore } from './dpop'
import { createForbiddenHandler } from './forbiddenRefresh'
import { createLeoDirectTransport } from './transport'

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

describe('createForbiddenHandler', () => {
  it('refresca una vez; 403 durante el refresco no encadenan otro', async () => {
    let done!: () => void
    const refresh = vi.fn(() => new Promise<void>((r) => { done = r }))
    const handle = createForbiddenHandler({ refresh, goToForbiddenPage: vi.fn() })
    handle('refresh')
    handle('refresh')
    handle('refresh')
    expect(refresh).toHaveBeenCalledTimes(1)
    done()
    await Promise.resolve()
    await Promise.resolve()
    handle('refresh')
    expect(refresh).toHaveBeenCalledTimes(2)
  })

  it('un refresco fallido se libera y no lanza', async () => {
    const refresh = vi.fn(async () => { throw new Error('red') })
    const handle = createForbiddenHandler({ refresh, goToForbiddenPage: vi.fn() })
    handle('refresh')
    await new Promise(r => setTimeout(r))
    handle('refresh')
    expect(refresh).toHaveBeenCalledTimes(2)
  })

  it('solo forbidden-page navega', () => {
    const goToForbiddenPage = vi.fn()
    const handle = createForbiddenHandler({ refresh: async () => {}, goToForbiddenPage })
    handle('refresh')
    expect(goToForbiddenPage).not.toHaveBeenCalled()
    handle('forbidden-page')
    expect(goToForbiddenPage).toHaveBeenCalledTimes(1)
  })
})

describe('transporte: onForbidden', () => {
  async function setup(response: () => Response) {
    const onForbidden = vi.fn()
    const transport = createLeoDirectTransport({
      apiBase: 'http://localhost:8100/api/v1',
      publicUrl: 'http://localhost:8100',
      loginPath: '/login',
      signer: await createDpopSigner(memoryDpopKeyStore()),
      fetch: (async () => response()) as unknown as typeof fetch,
      onForbidden
    })
    return { transport, onForbidden }
  }

  it('403 forbidden avisa con el modo por defecto o el de la llamada', async () => {
    const { transport, onForbidden } = await setup(() => json(403, { code: 'forbidden', message: 'x' }))
    await transport.request('/a').catch(() => {})
    await transport.request('/a', { onForbidden: 'forbidden-page' }).catch(() => {})
    expect(onForbidden.mock.calls.map(c => c[1])).toEqual(['refresh', 'forbidden-page'])
  })

  it('403 con otro code (regla de negocio) no refresca', async () => {
    const { transport, onForbidden } = await setup(() => json(403, { code: 'account_locked', message: 'x' }))
    await transport.request('/a').catch(() => {})
    expect(onForbidden).not.toHaveBeenCalled()
  })

  it('skipSessionHandling no dispara onForbidden', async () => {
    const { transport, onForbidden } = await setup(() => json(403, { code: 'forbidden', message: 'x' }))
    await transport.request('/a', { skipSessionHandling: true }).catch(() => {})
    expect(onForbidden).not.toHaveBeenCalled()
  })
})
