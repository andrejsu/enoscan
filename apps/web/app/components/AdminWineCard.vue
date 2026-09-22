<script setup lang="ts">
import type { CatalogAdminWine, CatalogMappingKind, CatalogReviewStatus } from '#shared/contracts'
import { ChevronDown, ImageOff, Maximize2 } from '@lucide/vue'

const mappingKindLabels: Record<CatalogMappingKind, string> = {
  image_filename: 'По имени фото из CSV',
  slug: 'По slug',
  fuzzy_filename: 'По похожему имени файла',
  manual: 'Вручную (overrides)',
}

const reviewStatusLabels: Record<CatalogReviewStatus, string> = {
  auto: 'Автоматически',
  suspicious: 'Требует проверки',
  confirmed: 'Подтверждено',
}

const props = defineProps<{
  wine: CatalogAdminWine
}>()

const emit = defineEmits<{
  imageRequested: [wine: CatalogAdminWine]
}>()

const imageStatus = computed(() => {
  if (!props.wine.imageUrl) return { label: 'Без фото', modifier: 'missing' }
  if (props.wine.reviewStatus === 'suspicious') return { label: 'Проверить привязку', modifier: 'warning' }
  return { label: 'Фото привязано', modifier: 'ready' }
})

function handleImageRequest() {
  emit('imageRequested', props.wine)
}
</script>

<template>
  <article class="admin-wine-card">
    <div class="admin-wine-card__media">
      <button
        v-if="wine.imageUrl"
        class="admin-wine-card__image-button"
        type="button"
        :aria-label="`Открыть фото ${wine.name} на весь экран`"
        @click="handleImageRequest"
      >
        <img
          :src="wine.imagePreviewUrl || wine.imageUrl"
          :alt="`Эталонное фото ${wine.name}`"
          loading="lazy"
          decoding="async"
        >
        <span class="admin-wine-card__image-action">
          <Maximize2 :size="15" aria-hidden="true" />
          Открыть
        </span>
      </button>
      <div v-else class="admin-wine-card__missing">
        <ImageOff :size="28" aria-hidden="true" />
        <span>Фото не привязано</span>
      </div>
    </div>

    <div class="admin-wine-card__body">
      <div class="admin-wine-card__heading">
        <div>
          <p class="admin-wine-card__producer">{{ wine.producer }}</p>
          <h2>{{ wine.name }}</h2>
        </div>
        <div class="admin-wine-card__statuses">
          <span class="catalog-status" :class="`catalog-status--${imageStatus.modifier}`">
            {{ imageStatus.label }}
          </span>
          <span
            class="catalog-status"
            :class="wine.isIndexed ? 'catalog-status--ready' : 'catalog-status--missing'"
          >
            {{ wine.isIndexed ? 'В индексе поиска' : 'Вне индекса поиска' }}
          </span>
        </div>
      </div>

      <p class="admin-wine-card__summary">
        {{ [wine.year, wine.category, wine.region].filter(Boolean).join(' · ') || 'Основные сведения не заполнены' }}
      </p>

      <details class="admin-wine-card__details">
        <summary>
          Все данные
          <ChevronDown :size="18" aria-hidden="true" />
        </summary>

        <dl class="admin-data-list">
          <div>
            <dt>Slug</dt>
            <dd><code>{{ wine.slug }}</code></dd>
          </div>
          <div>
            <dt>Категория</dt>
            <dd>{{ wine.category || '—' }}</dd>
          </div>
          <div>
            <dt>Цвет</dt>
            <dd>{{ wine.color || '—' }}</dd>
          </div>
          <div>
            <dt>Регион</dt>
            <dd>{{ wine.region || '—' }}</dd>
          </div>
          <div>
            <dt>Сорта</dt>
            <dd>{{ wine.grapeVarieties.join(', ') || '—' }}</dd>
          </div>
          <div>
            <dt>Строк с этим slug</dt>
            <dd>{{ wine.rawRecordCount }}</dd>
          </div>
          <div>
            <dt>Имя фото в CSV</dt>
            <dd><code>{{ wine.sourceImageFilename || '—' }}</code></dd>
          </div>
          <div>
            <dt>Файл Strapi</dt>
            <dd><code>{{ wine.imageStrapiPath || '—' }}</code></dd>
          </div>
          <div>
            <dt>Тип привязки</dt>
            <dd>{{ wine.mappingKind ? mappingKindLabels[wine.mappingKind] : 'Не привязано' }}</dd>
          </div>
          <div>
            <dt>Оценка привязки</dt>
            <dd>{{ wine.mappingScore ?? '—' }}</dd>
          </div>
          <div>
            <dt>Проверка</dt>
            <dd>{{ wine.reviewStatus ? reviewStatusLabels[wine.reviewStatus] : '—' }}</dd>
          </div>
        </dl>

        <div class="admin-wine-card__description">
          <h3>Описание</h3>
          <p>{{ wine.description || 'Описание отсутствует.' }}</p>
        </div>
      </details>
    </div>
  </article>
</template>
