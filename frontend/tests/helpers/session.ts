// `signInWith` vive en leo-client; se re-exporta para que las pruebas lo sigan importando de aquí.
export { signInWith } from '#leo-client/testing/session'

export const ALL_APPLICATIONS_TAGS = [
  'leo.applications.view',
  'leo.applications.create',
  'leo.applications.edit',
  'leo.applications.deactivate',
  'leo.applications.rotate-secret',
  'leo.applications.grant-service-access'
]

export const ALL_ROLES_TAGS = [
  'leo.roles.view',
  'leo.roles.create',
  'leo.roles.edit',
  'leo.roles.deactivate'
]

export const ALL_USERS_TAGS = [
  'leo.users.view',
  'leo.users.create',
  'leo.users.edit',
  'leo.users.deactivate',
  'leo.users.unlock',
  'leo.users.reset-password',
  'leo.users.assign-roles'
]

export const ALL_AUDIT_TAGS = [
  'leo.audit.view',
  'leo.audit.export'
]

export const ALL_SESSIONS_TAGS = [
  'leo.auth.view',
  'leo.auth.revoke'
]
