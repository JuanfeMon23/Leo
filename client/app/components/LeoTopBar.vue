<script setup lang="ts">
import { buildProfileUrl, userDisplayName, userInitials } from '../lib/userMenu'
import type { LeoTransportKind } from '../lib/transport'

/**
 * Barra superior de Leo para todas las apps: app actual, selector de las apps
 * a las que el usuario tiene acceso, usuario y cerrar sesión. Ocupa la franja
 * superior del área de contenido (la barra lateral es de cada app); el slot
 * `#start` deja poner algo a la izquierda (p. ej. migas de pan).
 * A la derecha, menú de usuario (iniciales + nombre): datos de solo lectura,
 * "Mi perfil" (en Leo, `/profile`; en apps `bff`, `<leoUrl>/profile?return=…`)
 * y "Cerrar sesión".
 * Incluye el aviso de inactividad (`LeoIdleWarning`).
 */
const props = withDefaults(defineProps<{
  /** Nombre a mostrar; por defecto el de la app `appSlug` en Leo. */
  appName?: string
}>(), { appName: undefined })

const config = useRuntimeConfig().public.leo
const session = useLeoSession()

const currentSlug = computed(() => config.appSlug)
const currentName = computed(() =>
  props.appName
  ?? session.applications.value.find(app => app.slug === currentSlug.value)?.name
  ?? (config.appName || currentSlug.value)
)
const displayName = computed(() => userDisplayName(session.user.value))
const initials = computed(() => userInitials(displayName.value))

const menuOpen = ref(false)
const menuRef = ref<HTMLElement | null>(null)
const menuId = useId()
const userOpen = ref(false)
const userRef = ref<HTMLElement | null>(null)
const userButtonRef = ref<HTMLButtonElement | null>(null)
const userMenuId = useId()
const loggingOut = ref(false)
const currentUrl = ref('')

const isDirect = computed(() => config.transport === 'leo-direct')
const profileUrl = computed(() => buildProfileUrl(
  { transport: config.transport as LeoTransportKind, leoUrl: config.leoUrl },
  currentUrl.value
))

function menuItems(): HTMLElement[] {
  return Array.from(userRef.value?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? [])
}
async function toggleUserMenu() {
  userOpen.value = !userOpen.value
  if (!userOpen.value) return
  menuOpen.value = false
  // Solo la URL de la app actual (sin fragmento): es lo único que viaja en `return`.
  currentUrl.value = globalThis.location ? globalThis.location.href.split('#')[0]! : ''
  await nextTick()
  menuItems()[0]?.focus()
}
function closeUserMenu(restoreFocus = false) {
  if (!userOpen.value) return
  userOpen.value = false
  if (restoreFocus) userButtonRef.value?.focus()
}
function onUserMenuKeydown(event: KeyboardEvent) {
  const items = menuItems()
  const index = items.indexOf(document.activeElement as HTMLElement)
  const focusAt = (i: number) => { event.preventDefault(); items[(i + items.length) % items.length]?.focus() }
  if (event.key === 'ArrowDown') focusAt(index + 1)
  else if (event.key === 'ArrowUp') focusAt(index - 1)
  else if (event.key === 'Home') focusAt(0)
  else if (event.key === 'End') focusAt(items.length - 1)
  else if (event.key === 'Tab') closeUserMenu()
}

function onDocumentClick(event: MouseEvent) {
  const target = event.target as Node
  if (menuOpen.value && menuRef.value && !menuRef.value.contains(target)) menuOpen.value = false
  if (userOpen.value && userRef.value && !userRef.value.contains(target)) userOpen.value = false
}
function onKeydown(event: KeyboardEvent) {
  if (event.key !== 'Escape') return
  menuOpen.value = false
  closeUserMenu(true)
}
onMounted(() => {
  document.addEventListener('click', onDocumentClick)
  document.addEventListener('keydown', onKeydown)
})
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocumentClick)
  document.removeEventListener('keydown', onKeydown)
})

async function logout() {
  loggingOut.value = true
  try {
    await session.logout()
  } finally {
    loggingOut.value = false
    userOpen.value = false
  }
}
</script>

