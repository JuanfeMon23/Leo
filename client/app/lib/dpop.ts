/**
 * DPoP (RFC 9449) en el navegador con WebCrypto.
 *
 * - Llave ECDSA P-256 generada con `extractable: false`: la privada nunca se
 *   puede exportar ni leer; solo firmar. Se guarda como `CryptoKey` (no como
 *   bytes) en IndexedDB del origen.
 * - Prueba = JWS compacto ES256: header `{typ:"dpop+jwt", alg:"ES256", jwk}`,
 *   payload `{htm, htu, iat, jti}`; la firma es `r||s` (64 bytes), que es
 *   justo lo que entrega `crypto.subtle.sign` para ECDSA.
 * - `jkt` = thumbprint RFC 7638 de la llave pública.
 *
 * Sin dependencias de Vue/Nuxt: se prueba en entorno node.
 */

const EC_ALGORITHM = { name: 'ECDSA', namedCurve: 'P-256' } as const
const SIGN_ALGORITHM = { name: 'ECDSA', hash: 'SHA-256' } as const

export interface DpopPublicJwk {
  kty: 'EC'
  crv: 'P-256'
  x: string
  y: string
}

// ── base64url ──────────────────────────────────────────────────────────

export function base64UrlEncode(data: ArrayBuffer | Uint8Array | string): string {
  const bytes = typeof data === 'string'
    ? new TextEncoder().encode(data)
    : data instanceof Uint8Array ? data : new Uint8Array(data)
  let binary = ''
  for (const byte of bytes) binary += String.fromCharCode(byte)
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

export function base64UrlDecode(value: string): Uint8Array<ArrayBuffer> {
  const base64 = value.replace(/-/g, '+').replace(/_/g, '/')
  const binary = atob(base64 + '='.repeat((4 - (base64.length % 4)) % 4))
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
  return bytes
}

// ── llave y thumbprint ─────────────────────────────────────────────────

/** Miembros obligatorios por tipo de llave (RFC 7638 §3.2), en orden lexicográfico. */
const REQUIRED_MEMBERS: Record<string, readonly string[]> = {
  EC: ['crv', 'kty', 'x', 'y'],
  RSA: ['e', 'kty', 'n'],
  OKP: ['crv', 'kty', 'x']
}

/** Thumbprint RFC 7638 (SHA-256, base64url) de una llave pública JWK. */
export async function jwkThumbprint(jwk: JsonWebKey): Promise<string> {
  const members = jwk.kty ? REQUIRED_MEMBERS[jwk.kty] : undefined
  if (!members) throw new Error(`Tipo de llave no soportado: ${jwk.kty}`)
  const record = jwk as Record<string, unknown>
  // JSON sin espacios, miembros en orden lexicográfico (ya ordenados arriba).
  const canonical = `{${members.map(m => `"${m}":${JSON.stringify(record[m])}`).join(',')}}`
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(canonical))
  return base64UrlEncode(digest)
}

/** Par ECDSA P-256 con la privada no exportable (solo `sign`). */
export async function generateDpopKeyPair(): Promise<CryptoKeyPair> {
  return crypto.subtle.generateKey(EC_ALGORITHM, false, ['sign', 'verify'])
}

/** JWK público con SOLO `kty`, `crv`, `x`, `y` (lo que va en el header). */
export async function publicJwk(publicKey: CryptoKey): Promise<DpopPublicJwk> {
  const jwk = await crypto.subtle.exportKey('jwk', publicKey)
  return { kty: 'EC', crv: 'P-256', x: jwk.x as string, y: jwk.y as string }
}

// ── prueba ─────────────────────────────────────────────────────────────

