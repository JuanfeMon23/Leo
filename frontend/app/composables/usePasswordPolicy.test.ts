import { mockNuxtImport } from '@nuxt/test-utils/runtime'
import { flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DEFAULT_PASSWORD_POLICY, clearPasswordPolicyCache, usePasswordPolicy } from './usePasswordPolicy'

const { api } = vi.hoisted(() => ({ api: vi.fn() }))
mockNuxtImport('useLeoApi', () => () => api)

const SERVER = {
  min_length: 14, max_length: 64, require_lowercase: true, require_uppercase: true, require_digit: false, require_symbol: false
}

beforeEach(() => {
  api.mockReset()
  clearPasswordPolicyCache()
  vi.useRealTimers()
})

describe('usePasswordPolicy', () => {
  it('arranca estricta (12/128, 4 clases) y adopta la del servidor al llegar', async () => {
    api.mockResolvedValue(SERVER)
    const { policy } = usePasswordPolicy()
    expect(policy.value).toEqual(DEFAULT_PASSWORD_POLICY)
    expect(DEFAULT_PASSWORD_POLICY).toEqual({
      min_length: 12, max_length: 128, require_lowercase: true, require_uppercase: true, require_digit: true, require_symbol: true
    })
    await flushPromises()
    expect(policy.value).toEqual(SERVER)
    expect(api).toHaveBeenCalledWith('/auth/password-policy', { skipSessionHandling: true })
  })

  it('si la carga falla se queda con la estricta y no lanza', async () => {
    api.mockRejectedValue(new Error('red'))
    const { policy } = usePasswordPolicy()
    await flushPromises()
    expect(policy.value).toEqual(DEFAULT_PASSWORD_POLICY)
  })

  it('una respuesta con otra forma se ignora', async () => {
    api.mockResolvedValue({ items: [] })
    const { policy } = usePasswordPolicy()
    await flushPromises()
    expect(policy.value).toEqual(DEFAULT_PASSWORD_POLICY)
  })

  it('cachea ~30 s y vuelve a pedirla después; los fallos no se cachean', async () => {
    vi.useFakeTimers()
    api.mockResolvedValue(SERVER)
    usePasswordPolicy()
    await vi.advanceTimersByTimeAsync(0)
    const second = usePasswordPolicy()
    expect(second.policy.value).toEqual(SERVER) // sin esperar: sale de la caché
    expect(api).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(31_000)
    usePasswordPolicy()
    await vi.advanceTimersByTimeAsync(0)
    expect(api).toHaveBeenCalledTimes(2)

    clearPasswordPolicyCache()
    api.mockRejectedValueOnce(new Error('red'))
    usePasswordPolicy()
    await vi.advanceTimersByTimeAsync(0)
    usePasswordPolicy()
    await vi.advanceTimersByTimeAsync(0)
    expect(api).toHaveBeenCalledTimes(4)
  })

  it('peticiones simultáneas comparten una sola llamada', async () => {
    api.mockResolvedValue(SERVER)
    usePasswordPolicy()
    usePasswordPolicy()
    await flushPromises()
    expect(api).toHaveBeenCalledTimes(1)
  })
})
