import { describe, expect, it } from 'vitest'
import { safeReturnUrl } from './returnUrl'

const apps = [
  { name: 'Vladimir', base_url: 'https://vladimir.example.co' },
  { name: 'Incubus', base_url: 'http://localhost:3200/' }
]

describe('safeReturnUrl', () => {
  it('acepta una URL del origen de una app y devuelve su nombre', () => {
    expect(safeReturnUrl('https://vladimir.example.co/samples?x=1#a', apps)).toEqual({
      url: 'https://vladimir.example.co/samples?x=1#a',
      app: apps[0]
    })
    expect(safeReturnUrl('http://localhost:3200/', apps)?.app.name).toBe('Incubus')
    expect(safeReturnUrl('  https://vladimir.example.co  ', apps)?.app.name).toBe('Vladimir')
  })

  it.each([
    ['esquema javascript:', 'javascript:alert(1)'],
    ['javascript con mayúsculas y espacios', ' JaVaScRiPt:alert(1)'],
    ['data:', 'data:text/html,<script>alert(1)</script>'],
    ['otro origen', 'https://evil.example/x'],
    ['subdominio del origen permitido', 'https://vladimir.example.co.evil.example/'],
    ['mismo host, otro puerto', 'http://localhost:3999/'],
    ['mismo host, otro esquema', 'http://vladimir.example.co/'],
    ['credenciales para llevar a otro host', 'https://vladimir.example.co@evil.example/'],
    ['credenciales con el origen permitido', 'https://user:pw@vladimir.example.co/'],
    ['ruta relativa', '/users'],
    ['protocolo relativo', '//evil.example'],
    ['barras invertidas', '\\evil.example'],
    ['sin esquema', 'vladimir.example.co/x'],
    ['vacío', ''],
    ['solo espacios', '   ']
  ])('rechaza %s', (_name, value) => {
    expect(safeReturnUrl(value, apps)).toBeNull()
  })

  it.each([undefined, null, 42, ['https://vladimir.example.co'], {}])('rechaza un valor que no es texto (%o)', (value) => {
    expect(safeReturnUrl(value, apps)).toBeNull()
  })

  it('sin apps accesibles no hay destino', () => {
    expect(safeReturnUrl('https://vladimir.example.co', [])).toBeNull()
  })

  it('ignora apps con base_url inválida', () => {
    expect(safeReturnUrl('https://vladimir.example.co', [{ name: 'X', base_url: 'no-es-url' }])).toBeNull()
  })
})
