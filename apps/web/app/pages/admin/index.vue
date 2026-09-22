<script setup lang="ts">
import type { CatalogAdminResponse, CatalogAdminWine, CatalogImageStatus } from '#shared/contracts'
import { Database, ImageOff, Images, Search, SearchX, TriangleAlert, Wine } from '@lucide/vue'

const draftSearch = ref('')
const appliedSearch = ref('')
const imageStatus = ref<CatalogImageStatus>('all')
const page = ref(1)
const selectedWine = ref<CatalogAdminWine | null>(null)
const requestQuery = computed(() => ({
  q: appliedSearch.value,
  imageStatus: imageStatus.value,
  page: page.value,
}))

const { data, status, error, refresh } = await useFetch<CatalogAdminResponse>('/api/admin/wines', {
  query: requestQuery,
})

const stats = computed(() => {
  const summary = data.value?.summary
  if (!summary) {
    return []
  }

  return [
    { label: 'Уникальных вин', value: summary.uniqueWines, icon: Wine },
    { label: 'С фото', value: summary.winesWithImage, icon: Images },
    { label: 'Требуют проверки', value: summary.suspiciousMappings, icon: TriangleAlert },
    { label: 'В поисковом индексе', value: summary.indexedWines, icon: Database },
    { label: 'Файлов без вина', value: summary.orphanImages, icon: ImageOff },
  ]
})

const importedAt = computed(() => {
  const value = data.value?.summary.importedAt
  return value ? new Date(value).toLocaleString('ru-RU') : null
})

function handleSearch() {
  appliedSearch.value = draftSearch.value.trim()
  page.value = 1
}

function handleImageStatusChange() {
  page.value = 1
}

function handlePageChange(nextPage: number) {
  page.value = nextPage
  if (import.meta.client) {
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }
}

function handleImageRequested(wine: CatalogAdminWine) {
  selectedWine.value = wine
}

function handleLightboxClosed() {
  selectedWine.value = null
}
</script>

<template>
  <div class="page-container admin-page">
    <header class="admin-heading">
      <div>
        <p class="eyebrow">Диагностика данных</p>
        <h1>Каталог вина</h1>
        <p>Просмотр PostgreSQL, исходных дублей и связи карточек с эталонными изображениями.</p>
      </div>
      <span class="admin-readonly">Только просмотр</span>
    </header>

    <section v-if="stats.length" class="admin-stats" aria-label="Сводка каталога">
      <article v-for="item in stats" :key="item.label">
        <component :is="item.icon" :size="21" aria-hidden="true" />
        <strong>{{ item.value.toLocaleString('ru-RU') }}</strong>
        <span>{{ item.label }}</span>
      </article>
    </section>

    <section class="admin-panel" aria-labelledby="catalog-filters-title">
      <h2 id="catalog-filters-title" class="sr-only">Фильтры каталога</h2>
      <form class="admin-filters" @submit.prevent="handleSearch">
        <label class="admin-field">
          <span>Поиск</span>
          <span class="admin-input-wrap">
            <Search :size="18" aria-hidden="true" />
            <input
              v-model="draftSearch"
              type="search"
              maxlength="120"
              placeholder="Название, производитель, slug, регион"
            >
          </span>
        </label>

        <label class="admin-field">
          <span>Изображение</span>
          <select v-model="imageStatus" @change="handleImageStatusChange">
            <option value="all">Все карточки</option>
            <option value="with_image">С фото</option>
            <option value="without_image">Без фото</option>
            <option value="suspicious">Требуют проверки</option>
            <option value="not_indexed">Вне индекса поиска</option>
          </select>
        </label>

        <button class="button button--primary admin-search-button" type="submit">
          Найти
        </button>
      </form>

      <div v-if="data" class="admin-results-meta" aria-live="polite">
        <span>Найдено: <strong>{{ data.pagination.totalItems.toLocaleString('ru-RU') }}</strong></span>
        <span v-if="data.summary.duplicateSlugs">
          slug с дублями: <strong>{{ data.summary.duplicateSlugs.toLocaleString('ru-RU') }}</strong>
        </span>
        <span>
          строк CSV: <strong>{{ data.summary.rawRecords.toLocaleString('ru-RU') }}</strong>
        </span>
        <span v-if="data.summary.inactiveWines">
          снято с каталога: <strong>{{ data.summary.inactiveWines.toLocaleString('ru-RU') }}</strong>
        </span>
        <span>
          версия данных: <code :title="data.summary.datasetVersion">{{ data.summary.datasetVersion.slice(0, 12) }}</code>
          <template v-if="importedAt"> от {{ importedAt }}</template>
        </span>
      </div>
    </section>

    <div v-if="status === 'pending'" class="admin-state" role="status">
      <span class="loader" aria-hidden="true" />
      <p>Загружаем каталог…</p>
    </div>

    <div v-else-if="error" class="admin-state admin-state--error" role="alert">
      <TriangleAlert :size="28" aria-hidden="true" />
      <h2>Каталог временно недоступен</h2>
      <p>{{ error.message }}</p>
      <button class="button button--secondary" type="button" @click="refresh()">Повторить</button>
    </div>

    <div v-else-if="data && data.wines.length" class="admin-wine-grid">
      <AdminWineCard
        v-for="wineItem in data.wines"
        :key="wineItem.slug"
        :wine="wineItem"
        @image-requested="handleImageRequested"
      />
    </div>

    <div v-else class="admin-state">
      <SearchX :size="30" aria-hidden="true" />
      <h2>Ничего не найдено</h2>
      <p>Измените запрос или выберите другой фильтр изображений.</p>
    </div>

    <nav
      v-if="data && data.pagination.totalPages > 1"
      class="admin-pagination"
      aria-label="Страницы каталога"
    >
      <button
        class="button button--secondary"
        type="button"
        :disabled="data.pagination.page <= 1"
        @click="handlePageChange(data.pagination.page - 1)"
      >
        Назад
      </button>
      <span>
        Страница <strong>{{ data.pagination.page }}</strong> из {{ data.pagination.totalPages }}
      </span>
      <button
        class="button button--secondary"
        type="button"
        :disabled="data.pagination.page >= data.pagination.totalPages"
        @click="handlePageChange(data.pagination.page + 1)"
      >
        Дальше
      </button>
    </nav>

    <CatalogImageLightbox :wine="selectedWine" @closed="handleLightboxClosed" />
  </div>
</template>
