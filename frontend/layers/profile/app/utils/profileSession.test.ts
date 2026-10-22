import { describe, expect, it, vi } from 'vitest'
import { createDpopSigner, memoryDpopKeyStore } from '#leo-client/lib/dpop'
import { createLeoDirectTransport } from '#leo-client/lib/transport'

/**
 * Contrato con leo-client: el 401 `invalid_credentials` de
 * `POST /auth/me/password` NO es una sesión caducada y no debe cerrar la
 * sesión; solo `session_expired`, `not_authenticated` e `invalid_dpop_proof`
 * lo hacen (y `skipSessionHandling` los evita aun así).
 */
async function setup(status: number, code: string) {
  const onUnauthorized = vi.fn()
  const transport = createLeoDirectTransport({
    apiBase: 'http://api.test/api/v1',
    publicUrl: 'http://api.test',
    loginPath: '/login',
    signer: await createDpopSigner(memoryDpopKeyStore()),
    fetch: (async () =>
      new Response(JSON.stringify({ code, message: 'x' }), { status, headers: { 'Content-Type': 'application/json' } })
    ) as unknown as typeof fetch,
    onUnauthorized
  })
  return { transport, onUnauthorized }
}

const change = { method: 'POST', body: { current_password: 'a', new_password: 'b' } } as const

describe('cambio de contraseña y cierre de sesión', () => {
  it('401 invalid_credentials no cierra la sesión (ni siquiera sin skipSessionHandling)', async () => {
    const { transport, onUnauthorized } = await setup(401, 'invalid_credentials')
    await expect(transport.request('/auth/me/password', change)).rejects.toMatchObject({ code: 'invalid_credentials' })
    await expect(transport.request('/auth/me/password', { ...change, skipSessionHandling: true })).rejects.toMatchObject({ status: 401 })
    expect(onUnauthorized).not.toHaveBeenCalled()
  })

  it.each(['session_expired', 'not_authenticated', 'invalid_dpop_proof'])('401 %s sí cierra la sesión', async (code) => {
    const { transport, onUnauthorized } = await setup(401, code)
    await expect(transport.request('/auth/me/password', change)).rejects.toMatchObject({ code })
    expect(onUnauthorized).toHaveBeenCalledOnce()
  })
})
