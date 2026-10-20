import { normalizeSearchTerm } from '#andromeda/utils/search'

export const USERS_PAGE_SIZE = 20

export interface UsersQueryInput {
  search: string
  page: number
  /** `undefined` = todos. */
  active: boolean | undefined
}

/** Query de `GET /users`: solo envía `q` y `active` cuando tienen valor. */
export function buildUsersQuery(input: UsersQueryInput) {
  const q = normalizeSearchTerm(input.search)
  return {
    page: input.page,
    page_size: USERS_PAGE_SIZE,
    ...(q ? { q } : {}),
    ...(input.active !== undefined ? { active: input.active } : {})
  }
}
