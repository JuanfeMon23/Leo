import { normalizeSearchTerm } from '#andromeda/utils/search'

export const APPLICATIONS_PAGE_SIZE = 20

export interface ApplicationsQueryInput {
  search: string
  page: number
  /** `undefined` = todas. */
  active: boolean | undefined
}

/** Query de `GET /applications`: solo envía `q` y `active` cuando tienen valor. */
export function buildApplicationsQuery(input: ApplicationsQueryInput) {
  const q = normalizeSearchTerm(input.search)
  return {
    page: input.page,
    page_size: APPLICATIONS_PAGE_SIZE,
    ...(q ? { q } : {}),
    ...(input.active !== undefined ? { active: input.active } : {})
  }
}
