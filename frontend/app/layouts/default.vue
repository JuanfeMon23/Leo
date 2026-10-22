<script setup lang="ts">
import type { UiSidebarItem } from '#andromeda/components/ui/UiSidebar.vue'

// Los módulos del admin agregan aquí su entrada, visible solo con el tag `view` del módulo.
const canViewApplications = useCan('leo.applications.view')
const canViewUsers = useCan('leo.users.view')
const canViewRoles = useCan('leo.roles.view')
const canViewAudit = useCan('leo.audit.view')
const canViewSessions = useCan('leo.auth.view')
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
    : [])
])
const collapsedPad = ref(false)
</script>

<template>
  <div class="min-h-screen bg-background text-text">
    <UiSidebar v-model:collapsed="collapsedPad" :items="menu" brand="Leo" storage-key="leo.sidebar.collapsed" />

    <!-- El contenido deja el espacio de la barra lateral en pantallas grandes -->
    <div class="transition-all duration-200 lg:pl-64" :class="{ 'lg:!pl-[4.5rem]': collapsedPad }">
      <!-- Contrato de leo-client (client/nuxt.config.ts): LeoTopBar trae su propio <header>; sin envoltorio ni clases. -->
      <LeoTopBar />
      <main class="mx-auto max-w-6xl px-4 py-6">
        <slot />
      </main>
    </div>
  </div>
</template>
