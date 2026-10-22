<script setup lang="ts">
import type { UiSidebarItem } from '#andromeda/components/ui/UiSidebar.vue'

/**
 * Layout de las apps: `UiAppShell` de Andromeda (menú lateral) con la barra
 * superior `LeoTopBar` como hijo directo de la columna de contenido (contrato
 * en `client/nuxt.config.ts`) y la hamburguesa del menú en su slot `#start`.
 * `items` ya llega filtrado por permisos (la app decide con `useCan`).
 * Slot `#sidebar-footer="{ collapsed }"` se reenvía; el contenido va en `#default`.
 */
withDefaults(defineProps<{
  items: UiSidebarItem[]
  brand?: string
  brandTo?: string
  storageKey?: string
  contentWidth?: 'contained' | 'full'
}>(), { brand: '', brandTo: undefined, storageKey: undefined, contentWidth: 'contained' })
</script>

<template>
  <UiAppShell :items="items" :brand="brand" :brand-to="brandTo" :storage-key="storageKey" :content-width="contentWidth">
    <template #topbar="{ openMenu }">
      <LeoTopBar>
        <template #start>
          <UiButton variant="ghost" icon-only class="lg:hidden" aria-label="Abrir menú" data-testid="leo-menu-button" @click="openMenu">
            <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
              <path d="M4 7h16M4 12h16M4 17h16" />
            </svg>
          </UiButton>
        </template>
      </LeoTopBar>
    </template>
    <template v-if="$slots['sidebar-footer']" #sidebar-footer="slotProps">
      <slot name="sidebar-footer" v-bind="slotProps" />
    </template>
    <slot />
  </UiAppShell>
</template>
