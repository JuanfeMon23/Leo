import type { LeoTagMode } from '../lib/permissions'

/** Metadatos de página de leo-client: `definePageMeta({ leo: { tag: 'app.mod.verbo' } })`. */
export interface LeoPageMeta {
  /** Página sin sesión (login, páginas públicas). Por defecto toda página exige sesión. */
  public?: boolean
  /** Tag(s) de acción exigidos; sin ellos se muestra la página 403. */
  tag?: string | string[]
  /** Con varios tags: `all` (por defecto) o `any`. */
  mode?: LeoTagMode
}

declare module '#app' {
  interface PageMeta {
    leo?: LeoPageMeta
  }
}

export {}
