<script setup lang="ts">
import { Camera, ImagePlus, LoaderCircle, RotateCcw, ScanLine, Upload } from '@lucide/vue'
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

const viewfinderLabel = computed(() => {
  if (props.status === 'processing') {
    return 'Сверяем выбранную этикетку с каталогом'
  }

  if (props.previewUrl) {
    return 'Фото этикетки выбрано. Нажмите или перетащите другой файл, чтобы заменить его'
  }

  return 'Выбрать или перетащить фотографию винной этикетки'
})

function handleFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  const file = getFirstScanFile(target.files)

  if (file) {
    dragDepth.value = 0
    isDragging.value = false
    emit('fileSelected', file)
  }
}

function handleGalleryRequested() {
  if (props.status === 'processing') return

  if (galleryInput.value) {
    galleryInput.value.value = ''
    galleryInput.value.click()
  }
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
    <div class="scanner__copy">
      <p class="eyebrow">Поиск по каталогу российских вин</p>
      <h1 id="scanner-heading">Покажите этикетку — найдём точную карточку</h1>
      <p>
        Снимайте бутылку прямо или выберите готовое фото. Год и мелкие надписи должны быть видны.
      </p>
    </div>

    <div class="scanner__stage">
      <button
        class="viewfinder"
        :class="{
          'viewfinder--filled': previewUrl,
          'viewfinder--loading': status === 'processing',
          'viewfinder--dragging': isDragging,
        }"
        type="button"
        :aria-label="viewfinderLabel"
        :aria-describedby="error ? 'scanner-file-error' : 'scanner-file-hint'"
        :disabled="status === 'processing'"
        @click="handleGalleryRequested"
        @dragenter.prevent="handleDragEnter"
        @dragover.prevent="handleDragOver"
        @dragleave.prevent="handleDragLeave"
        @drop.prevent.stop="handleDrop"
      >
        <img
          v-if="previewUrl"
          class="viewfinder__preview"
          :src="previewUrl"
          alt="Выбранная фотография винной этикетки"
        >
        <div v-else class="viewfinder__empty" aria-hidden="true">
          <span class="viewfinder__art">
            <span class="viewfinder__bottle" />
            <span class="viewfinder__scan-badge">
              <ScanLine :size="27" stroke-width="1.5" />
            </span>
          </span>
          <strong class="viewfinder__title">Добавьте фото этикетки</strong>
          <span class="viewfinder__description">Перетащите сюда или нажмите, чтобы выбрать</span>
        </div>

        <span class="viewfinder__corner viewfinder__corner--tl" />
        <span class="viewfinder__corner viewfinder__corner--tr" />
        <span class="viewfinder__corner viewfinder__corner--bl" />
        <span class="viewfinder__corner viewfinder__corner--br" />

        <span
          v-if="previewUrl && status !== 'processing' && !isDragging"
          class="viewfinder__ready-badge"
          aria-hidden="true"
        >
          <span /> Фото готово · нажмите, чтобы заменить
        </span>

        <span v-if="isDragging" class="viewfinder__drop-overlay" aria-hidden="true">
          <span class="viewfinder__upload-icon">
            <Upload :size="30" stroke-width="1.8" />
          </span>
          <strong>Отпустите фото</strong>
          <span>Покажем превью перед поиском</span>
        </span>

        <div v-if="status === 'processing'" class="viewfinder__progress" role="status">
          <LoaderCircle class="spin" :size="28" aria-hidden="true" />
          <strong>Сверяем этикетку</strong>
          <span>Ищем точный год и позицию каталога</span>
        </div>
      </button>

      <div v-if="status === 'idle'" class="scanner__actions">
        <label class="button button--primary" for="wine-camera">
          <Camera :size="20" aria-hidden="true" />
          Снять этикетку
        </label>
        <label class="button button--secondary" for="wine-gallery">
          <ImagePlus :size="20" aria-hidden="true" />
          Выбрать фото
        </label>
      </div>

      <div v-else-if="status === 'ready'" class="scanner__actions">
        <button class="button button--primary" type="button" @click="emit('scanRequested')">
          <ScanLine :size="20" aria-hidden="true" />
          Найти вино
        </button>
        <button class="button button--quiet" type="button" @click="handleReset">
          <RotateCcw :size="19" aria-hidden="true" />
          Удалить фото
        </button>
      </div>

      <button
        v-else-if="status === 'error'"
        class="button button--primary scanner__retry"
        type="button"
        @click="handleGalleryRequested"
      >
        <RotateCcw :size="19" aria-hidden="true" />
        Выбрать другое фото
      </button>

      <input
        id="wine-camera"
        ref="cameraInput"
        class="sr-only"
        type="file"
        name="image"
        accept="image/jpeg,image/png,image/webp"
        capture="environment"
        :disabled="status === 'processing'"
        @change="handleFileChange"
      >
      <input
        id="wine-gallery"
        ref="galleryInput"
        class="sr-only"
        type="file"
        name="image"
        accept="image/jpeg,image/png,image/webp"
        :disabled="status === 'processing'"
        @change="handleFileChange"
      >

      <p v-if="error" id="scanner-file-error" class="scanner__error" role="alert">{{ error }}</p>
      <p v-else id="scanner-file-hint" class="scanner__hint">JPEG, PNG или WebP · до 10 МБ</p>
    </div>
  </section>
</template>
