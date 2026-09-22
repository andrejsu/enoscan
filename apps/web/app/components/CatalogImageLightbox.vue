<script setup lang="ts">
import type { CatalogAdminWine } from '#shared/contracts'
import { X } from '@lucide/vue'

const props = defineProps<{
  wine: CatalogAdminWine | null
}>()

const emit = defineEmits<{
  closed: []
}>()

const dialog = useTemplateRef<HTMLDialogElement>('dialog')

watch(() => props.wine, async (wine) => {
  await nextTick()

  if (wine && dialog.value && !dialog.value.open) {
    dialog.value.showModal()
  } else if (!wine && dialog.value?.open) {
    dialog.value.close()
  }
})

function closeDialog() {
  dialog.value?.close()
}

function handleBackdropClick(event: MouseEvent) {
  if (event.target === dialog.value) {
    closeDialog()
  }
}

function handleClosed() {
  emit('closed')
}
</script>

<template>
  <Teleport to="body">
    <dialog
      ref="dialog"
      class="catalog-lightbox"
      aria-labelledby="catalog-lightbox-title"
      @click="handleBackdropClick"
      @close="handleClosed"
    >
      <div v-if="wine?.imageUrl" class="catalog-lightbox__panel" @click.self="closeDialog">
        <button
          class="catalog-lightbox__close"
          type="button"
          aria-label="Закрыть полноэкранное фото"
          autofocus
          @click="closeDialog"
        >
          <X :size="24" aria-hidden="true" />
        </button>

        <img
          :src="wine.imageUrl"
          :alt="`Эталонное фото ${wine.name}`"
          decoding="async"
        >

        <div class="catalog-lightbox__caption">
          <p>Эталонное изображение</p>
          <h2 id="catalog-lightbox-title">{{ wine.name }}</h2>
          <span>{{ wine.producer }}</span>
        </div>
      </div>
    </dialog>
  </Teleport>
</template>
