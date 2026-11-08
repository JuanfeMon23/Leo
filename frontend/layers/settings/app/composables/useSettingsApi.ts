import type { SettingHistoryPage, SettingItem, SettingsListResponse, SettingUpdateBody } from '#andromeda/types/settings'

/**
 * Llamadas a `/settings`: única puerta del módulo a la API. Lanzan
 * `LeoApiError` (con `code` y `details`, que `useSettingsAdmin` interpreta).
 */
export function useSettingsApi() {
  const api = useLeoApi()
  const key = (settingKey: string) => `/settings/${encodeURIComponent(settingKey)}`

  return {
    list: () => api<SettingsListResponse>('/settings'),
    history: (settingKey: string, page: number) => api<SettingHistoryPage>(`${key(settingKey)}/history`, { query: { page } }),
    update: (settingKey: string, body: SettingUpdateBody) => api<SettingItem>(key(settingKey), { method: 'PUT', body })
  }
}
