<script setup lang="ts">
import type { WineCard } from '#shared/contracts'
import { BookmarkPlus, Grape } from '@lucide/vue'
import { detectPairingTastes, pairingLocation } from '~/utils/pairings'

const props = defineProps<{
  wine: WineCard
  /** «к запечённой рыбе» из вопроса пользователя. */
  pairing?: string
  /** Ответ сомелье, в котором вино рекомендовано: из него берутся вкусы. */
  reply?: string
}>()

const pairingTo = computed(() => pairingLocation(props.wine, {
  pairing: props.pairing,
  tastes: detectPairingTastes(props.reply, props.wine.category, props.wine.description),
}))
</script>

<template>
  <article class="sommelier-wine">
    <div class="sommelier-wine__media">
      <img
        v-if="wine.imagePreviewUrl || wine.imageUrl"
        :src="wine.imagePreviewUrl || wine.imageUrl || undefined"
        :alt="`Бутылка ${wine.name}`"
        width="94"
        height="94"
        loading="lazy"
      >
      <Grape v-else :size="28" aria-hidden="true" />
    </div>
    <div class="sommelier-wine__body">
      <p>{{ wine.producer }}</p>
      <h3>{{ wine.name }}</h3>
      <span>{{ [wine.color, wine.region].filter(Boolean).join(' · ') }}</span>
      <NuxtLink class="sommelier-wine__link" :to="pairingTo">
        <BookmarkPlus :size="16" aria-hidden="true" /> В сочетания
      </NuxtLink>
    </div>
  </article>
</template>
