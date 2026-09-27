<script setup lang="ts">
import type { ScanRecommendation, WineCard } from '#shared/contracts'
import { ArrowRight, CircleAlert, Grape } from '@lucide/vue'

defineProps<{
  recommendations: readonly ScanRecommendation[]
}>()

const emit = defineEmits<{
  wineSelected: [wine: WineCard]
}>()
</script>

<template>
  <section class="scan-recommendations" aria-labelledby="scan-recommendations-title">
    <header class="scan-recommendations__header">
      <p class="eyebrow">Это не найденное вино</p>
      <h3 id="scan-recommendations-title">Похожие вина из каталога</h3>
    </header>

    <ul class="scan-recommendations__list">
      <li v-for="item in recommendations" :key="item.slug">
        <article class="scan-recommendation">
          <div class="scan-recommendation__media">
            <img
              v-if="item.wine.imagePreviewUrl || item.wine.imageUrl"
              :src="item.wine.imagePreviewUrl || item.wine.imageUrl || undefined"
              :alt="`Бутылка ${item.wine.name}`"
              width="80"
              height="104"
              loading="lazy"
            >
            <Grape v-else :size="26" aria-hidden="true" />
          </div>
          <div class="scan-recommendation__body">
            <p class="scan-recommendation__producer">{{ item.wine.producer }}</p>
            <h4>{{ item.wine.name }}</h4>
            <p class="scan-recommendation__reason">{{ item.reason }}</p>
            <p v-if="item.difference" class="scan-recommendation__difference">
              <CircleAlert :size="15" aria-hidden="true" />
              {{ item.difference }}
            </p>
            <button
              class="scan-recommendation__open"
              type="button"
              :aria-label="`Открыть карточку: ${item.wine.name}`"
              @click="emit('wineSelected', item.wine)"
            >
              Открыть карточку
              <ArrowRight :size="16" aria-hidden="true" />
            </button>
          </div>
        </article>
      </li>
    </ul>
  </section>
</template>
