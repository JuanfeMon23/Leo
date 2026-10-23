import type { SettingHistoryPage, SettingItem, SettingsListResponse, SettingUpdateBody } from '#andromeda/types/settings'

/**
 * Llamadas a `/settings`: única puerta del módulo a la API. Lanzan
 * `LeoApiError` (con `code` y `details`, que `useSettingsAdmin` interpreta).
 */
export function useSettingsApi() {
  const api = useLeoApi()
  const key = (k: string) => `/settings/${encodeURIComponent(k)}`

  return {
    list: () => api<SettingsListResponse>('/settings'),
    history: (k: string, page: number) => api<SettingHistoryPage>(`${key(k)}/history`, { query: { page } }),
    update: (k: string, body: SettingUpdateBody) => api<SettingItem>(key(k), { method: 'PUT', body })
  }
}
