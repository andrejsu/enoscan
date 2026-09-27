<script setup lang="ts">
import type { SavedPairing } from '#shared/contracts'
import { Bookmark, Grape, ScanLine, Trash2 } from '@lucide/vue'

const { pairings, isLoaded, remove } = useSavedPairings()
const dateFormat = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long' })

function wineMeta(wine: SavedPairing['wine']) {
  return [wine.year, wine.color, wine.region].filter(Boolean).join(' · ')
}

function handleRemove(pairing: SavedPairing) {
  if (window.confirm(`Удалить сочетание с «${pairing.wine.name}»?`)) {
    remove(pairing.id)
  }
}
</script>

<template>
  <div class="page-container secondary-page">
    <header class="page-heading">
      <h1>Мои сочетания</h1>
      <p>Вина из каталога и то, с чем они вам понравились.</p>
    </header>

    <div v-if="!isLoaded" class="saved-empty" role="status">Загружаем сохранённые сочетания…</div>

    <section v-else-if="pairings.length" class="saved-list" aria-label="Сохранённые сочетания">
      <article v-for="pairing in pairings" :key="pairing.id" class="saved-card">
        <div class="saved-card__media">
          <img
            v-if="pairing.wine.imagePreviewUrl"
            :src="pairing.wine.imagePreviewUrl"
            :alt="`Бутылка ${pairing.wine.name}`"
            loading="lazy"
          >
          <Grape v-else :size="26" aria-hidden="true" />
        </div>
        <div class="saved-card__body">
          <h2>{{ pairing.wine.name }}</h2>
          <p v-if="pairing.wine.producer">{{ pairing.wine.producer }}</p>
          <p v-if="wineMeta(pairing.wine)" class="saved-card__meta">{{ wineMeta(pairing.wine) }}</p>
          <p v-if="pairing.pairing" class="saved-card__pairing">{{ pairing.pairing }}</p>
          <ul v-if="pairing.tastes.length" class="taste-chips" aria-label="Вкусы">
            <li v-for="taste in pairing.tastes" :key="taste" class="taste-chip">{{ taste }}</li>
          </ul>
          <time class="saved-card__date" :datetime="pairing.savedAt">{{ dateFormat.format(new Date(pairing.savedAt)) }}</time>
        </div>
        <button
          class="icon-button saved-card__remove"
          type="button"
          :aria-label="`Удалить сочетание с «${pairing.wine.name}»`"
          title="Удалить"
          @click="handleRemove(pairing)"
        >
          <Trash2 :size="19" aria-hidden="true" />
        </button>
      </article>
    </section>

    <section v-else class="saved-empty">
      <Bookmark :size="34" aria-hidden="true" />
      <h2>Пока ничего не сохранено</h2>
      <p>Найдите вино сканером или у сомелье и нажмите «В сочетания».</p>
      <NuxtLink class="button button--primary" to="/">
        <ScanLine :size="19" aria-hidden="true" />
        Открыть сканер
      </NuxtLink>
    </section>
  </div>
</template>
