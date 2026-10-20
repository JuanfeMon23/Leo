import { describe, expect, it } from 'vitest'
import { summarizeUserAgent } from './userAgent'

describe('summarizeUserAgent', () => {
  it('Chrome en Windows', () => {
    expect(summarizeUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'))
      .toBe('Chrome 141 en Windows')
  })

  it('Edge se distingue de Chrome', () => {
    expect(summarizeUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0'))
      .toBe('Edge 141 en Windows')
  })

  it('Firefox en Linux', () => {
    expect(summarizeUserAgent('Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0')).toBe('Firefox 130 en Linux')
  })

  it('Safari en iPhone (iOS) y Chrome en Android', () => {
    expect(summarizeUserAgent('Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'))
      .toBe('Safari 17 en iOS')
    expect(summarizeUserAgent('Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Mobile Safari/537.36'))
      .toBe('Chrome 141 en Android')
  })

  it('Safari en macOS', () => {
    expect(summarizeUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15'))
      .toBe('Safari 17 en macOS')
  })

  it('clientes no navegador y vacío', () => {
    expect(summarizeUserAgent('python-httpx/0.27')).toBe('python-httpx/0.27')
    expect(summarizeUserAgent(null)).toBe('Desconocido')
    expect(summarizeUserAgent('')).toBe('Desconocido')
  })

  it('un texto desconocido muy largo se recorta', () => {
    expect(summarizeUserAgent('x'.repeat(200)).length).toBeLessThanOrEqual(60)
  })
})
