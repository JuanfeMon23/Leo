<script setup lang="ts">
/**
 * Barra superior de Leo para todas las apps: app actual, selector de las apps
 * a las que el usuario tiene acceso, usuario y cerrar sesión. Ocupa la franja
 * superior del área de contenido (la barra lateral es de cada app); el slot
 * `#start` deja poner algo a la izquierda (p. ej. migas de pan).
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
const displayName = computed(() => {
  const user = session.user.value
  if (!user) return ''
  return `${user.first_name} ${user.last_name}`.trim() || user.username
})

const menuOpen = ref(false)
const menuRef = ref<HTMLElement | null>(null)
const menuId = useId()
const loggingOut = ref(false)

function onDocumentClick(event: MouseEvent) {
  if (menuOpen.value && menuRef.value && !menuRef.value.contains(event.target as Node)) menuOpen.value = false
}
function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') menuOpen.value = false
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

      <div class="hidden min-w-0 flex-col text-right leading-tight sm:flex">
        <span class="truncate text-sm font-medium text-text" data-testid="leo-user-name">{{ displayName }}</span>
        <span class="truncate text-xs text-text-muted">{{ session.user.value?.username }}</span>
      </div>

      <UiButton variant="ghost" size="sm" :loading="loggingOut" @click="logout">Cerrar sesión</UiButton>
    </div>

    <LeoIdleWarning />
  </header>
</template>
