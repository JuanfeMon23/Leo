<script setup lang="ts">
import { appInitial, buildProfileUrl, userDisplayName, userInitials } from '../lib/userMenu'
import type { LeoTransportKind } from '../lib/transport'

/**
 * Barra superior de Leo, IDÉNTICA en todas las apps: renderiza su propio
 * `<header>` completo (alto, fondo, borde, sticky, z-index, padding), así que
 * la app NO la envuelve en contenedores con estilos propios. Contrato en la
 * cabecera de `client/nuxt.config.ts`.
 *
 * Slots: `#start` (a la izquierda: hamburguesa del menú lateral o logo según el
 * layout de la app) y `#end` (acciones propias de la app, antes del selector).
 * Muestra la app actual, el selector de aplicaciones (desplegable con las apps
 * a las que el usuario tiene acceso) y el menú de usuario (datos de solo
 * lectura, "Mi perfil" —en Leo `/profile`; en apps `bff`,
 * `<url>/profile?return=…`— y "Cerrar sesión" en rojo).
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
const menuButtonRef = ref<HTMLButtonElement | null>(null)
const menuId = useId()
const userOpen = ref(false)
const userRef = ref<HTMLElement | null>(null)
const userButtonRef = ref<HTMLButtonElement | null>(null)
const userMenuId = useId()
const loggingOut = ref(false)
const currentUrl = ref('')

const profileUrl = computed(() => buildProfileUrl(
  { transport: config.transport as LeoTransportKind, leoUrl: config.url },
  currentUrl.value
))

function closeAppsMenu(restoreFocus = false) {
  if (!menuOpen.value) return
  menuOpen.value = false
  if (restoreFocus) menuButtonRef.value?.focus()
}
function toggleAppsMenu() {
  menuOpen.value = !menuOpen.value
  if (menuOpen.value) userOpen.value = false
}
function onAppsFocusOut(event: FocusEvent) {
  // El foco salió del selector (Tab hacia otro elemento): se cierra.
  const next = event.relatedTarget as Node | null
  if (next && menuRef.value && !menuRef.value.contains(next)) menuOpen.value = false
}

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
  closeAppsMenu(true)
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

// Clases compartidas (un solo lugar para el lenguaje visual de la barra).
const focusRing = 'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-500'
const triggerClass = `flex h-10 items-center gap-2 text-sm font-medium text-default-700 transition duration-150 ease-out hover:bg-default-100 active:scale-[0.97] aria-expanded:bg-default-100 motion-reduce:transition-none motion-reduce:active:scale-100 ${focusRing}`
const panelClass = 'z-30 overflow-hidden rounded-xl border border-border bg-surface shadow-lg'
const itemClass = `flex min-h-11 w-full items-center gap-3 px-3 text-left text-sm font-medium transition-colors duration-150 focus-visible:outline-none motion-reduce:transition-none`
// Mismo lenguaje que el botón `danger-ghost` de Andromeda (texto danger-600, fondo danger-50/100).
const dangerItemClass = `${itemClass} text-danger-600 hover:bg-danger-50 focus-visible:bg-danger-50 active:bg-danger-100 disabled:opacity-60`
const neutralItemClass = `${itemClass} text-default-700 hover:bg-default-100 focus-visible:bg-default-100 active:bg-default-200`
const enterActive = 'transition duration-150 ease-out motion-reduce:transition-none'
const leaveActive = 'transition duration-100 ease-in motion-reduce:transition-none'
const hiddenState = 'opacity-0 scale-95 motion-reduce:scale-100'
</script>

<template>
  <header class="sticky top-0 z-20 flex h-14 w-full min-w-0 items-center gap-3 border-b border-border bg-surface/90 backdrop-blur-md max-sm:px-3 sm:px-6" data-testid="leo-topbar">
    <slot name="start" />

    <div class="flex min-w-0 items-center gap-2.5">
      <span class="relative flex h-2.5 w-2.5 shrink-0" aria-hidden="true">
        <span class="absolute inset-0 rounded-full bg-primary-500/25" />
        <span class="m-auto h-1.5 w-1.5 rounded-full bg-primary-500" />
      </span>
      <span class="truncate font-semibold tracking-tight text-text max-sm:text-sm sm:text-base" data-testid="leo-current-app">{{ currentName }}</span>
    </div>

    <div class="ml-auto flex items-center max-sm:gap-1 sm:gap-2">
      <slot name="end" />

      <template v-if="session.isAuthenticated.value">
        <div v-if="session.applications.value.length" ref="menuRef" class="sm:relative" @focusout="onAppsFocusOut">
          <button
            ref="menuButtonRef"
            type="button"
            :class="[triggerClass, 'rounded-md px-2.5']"
            aria-label="Aplicaciones"
            :aria-expanded="menuOpen"
            :aria-controls="menuId"
            data-testid="leo-apps-button"
            @click="toggleAppsMenu"
          >
            <svg viewBox="0 0 24 24" class="h-5 w-5 text-default-500" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" aria-hidden="true">
              <path d="M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z" />
            </svg>
            <span class="max-sm:hidden">Aplicaciones</span>
            <svg viewBox="0 0 24 24" class="h-4 w-4 text-default-500 transition-transform duration-150 max-sm:hidden motion-reduce:transition-none" :class="menuOpen ? 'rotate-180' : ''" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M6 9l6 6 6-6" />
            </svg>
          </button>
          <Transition :enter-active-class="enterActive" :leave-active-class="leaveActive" :enter-from-class="hiddenState" :leave-to-class="hiddenState">
            <div
              v-if="menuOpen"
              :id="menuId"
              role="group"
              aria-label="Aplicaciones a las que tienes acceso"
              :class="[panelClass, 'absolute top-full mt-2 max-sm:inset-x-3 max-sm:origin-top sm:right-0 sm:w-80 sm:origin-top-right']"
            >
              <p class="border-b border-border bg-surface-muted px-4 py-2.5 text-xs font-semibold uppercase tracking-wider text-text-muted">
                Tus aplicaciones
              </p>
              <ul class="max-h-80 overflow-y-auto p-1.5">
                <li v-for="app in session.applications.value" :key="app.slug">
                  <a
                    :href="app.base_url"
                    class="flex min-h-12 items-center gap-3 rounded-lg px-2.5 py-1.5 text-sm transition-colors duration-150 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary-500 motion-reduce:transition-none"
                    :class="app.slug === currentSlug ? 'bg-primary-50' : 'hover:bg-default-100 focus-visible:bg-default-100'"
                    :aria-current="app.slug === currentSlug ? 'page' : undefined"
                  >
                    <span
                      class="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-sm font-semibold"
                      :class="app.slug === currentSlug ? 'bg-primary-500 text-text-inverted' : 'bg-default-100 text-default-700'"
                      aria-hidden="true"
                    >{{ appInitial(app.name) }}</span>
                    <span class="min-w-0 flex-1 truncate font-medium" :class="app.slug === currentSlug ? 'text-primary-700' : 'text-default-800'" data-testid="leo-app-name">{{ app.name }}</span>
                    <span v-if="app.slug === currentSlug" class="flex shrink-0 items-center gap-1 text-xs font-medium text-primary-700">
                      <svg viewBox="0 0 24 24" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                        <path d="M5 12.5l4.5 4.5L19 7.5" />
                      </svg>
                      Actual
                    </span>
                  </a>
                </li>
              </ul>
            </div>
          </Transition>
        </div>

        <div ref="userRef" class="relative">
          <button
            ref="userButtonRef"
            type="button"
            :class="[triggerClass, 'max-sm:rounded-full max-sm:px-1 sm:rounded-md sm:pl-1.5 sm:pr-2.5']"
            aria-haspopup="menu"
            :aria-expanded="userOpen"
            :aria-controls="userMenuId"
            :aria-label="displayName ? `Menú de usuario: ${displayName}` : 'Menú de usuario'"
            data-testid="leo-user-button"
            @click="toggleUserMenu"
          >
            <span class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-linear-to-br from-primary-400 to-primary-700 text-xs font-semibold text-text-inverted shadow-sm" aria-hidden="true" data-testid="leo-user-initials">{{ initials }}</span>
            <div class="min-w-0 max-w-44 text-left leading-tight max-sm:hidden">
              <p class="truncate text-sm font-semibold text-text" data-testid="leo-user-name">{{ displayName }}</p>
              <p v-if="session.user.value?.email" class="truncate text-xs font-normal text-text-muted max-md:hidden" data-testid="leo-user-button-email">{{ session.user.value.email }}</p>
            </div>
            <svg viewBox="0 0 24 24" class="h-4 w-4 shrink-0 text-default-500 transition-transform duration-150 max-sm:hidden motion-reduce:transition-none" :class="userOpen ? 'rotate-180' : ''" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M6 9l6 6 6-6" />
            </svg>
          </button>
          <Transition :enter-active-class="enterActive" :leave-active-class="leaveActive" :enter-from-class="hiddenState" :leave-to-class="hiddenState">
            <div
              v-if="userOpen"
              :id="userMenuId"
              role="menu"
              aria-label="Menú de usuario"
              :class="[panelClass, 'absolute right-0 top-full mt-2 w-72 max-w-[calc(100vw-1.5rem)] origin-top-right']"
              @keydown="onUserMenuKeydown"
            >
              <div v-if="displayName" role="presentation" class="flex items-center gap-3 bg-surface-muted px-4 py-4" data-testid="leo-user-card">
                <span class="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-linear-to-br from-primary-400 to-primary-700 text-base font-semibold text-text-inverted shadow-sm" aria-hidden="true">{{ initials }}</span>
                <div class="min-w-0 leading-tight">
                  <p class="truncate text-sm font-semibold text-text">{{ displayName }}</p>
                  <p v-if="session.user.value?.email" class="mt-0.5 truncate text-xs text-text-muted" data-testid="leo-user-email">{{ session.user.value.email }}</p>
                  <p v-if="session.user.value?.username" class="truncate text-xs text-text-muted" data-testid="leo-user-username">@{{ session.user.value.username }}</p>
                </div>
              </div>
              <div v-if="displayName" role="separator" class="border-t border-border" />
              <div class="p-1.5">
                <NuxtLink
                  v-if="profileUrl"
                  :to="profileUrl"
                  role="menuitem"
                  :class="[neutralItemClass, 'rounded-lg']"
                  @click="userOpen = false"
                >
                  <svg viewBox="0 0 24 24" class="h-5 w-5 shrink-0 text-default-500" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M12 12a4 4 0 100-8 4 4 0 000 8zM4 20c0-4 3.5-6 8-6s8 2 8 6" />
                  </svg>
                  Mi perfil
                </NuxtLink>
              </div>
              <div role="separator" class="border-t border-border" />
              <div class="p-1.5">
                <button
                  type="button"
                  role="menuitem"
                  :class="[dangerItemClass, 'rounded-lg']"
                  data-testid="leo-logout"
                  :disabled="loggingOut"
                  @click="logout"
                >
                  <svg viewBox="0 0 24 24" class="h-5 w-5 shrink-0" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M9 4H6a2 2 0 00-2 2v12a2 2 0 002 2h3M16 8l4 4-4 4M20 12H9" />
                  </svg>
                  {{ loggingOut ? 'Cerrando sesión…' : 'Cerrar sesión' }}
                </button>
              </div>
            </div>
          </Transition>
        </div>
      </template>
    </div>

    <LeoIdleWarning />
  </header>
</template>
