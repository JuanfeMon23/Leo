// `signInWith` vive en leo-client; se re-exporta para que las pruebas lo sigan importando de aquí.
export { signInWith } from '#leo-client/testing/session'

import { assignableTagsOf } from '../../app/utils/permissionContract'

// Tags asignables de cada módulo, derivados del contrato generado por el backend.
export const ALL_APPLICATIONS_TAGS = assignableTagsOf('applications')
export const ALL_ROLES_TAGS = assignableTagsOf('roles')
export const ALL_USERS_TAGS = assignableTagsOf('users')
export const ALL_AUDIT_TAGS = assignableTagsOf('audit')
export const ALL_SESSIONS_TAGS = assignableTagsOf('auth')
export const ALL_SETTINGS_TAGS = assignableTagsOf('settings')
