<script setup lang="ts">
import type { UiSidebarItem } from '#andromeda/components/ui/UiSidebar.vue'

// Los módulos del admin agregan aquí su entrada, visible solo con el tag `view` del módulo.
const canViewApplications = useCan('leo.applications.view')
const canViewUsers = useCan('leo.users.view')
const canViewRoles = useCan('leo.roles.view')
const canViewAudit = useCan('leo.audit.view')
const canViewSessions = useCan('leo.auth.view')
const canViewSettings = useCan('leo.settings.view')
const menu = computed<UiSidebarItem[]>(() => [
  ...(canViewApplications.value
    ? [{
        label: 'Aplicaciones',
        to: '/applications',
        // Cuadrícula de 4 recuadros (trazo, 24×24).
        icon: 'M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z'
      }]
    : []),
  ...(canViewUsers.value
    ? [{
        label: 'Usuarios',
        to: '/users',
        // Persona: cabeza y hombros (trazo, 24×24).
        icon: 'M12 12a4 4 0 100-8 4 4 0 000 8zM4 20c0-4 3.5-6 8-6s8 2 8 6'
      }]
    : []),
  ...(canViewRoles.value
    ? [{
        label: 'Roles',
        to: '/roles',
        // Escudo (trazo, 24×24).
        icon: 'M12 3l7 3v5c0 5-3 8-7 10-4-2-7-5-7-10V6z'
      }]
    : []),
  ...(canViewSessions.value
    ? [{
        label: 'Sesiones',
        to: '/sessions',
        // Monitor con base (trazo, 24×24).
        icon: 'M4 5h16v11H4zM9 20h6M12 16v4'
      }]
    : []),
  ...(canViewAudit.value
    ? [{
        label: 'Auditoría',
        to: '/audit',
        // Documento con líneas (trazo, 24×24).
        icon: 'M7 3h7l4 4v14H7zM14 3v4h4M10 12h5M10 16h5'
      }]
    : []),
  ...(canViewSettings.value
    ? [{
        label: 'Ajustes',
        to: '/ajustes',
        // Controles deslizantes (trazo, 24×24).
        icon: 'M4 7h8M16 7h4M4 17h4M12 17h8M14 4v6M10 14v6'
      }]
    : [])
])
</script>

<template>
  <LeoAppShell :items="menu" brand="Leo" storage-key="leo.sidebar.collapsed">
    <slot />
  </LeoAppShell>
</template>
