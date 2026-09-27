<script setup lang="ts">
import { LoaderCircle, Upload } from '@lucide/vue'
import { getFirstScanFile } from '~/utils/scan-file'

const emit = defineEmits<{
  fileSelected: [file: File]
  scanRequested: []
  resetRequested: []
}>()

const props = defineProps<{
  status: 'idle' | 'ready' | 'processing' | 'success' | 'error'
  previewUrl?: string
  error?: string
}>()

const cameraInput = useTemplateRef<HTMLInputElement>('cameraInput')
const galleryInput = useTemplateRef<HTMLInputElement>('galleryInput')
const dragDepth = ref(0)
const isDragging = ref(false)

function handleFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  const file = getFirstScanFile(target.files)

  if (file) {
    dragDepth.value = 0
    isDragging.value = false
    emit('fileSelected', file)
  }
}

function openPicker(input: HTMLInputElement | null) {
  if (props.status === 'processing' || !input) return

  input.value = ''
  input.click()
}

function handleDragEnter(event: DragEvent) {
  if (props.status === 'processing' || !event.dataTransfer?.types.includes('Files')) return

  dragDepth.value += 1
  isDragging.value = true
}

function handleDragOver(event: DragEvent) {
  if (props.status === 'processing' || !event.dataTransfer) return

  event.dataTransfer.dropEffect = 'copy'
}

function handleDragLeave() {
  dragDepth.value = Math.max(0, dragDepth.value - 1)
  isDragging.value = dragDepth.value > 0
}

function handleDrop(event: DragEvent) {
  dragDepth.value = 0
  isDragging.value = false

  if (props.status === 'processing') return

  const file = getFirstScanFile(event.dataTransfer?.files)
  if (file) {
    emit('fileSelected', file)
  }
}

function handleReset() {
  if (cameraInput.value) {
    cameraInput.value.value = ''
  }

  if (galleryInput.value) {
    galleryInput.value.value = ''
  }

  emit('resetRequested')
}
</script>

<template>
  <section class="scanner" aria-labelledby="scanner-heading">
    <header class="scanner__intro">
      <h1 id="scanner-heading">Свои вина</h1>
      <p>Сфотографируйте этикетку Российского вина или загрузите фото, чтобы найти его</p>
    </header>

    <div
      class="scanner-card"
      :class="{ 'scanner-card--dragging': isDragging }"
      @dragenter.prevent="handleDragEnter"
      @dragover.prevent="handleDragOver"
      @dragleave.prevent="handleDragLeave"
      @drop.prevent.stop="handleDrop"
    >
      <div class="scanner-card__visual">
        <img
          v-if="previewUrl"
          class="scanner-card__preview"
          :src="previewUrl"
          alt="Выбранная фотография винной этикетки"
        >
        <img
          v-else
          class="scanner-card__art"
          src="/svg/scanner.svg"
          width="119"
          height="120"
          alt=""
        >

        <div v-if="status === 'processing'" class="scanner-card__overlay" role="status">
          <LoaderCircle class="spin" :size="28" aria-hidden="true" />
          <span>Ищем вино в каталоге</span>
        </div>
        <div v-else-if="isDragging" class="scanner-card__overlay" aria-hidden="true">
          <Upload :size="28" />
          <span>Отпустите фото</span>
        </div>
      </div>

      <p v-if="error" class="scanner__error" role="alert">{{ error }}</p>

      <template v-if="status === 'ready' || status === 'processing'">
        <button
          class="scanner-card__primary"
          type="button"
          :disabled="status === 'processing'"
          @click="emit('scanRequested')"
        >
          Найти вино
        </button>
        <button
          class="scanner-card__secondary"
          type="button"
          :disabled="status === 'processing'"
          @click="handleReset"
        >
          Удалить фото
        </button>
      </template>
      <template v-else>
        <button class="scanner-card__primary" type="button" @click="openPicker(cameraInput)">
          Сканировать
        </button>
        <button class="scanner-card__secondary" type="button" @click="openPicker(galleryInput)">
          Загрузить фото
        </button>
      </template>

      <input
        ref="cameraInput"
        class="sr-only"
        type="file"
        name="image"
        accept="image/jpeg,image/png,image/webp"
        capture="environment"
        tabindex="-1"
        aria-hidden="true"
        :disabled="status === 'processing'"
        @change="handleFileChange"
      >
      <input
        ref="galleryInput"
        class="sr-only"
        type="file"
        name="image"
        accept="image/jpeg,image/png,image/webp"
        tabindex="-1"
        aria-hidden="true"
        :disabled="status === 'processing'"
        @change="handleFileChange"
      >
    </div>
  </section>
</template>
