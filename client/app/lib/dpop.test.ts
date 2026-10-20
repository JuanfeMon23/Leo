import { describe, expect, it } from 'vitest'
import {
  base64UrlDecode,
  createDpopProof,
  createDpopSigner,
  dpopHtu,
  generateDpopKeyPair,
  jwkThumbprint,
  memoryDpopKeyStore,
  publicJwk
} from './dpop'

function decodeJson(segment: string): Record<string, unknown> {
  return JSON.parse(new TextDecoder().decode(base64UrlDecode(segment)))
}

describe('jwkThumbprint (RFC 7638)', () => {
  it('coincide con el vector RSA de la RFC 7638 §3.1', async () => {
    const jwk = {
      kty: 'RSA',
      n: '0vx7agoebGcQSuuPiLJXZptN9nndrQmbXEps2aiAFbWhM78LhWx4cbbfAAtVT86zwu1RK7aPFFxuhDR1L6tSoc_BJECPebWKRXjBZCiFV4n3oknjhMstn64tZ_2W-5JsGY4Hc5n9yBXArwl93lqt7_RN5w6Cf0h4QyQ5v-65YGjQR0_FDW2QvzqY368QQMicAtaSqzs8KJZgnYb9c7d0zgdAZHzu6qMQvRL5hajrn1n91CbOpbISD08qNLyrdkt-bFTWhAI4vMQFh6WeZu0fM4lFd2NcRwr3XPksINHaQ-G_xBniIqbw0Ls1jF44-csFCur-kEgU8awapJzKnqDKgw',
      e: 'AQAB',
      alg: 'RS256',
      kid: '2011-04-29'
    }
    expect(await jwkThumbprint(jwk)).toBe('NzbLsXh8uDCcd-6MNwXF4W_7noWXFZAfHkxZsRGC9Xs')
  })

  it('coincide con el jkt del ejemplo EC P-256 de la RFC 9449 (y con el backend)', async () => {
    const jwk = {
      kty: 'EC',
      x: 'l8tFrhx-34tV3hRICRDY9zCkDlpBhF42UQUfWVAWBFs',
      y: '9VE4jf_Ok_o64zbTTlcuNJajHmt6v9TDVrU0CdvGRDA',
      crv: 'P-256'
    }
    expect(await jwkThumbprint(jwk)).toBe('0ZcOCORZNYy-DWpqq30jZyJGHTN0d2HglBV3uiguA4I')
  })

  it('ignora miembros que no son obligatorios (orden y extras no cambian el resultado)', async () => {
    const a = await jwkThumbprint({ crv: 'P-256', kty: 'EC', x: 'l8tFrhx-34tV3hRICRDY9zCkDlpBhF42UQUfWVAWBFs', y: '9VE4jf_Ok_o64zbTTlcuNJajHmt6v9TDVrU0CdvGRDA', ext: true, key_ops: ['verify'] })
    expect(a).toBe('0ZcOCORZNYy-DWpqq30jZyJGHTN0d2HglBV3uiguA4I')
  })
})

describe('generateDpopKeyPair', () => {
  it('genera ECDSA P-256 con la llave privada NO exportable', async () => {
    const pair = await generateDpopKeyPair()
    expect(pair.privateKey.extractable).toBe(false)
    expect(pair.privateKey.algorithm).toMatchObject({ name: 'ECDSA', namedCurve: 'P-256' })
    await expect(crypto.subtle.exportKey('jwk', pair.privateKey)).rejects.toThrow()
    await expect(crypto.subtle.exportKey('pkcs8', pair.privateKey)).rejects.toThrow()
  })

  it('la llave pública se expone solo con sus miembros públicos', async () => {
    const pair = await generateDpopKeyPair()
    const jwk = await publicJwk(pair.publicKey)
    expect(Object.keys(jwk).sort()).toEqual(['crv', 'kty', 'x', 'y'])
    expect(jwk).toMatchObject({ kty: 'EC', crv: 'P-256' })
  })
})

