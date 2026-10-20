import { describe, expect, it } from 'vitest'
import { LeoApiError } from '#leo-client/lib/errors'
import type { ApplicationRead, ApplicationsServiceGrant } from '../types/applications'
import {
  applicationsGrantSummary,
  applicationsGrantableTargets,
  applicationsGroupServiceGrants,
  applicationsServiceAccessErrorMessage
} from './serviceAccess'

function grant(id: string, appSlug: string, appName: string, roleName: string): ApplicationsServiceGrant {
  return {
    id,
    role: { id: `r-${id}`, slug: roleName.toLowerCase(), name: roleName, is_active: true },
    application: { id: `a-${appSlug}`, slug: appSlug, name: appName },
    permissions: [],
    created_at: ''
  }
}

describe('applicationsGroupServiceGrants', () => {
  it('sin concesiones: sin grupos', () => {
    expect(applicationsGroupServiceGrants([])).toEqual([])
  })

  it('agrupa por aplicación destino, ordenadas por nombre, y los roles por nombre', () => {
    const groups = applicationsGroupServiceGrants([
      grant('1', 'vladimir', 'Vladimir', 'Lector'),
      grant('2', 'acuarius', 'Acuarius', 'Operador'),
      grant('3', 'vladimir', 'Vladimir', 'Analista')
    ])
    expect(groups.map(g => g.application.name)).toEqual(['Acuarius', 'Vladimir'])
    expect(groups[1]!.grants.map(g => g.role.name)).toEqual(['Analista', 'Lector'])
  })

  it('no muta la entrada', () => {
    const input = [grant('1', 'b', 'B', 'X'), grant('2', 'a', 'A', 'Y')]
    applicationsGroupServiceGrants(input)
    expect(input.map(g => g.id)).toEqual(['1', '2'])
  })
})

describe('applicationsGrantableTargets', () => {
  const app = (id: string, slug: string, name: string): ApplicationRead => ({
    id, slug, name, description: null, base_url: '', redirect_uris: [], client_id: slug, is_active: true, created_at: '', updated_at: ''
  })

  it('excluye la app actual y la app leo', () => {
    const apps = [app('1', 'incubus', 'Incubus'), app('2', 'leo', 'Leo'), app('3', 'vladimir', 'Vladimir')]
    expect(applicationsGrantableTargets(apps, '1').map(a => a.slug)).toEqual(['vladimir'])
  })
})

describe('applicationsGrantSummary', () => {
  it('dice qué app podrá consultar a cuál', () => {
    expect(applicationsGrantSummary('Incubus', 'Vladimir')).toBe('Incubus podrá consultar Vladimir con los permisos de estos roles.')
  })
})

describe('applicationsServiceAccessErrorMessage', () => {
  const e = (code: string) => new LeoApiError(422, code, 'texto del backend')

  it.each([
    ['same_application', 'otra aplicación'],
    ['role_inactive', 'inactivo'],
    ['leo_app_not_grantable', 'Leo'],
    ['invalid_reference', 'ya no existen']
  ])('%s: texto propio legible', (code, fragment) => {
    expect(applicationsServiceAccessErrorMessage(e(code))).toContain(fragment)
  })

  it('403: mensaje del backend', () => {
    expect(applicationsServiceAccessErrorMessage(new LeoApiError(403, 'forbidden', 'No tienes acceso.'))).toBe('No tienes acceso.')
  })

  it('red o 500: legible, nunca crudo', () => {
    expect(applicationsServiceAccessErrorMessage(new TypeError('Failed to fetch'))).not.toMatch(/fetch/i)
    expect(applicationsServiceAccessErrorMessage(new LeoApiError(500, 'internal_error', 'Traceback'))).not.toMatch(/traceback/i)
  })
})