<template>
  <header class="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-border bg-surface px-4">
    <slot name="start" />
    <span class="truncate font-semibold tracking-tight text-text" data-testid="leo-current-app">{{ currentName }}</span>

    <div v-if="session.isAuthenticated.value" class="ml-auto flex items-center gap-2">
      <div v-if="session.applications.value.length" ref="menuRef" class="relative">
        <button
          type="button"
          class="flex h-9 items-center gap-1.5 rounded-md px-3 text-sm font-medium text-default-700 hover:bg-default-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-500"
          :aria-expanded="menuOpen"
          :aria-controls="menuId"
          @click="menuOpen = !menuOpen"
        >
          <svg viewBox="0 0 24 24" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
            <path d="M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z" />
          </svg>
          Aplicaciones
        </button>
        <ul
          v-if="menuOpen"
          :id="menuId"
          class="absolute right-0 z-30 mt-1 w-64 overflow-hidden rounded-lg border border-border bg-surface py-1 shadow-md"
          aria-label="Aplicaciones a las que tienes acceso"
        >
          <li v-for="app in session.applications.value" :key="app.slug">
            <a
              :href="app.base_url"
              class="flex items-center justify-between gap-2 px-3 py-2 text-sm hover:bg-default-100"
              :class="app.slug === currentSlug ? 'font-semibold text-primary-700' : 'text-default-700'"
              :aria-current="app.slug === currentSlug ? 'page' : undefined"
            >
              <span class="truncate">{{ app.name }}</span>
              <span v-if="app.slug === currentSlug" class="text-xs text-text-muted">Actual</span>
            </a>
          </li>
        </ul>
      </div>

      <div ref="userRef" class="relative">
        <button
          ref="userButtonRef"
          type="button"
          class="flex h-9 items-center gap-2 rounded-full pl-1 pr-1 text-sm font-medium text-default-700 hover:bg-default-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-500 sm:pr-3"
          aria-haspopup="menu"
          :aria-expanded="userOpen"
          :aria-controls="userMenuId"
          :aria-label="displayName ? `Menú de usuario: ${displayName}` : 'Menú de usuario'"
          data-testid="leo-user-button"
          @click="toggleUserMenu"
        >
          <span class="flex h-7 w-7 items-center justify-center rounded-full bg-primary-600 text-xs font-semibold text-white" aria-hidden="true" data-testid="leo-user-initials">{{ initials }}</span>
          <span class="hidden max-w-40 truncate sm:inline" data-testid="leo-user-name">{{ displayName }}</span>
        </button>
        <div
          v-if="userOpen"
          :id="userMenuId"
          role="menu"
          aria-label="Menú de usuario"
          class="absolute right-0 z-30 mt-1 w-64 overflow-hidden rounded-lg border border-border bg-surface py-1 shadow-md"
          @keydown="onUserMenuKeydown"
        >
          <div v-if="displayName" role="presentation" class="border-b border-border px-3 py-2 leading-tight" data-testid="leo-user-card">
            <p class="truncate text-sm font-semibold text-text">{{ displayName }}</p>
            <p v-if="session.user.value?.email" class="truncate text-xs text-text-muted" data-testid="leo-user-email">{{ session.user.value.email }}</p>
            <p v-if="session.user.value?.username" class="truncate text-xs text-text-muted" data-testid="leo-user-username">@{{ session.user.value.username }}</p>
          </div>
          <NuxtLink
            v-if="isDirect"
            to="/profile"
            role="menuitem"
            class="block px-3 py-2 text-sm text-default-700 hover:bg-default-100 focus-visible:bg-default-100 focus-visible:outline-none"
            @click="userOpen = false"
          >
            Mi perfil
          </NuxtLink>
          <a
            v-else-if="profileUrl"
            :href="profileUrl"
            role="menuitem"
            class="block px-3 py-2 text-sm text-default-700 hover:bg-default-100 focus-visible:bg-default-100 focus-visible:outline-none"
          >
            Mi perfil
          </a>
          <button
            type="button"
            role="menuitem"
            class="block w-full px-3 py-2 text-left text-sm text-default-700 hover:bg-default-100 focus-visible:bg-default-100 focus-visible:outline-none disabled:opacity-60"
            :disabled="loggingOut"
            @click="logout"
          >
            {{ loggingOut ? 'Cerrando sesión…' : 'Cerrar sesión' }}
          </button>
        </div>
      </div>
    </div>

    <LeoIdleWarning />
  </header>
</template>
