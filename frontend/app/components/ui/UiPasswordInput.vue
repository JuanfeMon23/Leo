<script setup lang="ts">
/**
 * Input de contraseña con ojo para mostrar/ocultar, a la IZQUIERDA dentro del
 * campo. Envuelve `UiTextInput` de Andromeda: mismos props (`v-model`, `id`,
 * `placeholder`, `disabled`, `invalid`…), atributos nativos (`autocomplete`,
 * `name`…) y enlace con `UiFormField` (vee-validate, estado inválido en rojo).
 *
 * Siempre inicia oculta, vuelve a oculta al desmontar y cuando el valor se
 * vacía (reset del formulario tras enviar). No guarda ni registra el valor.
 */
defineOptions({ inheritAttrs: false })

const props = withDefaults(
  defineProps<{
    modelValue?: string | null
    disabled?: boolean
  }>(),
  { modelValue: undefined, disabled: false }
)

const ctx = inject(UI_FORM_FIELD_KEY, null)
const visible = ref(false)
const attrs = useAttrs()

const currentValue = computed(() => props.modelValue ?? (ctx?.field?.value.value as string | undefined) ?? '')
const invalid = computed(() => Boolean(attrs.invalid) || ctx?.invalid.value || false)

// Valor vaciado (reset tras enviar con éxito): la contraseña vuelve a oculta.
watch(currentValue, (v) => {
  if (!v) visible.value = false
})
onBeforeUnmount(() => { visible.value = false })

const label = computed(() => (visible.value ? 'Ocultar contraseña' : 'Mostrar contraseña'))
</script>

<template>
  <div class="relative">
    <button
      type="button"
      data-testid="password-toggle"
      :aria-label="label"
      :aria-pressed="visible"
      :disabled="disabled"
      class="absolute inset-y-0 left-0 z-10 flex w-10 items-center justify-center rounded-l-md outline-none transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-primary-500 disabled:cursor-not-allowed disabled:opacity-50"
      :class="invalid ? 'text-danger-600 hover:text-danger-700' : 'text-default-500 hover:text-text'"
      @click="visible = !visible"
    >
      <svg
        v-if="!visible"
        class="size-5"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
      >
        <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" />
        <circle cx="12" cy="12" r="3" />
      </svg>
      <svg
        v-else
        class="size-5"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
      >
        <path d="M9.9 5.2A10.4 10.4 0 0 1 12 5c6.5 0 10 7 10 7a17 17 0 0 1-3.2 4.2M6.6 6.6A16.6 16.6 0 0 0 2 12s3.5 7 10 7a9.7 9.7 0 0 0 4.4-1.1" />
        <path d="M14.1 14.1a3 3 0 1 1-4.2-4.2" />
        <path d="m3 3 18 18" />
      </svg>
    </button>
    <UiTextInput
      v-bind="$attrs"
      :model-value="modelValue"
      :disabled="disabled"
      :type="visible ? 'text' : 'password'"
      class="w-full pl-10"
    />
  </div>
</template>