/** URL sin query ni fragmento (así compara el backend el `htu`). */
export function stripQueryAndFragment(url: string): string {
  const cut = url.search(/[?#]/)
  return cut === -1 ? url : url.slice(0, cut)
}

/**
 * `htu` esperado por el backend: su URL pública + el path de la petición.
 * Sin URL pública, el origen de la propia petición.
 */
export function dpopHtu(publicUrl: string, requestUrl: string): string {
  const url = new URL(requestUrl)
  const base = publicUrl ? publicUrl.replace(/\/+$/, '') : url.origin
  return base + url.pathname
}

export interface DpopProofClaims {
  htm: string
  htu: string
  /** Segundos epoch; por defecto, ahora. */
  iat?: number
  /** Identificador único; por defecto, 16 bytes aleatorios en base64url. */
  jti?: string
}

function randomJti(): string {
  return base64UrlEncode(crypto.getRandomValues(new Uint8Array(16)))
}

export async function createDpopProof(keyPair: CryptoKeyPair, claims: DpopProofClaims): Promise<string> {
  const header = { typ: 'dpop+jwt', alg: 'ES256', jwk: await publicJwk(keyPair.publicKey) }
  const payload = {
    htm: claims.htm.toUpperCase(),
    htu: stripQueryAndFragment(claims.htu),
    iat: claims.iat ?? Math.floor(Date.now() / 1000),
    jti: claims.jti ?? randomJti()
  }
  const signingInput = `${base64UrlEncode(JSON.stringify(header))}.${base64UrlEncode(JSON.stringify(payload))}`
  const signature = await crypto.subtle.sign(SIGN_ALGORITHM, keyPair.privateKey, new TextEncoder().encode(signingInput))
  return `${signingInput}.${base64UrlEncode(signature)}`
}

// ── almacén y firmante ─────────────────────────────────────────────────

/** Dónde vive el par de llaves (IndexedDB en el navegador; memoria en tests). */
export interface DpopKeyStore {
  load(): Promise<CryptoKeyPair | null>
  /**
   * Guarda `pair` solo si no hay uno (atómico) y devuelve el que quedó: si
   * dos pestañas generan llave a la vez, ambas terminan usando la misma.
   */
  claim(pair: CryptoKeyPair): Promise<CryptoKeyPair>
  clear(): Promise<void>
}

export function memoryDpopKeyStore(): DpopKeyStore {
  let current: CryptoKeyPair | null = null
  return {
    load: async () => current,
    claim: async (pair) => (current ??= pair),
    clear: async () => { current = null }
  }
}

function idbRequest<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

/**
 * Almacén en IndexedDB del origen. Guarda el `CryptoKeyPair` tal cual
 * (clonado estructurado): la privada sigue sin poder exportarse.
 */
export function indexedDbDpopKeyStore(dbName = 'leo-client', storeName = 'keys', key = 'dpop'): DpopKeyStore {
  let dbPromise: Promise<IDBDatabase> | null = null
  const open = () => {
    dbPromise ??= new Promise<IDBDatabase>((resolve, reject) => {
      const request = indexedDB.open(dbName, 1)
      request.onupgradeneeded = () => request.result.createObjectStore(storeName)
      request.onsuccess = () => resolve(request.result)
      request.onerror = () => reject(request.error)
    })
    return dbPromise
  }
  const store = async (mode: IDBTransactionMode) =>
    (await open()).transaction(storeName, mode).objectStore(storeName)

  return {
    async load() {
      const value = await idbRequest((await store('readonly')).get(key))
      return (value as CryptoKeyPair | undefined) ?? null
    },
    async claim(pair) {
      // get + put en la MISMA transacción readwrite: IndexedDB las serializa.
      const objectStore = await store('readwrite')
      const existing = await idbRequest(objectStore.get(key))
      if (existing) return existing as CryptoKeyPair
      await idbRequest(objectStore.put(pair, key))
      return pair
    },
    async clear() {
      await idbRequest((await store('readwrite')).delete(key))
    }
  }
}

export interface DpopSigner {
  /** Thumbprint de la llave actual (`dpop_jkt` de /authorize). */
  jkt(): Promise<string>
  /** Prueba DPoP para una petición (`htu` ya calculado). */
  proof(htm: string, htu: string): Promise<string>
  /** Descarta la llave (p. ej. tras cerrar sesión) y genera otra. */
  reset(): Promise<void>
}

/** Carga el par del almacén o lo genera (una sola vez) y lo guarda. */
export async function createDpopSigner(store: DpopKeyStore): Promise<DpopSigner> {
  let pair: Promise<CryptoKeyPair> | null = null
  let thumbprint: Promise<string> | null = null

  const keyPair = () => {
    pair ??= (async () => {
      const stored = await store.load()
      if (stored) return stored
      return store.claim(await generateDpopKeyPair())
    })()
    return pair
  }

  return {
    jkt() {
      thumbprint ??= keyPair().then(async p => jwkThumbprint(await publicJwk(p.publicKey)))
      return thumbprint
    },
    async proof(htm, htu) {
      return createDpopProof(await keyPair(), { htm, htu })
    },
    async reset() {
      await store.clear()
      pair = null
      thumbprint = null
    }
  }
}
