import { readdirSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { assignableTagsOf, CONTRACT_ACTIONS, PERMISSION_CONTRACT, PERMISSION_NAMES } from './permissionContract'
import { isEventAction } from './actionEvents'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..')
const TAG_PATTERN = /leo\.[a-z0-9-]+\.[a-z0-9-]+/g

/** Cadenas con forma de tag que NO son permisos (claves de almacenamiento, configuración). */
const NOT_PERMISSION_TAGS = new Set(['leo.sidebar.collapsed', 'leo.transport.login'])

/**
 * Tags asignables del backend que el frontend no referencia a propósito: son permisos de
 * servicio (los usa otra aplicación con credencial de servicio, no una pantalla de Leo).
 */
const TAGS_WITHOUT_SCREEN = new Set([
  'leo.users.provision-patient',
  'leo.users.delegated-self-manage'
])

function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    if (entry.name === 'node_modules' || entry.name === 'generated' || entry.name.startsWith('.')) return []
    const path = join(dir, entry.name)
    if (entry.isDirectory()) return sourceFiles(path)
    return /\.(ts|vue)$/.test(entry.name) && !entry.name.endsWith('.test.ts') ? [path] : []
  })
}

const usedTags = new Set(
  ['app', 'layers']
    .flatMap(dir => sourceFiles(join(ROOT, dir)))
    .flatMap(file => readFileSync(file, 'utf8').match(TAG_PATTERN) ?? [])
    .filter(tag => !NOT_PERMISSION_TAGS.has(tag))
)
const contractTags = new Set(CONTRACT_ACTIONS.map(a => a.tag))

describe('contrato de permisos (backend) vs frontend', () => {
  it('todo tag usado en el código fuente existe en el contrato', () => {
    expect([...usedTags].filter(tag => !contractTags.has(tag)).sort()).toEqual([])
  })

  it('todo tag asignable del contrato está referenciado o justificado en TAGS_WITHOUT_SCREEN', () => {
    const missing = CONTRACT_ACTIONS.filter(a => a.assignable && !usedTags.has(a.tag) && !TAGS_WITHOUT_SCREEN.has(a.tag))
    expect(missing.map(a => a.tag)).toEqual([])
  })

  it('TAGS_WITHOUT_SCREEN solo lista tags asignables que de verdad no se usan', () => {
    for (const tag of TAGS_WITHOUT_SCREEN) {
      expect(contractTags.has(tag), `${tag} no existe en el contrato`).toBe(true)
      expect(usedTags.has(tag), `${tag} ya se usa: quítalo de TAGS_WITHOUT_SCREEN`).toBe(false)
    }
  })
})

describe('derivados del contrato', () => {
  it('los tags son únicos y pertenecen a la app del contrato', () => {
    expect(contractTags.size).toBe(CONTRACT_ACTIONS.length)
    for (const a of CONTRACT_ACTIONS) expect(a.tag.startsWith(`${PERMISSION_CONTRACT.app}.`)).toBe(true)
  })

  it('assignable coincide con que la descripción no sea de evento', () => {
    for (const a of CONTRACT_ACTIONS) expect(a.assignable).toBe(!isEventAction(a.description))
  })

  it('PERMISSION_NAMES solo tiene acciones asignables', () => {
    expect(Object.keys(PERMISSION_NAMES).sort()).toEqual(CONTRACT_ACTIONS.filter(a => a.assignable).map(a => a.tag).sort())
    expect(PERMISSION_NAMES['leo.settings.edit-security']).toBeTruthy()
  })

  it('assignableTagsOf devuelve los de un módulo y [] si no existe', () => {
    expect(assignableTagsOf('audit')).toEqual(['leo.audit.view', 'leo.audit.export'])
    expect(assignableTagsOf('auth')).not.toContain('leo.auth.login')
    expect(assignableTagsOf('nope')).toEqual([])
  })
})