describe('createDpopProof', () => {
  it('arma un JWS ES256 compacto con header y claims de la RFC 9449, verificable con la llave pública', async () => {
    const pair = await generateDpopKeyPair()
    const proof = await createDpopProof(pair, {
      htm: 'post',
      htu: 'http://localhost:8100/api/v1/auth/login',
      iat: 1_700_000_000,
      jti: 'jti-fijo'
    })
    const [h, p, s] = proof.split('.')
    expect(h && p && s).toBeTruthy()

    const header = decodeJson(h!)
    expect(header).toMatchObject({ typ: 'dpop+jwt', alg: 'ES256' })
    expect(header.jwk).toEqual(await publicJwk(pair.publicKey))

    expect(decodeJson(p!)).toEqual({
      htm: 'POST',
      htu: 'http://localhost:8100/api/v1/auth/login',
      iat: 1_700_000_000,
      jti: 'jti-fijo'
    })

    const signature = base64UrlDecode(s!)
    expect(signature.byteLength).toBe(64) // r||s (IEEE P1363), no DER
    const publicKey = await crypto.subtle.importKey(
      'jwk',
      header.jwk as JsonWebKey,
      { name: 'ECDSA', namedCurve: 'P-256' },
      false,
      ['verify']
    )
    const ok = await crypto.subtle.verify(
      { name: 'ECDSA', hash: 'SHA-256' },
      publicKey,
      signature,
      new TextEncoder().encode(`${h}.${p}`)
    )
    expect(ok).toBe(true)
  })

  it('usa la hora actual en segundos y un jti aleatorio distinto en cada prueba', async () => {
    const pair = await generateDpopKeyPair()
    const before = Math.floor(Date.now() / 1000)
    const a = decodeJson((await createDpopProof(pair, { htm: 'GET', htu: 'http://x/a' })).split('.')[1]!)
    const b = decodeJson((await createDpopProof(pair, { htm: 'GET', htu: 'http://x/a' })).split('.')[1]!)
    expect(a.iat).toBeGreaterThanOrEqual(before)
    expect(Number.isInteger(a.iat)).toBe(true)
    expect(typeof a.jti).toBe('string')
    expect((a.jti as string).length).toBeGreaterThanOrEqual(22)
    expect(a.jti).not.toBe(b.jti)
  })

  it('quita query y fragmento del htu', async () => {
    const pair = await generateDpopKeyPair()
    const proof = await createDpopProof(pair, { htm: 'GET', htu: 'http://x/api/v1/users?q=a#top' })
    expect(decodeJson(proof.split('.')[1]!).htu).toBe('http://x/api/v1/users')
  })
})

describe('dpopHtu', () => {
  it('es la URL pública + el path de la petición, sin query', () => {
    expect(dpopHtu('http://localhost:8100', 'http://localhost:8100/api/v1/auth/me?x=1')).toBe(
      'http://localhost:8100/api/v1/auth/me'
    )
  })

  it('respeta la URL pública aunque la petición vaya por otro origen (proxy)', () => {
    expect(dpopHtu('https://leo.example.com/', 'http://127.0.0.1:8100/api/v1/users')).toBe(
      'https://leo.example.com/api/v1/users'
    )
  })

  it('sin URL pública usa el origen de la propia petición', () => {
    expect(dpopHtu('', 'http://localhost:8100/api/v1/users#x')).toBe('http://localhost:8100/api/v1/users')
  })
})

describe('createDpopSigner', () => {
  it('genera la llave una sola vez y la reutiliza desde el almacén', async () => {
    const store = memoryDpopKeyStore()
    const signer = await createDpopSigner(store)
    const jkt1 = await signer.jkt()
    const again = await createDpopSigner(store)
    expect(await again.jkt()).toBe(jkt1)
    expect(jkt1).toMatch(/^[A-Za-z0-9_-]{43}$/)
  })

  it('dos pestañas que generan llave a la vez terminan con la misma (claim atómico)', async () => {
    const store = memoryDpopKeyStore()
    const [a, b] = await Promise.all([createDpopSigner(store), createDpopSigner(store)])
    const [jktA, jktB] = await Promise.all([a.jkt(), b.jkt()])
    expect(jktA).toBe(jktB)
  })

  it('el jkt corresponde a la llave pública de las pruebas firmadas', async () => {
    const signer = await createDpopSigner(memoryDpopKeyStore())
    const proof = await signer.proof('GET', 'http://x/api/v1/auth/me')
    const header = decodeJson(proof.split('.')[0]!)
    expect(await jwkThumbprint(header.jwk as JsonWebKey)).toBe(await signer.jkt())
  })

  it('reset() descarta la llave y genera otra (nuevo jkt)', async () => {
    const store = memoryDpopKeyStore()
    const signer = await createDpopSigner(store)
    const before = await signer.jkt()
    await signer.reset()
    expect(await signer.jkt()).not.toBe(before)
    expect((await store.load())?.privateKey.extractable).toBe(false)
  })
})
