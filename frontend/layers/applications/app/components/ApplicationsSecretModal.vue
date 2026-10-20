<script setup lang="ts">
import type { ApplicationSecretReveal } from '../types/applications'

/**
 * Modal de UN SOLO USO del `client_secret` (al crear una app o rotar el
 * secreto). Solo se cierra con el botón explícito (sin Esc ni clic fuera) para
 * que no se pierda por accidente. El secreto llega por prop y no se guarda en
 * ningún otro sitio; al cerrar, quien la usa descarta `reveal`.
 */
const props = defineProps<{
  reveal: ApplicationSecretReveal | null
}>()

const emit = defineEmits<{ close: [] }>()

const copied = ref(false)
const copyError = ref<string | null>(null)

watch(() => props.reveal, () => {
  copied.value = false
  copyError.value = null
})

async function copy() {
  if (!props.reveal) return
  copyError.value = null
  try {
    await navigator.clipboard.writeText(props.reveal.secret)
    copied.value = true
  } catch {
    copied.value = false
    copyError.value = 'No se pudo copiar automáticamente. Selecciona el secreto y cópialo a mano.'
  }
}

const title = computed(() =>
  props.reveal?.reason === 'rotated' ? 'Nuevo secreto de la aplicación' : 'Aplicación creada'
)
</script>

<template>
  <UiModal
    :open="reveal !== null"
    :title="title"
    description="Este secreto se muestra una sola vez."
    :dismissable="false"
    hide-close-button
  >
    <div v-if="reveal" class="space-y-4">
      <UiAlert variant="warning" title="Cópialo y guárdalo ahora">
        No volverá a mostrarse: Leo solo conserva su huella. Si lo pierdes, deberás generar uno nuevo<template v-if="reveal.reason === 'rotated'"> (el anterior ya dejó de funcionar)</template>.
      </UiAlert>

      <dl class="space-y-3 text-sm">
        <div>
          <dt class="font-medium text-text-muted">client_id</dt>
          <dd class="mt-1"><code class="break-all rounded-md bg-default-100 px-2 py-1" data-testid="secret-client-id">{{ reveal.clientId }}</code></dd>
        </div>
        <div>
          <dt class="font-medium text-text-muted">client_secret</dt>
          <dd class="mt-1 flex flex-wrap items-center gap-2">
            <code class="break-all rounded-md bg-default-100 px-2 py-1" data-testid="secret-value">{{ reveal.secret }}</code>
            <UiButton variant="secondary" size="sm" data-testid="secret-copy" @click="copy">
              {{ copied ? 'Copiado' : 'Copiar' }}
            </UiButton>
          </dd>
        </div>
      </dl>
      <UiAlert v-if="copyError" variant="danger" :message="copyError" data-testid="secret-copy-error" />
    </div>

    <template #footer>
      <UiButton data-testid="secret-done" @click="emit('close')">Ya guardé el secreto</UiButton>
    </template>
  </UiModal>
</template>
