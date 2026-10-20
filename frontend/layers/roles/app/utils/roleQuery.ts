import { normalizeSearchTerm } from '#andromeda/utils/search'

export const ROLES_PAGE_SIZE = 20

export interface RolesQueryInput {
  search: string
  page: number
  /** `undefined` = todos. */
  active: boolean | undefined
  /** `''` = todas las aplicaciones. */
  applicationId: string
}

/** Query de `GET /roles`: solo envía `q`, `active` y `application_id` cuando tienen valor. */
export function buildRolesQuery(input: RolesQueryInput) {
  const q = normalizeSearchTerm(input.search)
  return {
    page: input.page,
    page_size: ROLES_PAGE_SIZE,
    ...(q ? { q } : {}),
    ...(input.active !== undefined ? { active: input.active } : {}),
    ...(input.applicationId ? { application_id: input.applicationId } : {})
  }
}
