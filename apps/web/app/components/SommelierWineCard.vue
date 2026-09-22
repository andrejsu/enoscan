<script setup lang="ts">
import type { WineCard } from '#shared/contracts'
import { ArrowRight, Grape } from '@lucide/vue'

defineProps<{ wine: WineCard }>()
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
      <NuxtLink
        class="sommelier-wine__link"
        :to="{ path: '/pairings/new', query: { slug: wine.slug, name: wine.name, producer: wine.producer } }"
      >
        К ужину <ArrowRight :size="16" aria-hidden="true" />
      </NuxtLink>
    </div>
  </article>
</template>
