<script setup lang="ts">
/**
 * Renderizado condicional por tag de acción. Sin permiso el contenido NO se
 * renderiza (no es un `display: none`); se muestra el slot `#fallback` si hay.
 *
 * <LeoCan tag="leo.users.create"><UiButton>Nuevo</UiButton></LeoCan>
 * <LeoCan :tag="['leo.audit.view', 'leo.audit.export']" any>…</LeoCan>
 */
const props = withDefaults(
  defineProps<{
    tag: string | string[]
    /** Basta con uno de los tags. */
    any?: boolean
    /** Exige todos (por defecto). */
    all?: boolean
  }>(),
  { any: false, all: false }
)

const allowed = useCan(() => props.tag, () => (props.any && !props.all ? 'any' : 'all'))
</script>

<template>
  <slot v-if="allowed" />
  <slot v-else name="fallback" />
</template>
