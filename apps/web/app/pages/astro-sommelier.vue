<script setup lang="ts">
import type { ZodiacSignId } from '#shared/contracts'
import { zodiacWineProfiles } from '#shared/contracts'
import { BookmarkPlus, Grape, RefreshCw, TriangleAlert } from '@lucide/vue'
import { detectPairingTastes, pairingLocation } from '~/utils/pairings'

definePageMeta({ middleware: 'astro-enabled' })

const { errorMessage, isLoading, response, retry, selectedSign, selectSign } = useAstroRecommendations()
const output = useTemplateRef<HTMLElement>('output')

function scrollToOutput() {
  const behavior = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'
  output.value?.scrollIntoView({ behavior, block: 'start' })
}

// Сначала показываем индикатор загрузки, затем докручиваем к результату:
// пока страница короткая, браузер не может поднять блок к верху экрана.
async function handleSignSelected(sign: ZodiacSignId) {
  const request = selectSign(sign)
  await nextTick()
  scrollToOutput()
  await request
  await nextTick()
  scrollToOutput()
}
</script>

<template>
  <div class="page-container secondary-page astro-page">
    <header class="astro-hero">
      <div>
        <h1>Астро-сомелье</h1>
        <p>Выберите знак — мы найдём в каталоге вина с подходящим стилевым профилем и объясним выбор через реальные сорта и характеристики.</p>
      </div>
    </header>

    <section aria-labelledby="zodiac-picker-title">
      <h2 id="zodiac-picker-title" class="astro-section-title">Ваш знак</h2>
      <div class="zodiac-grid">
        <button
          v-for="profile in zodiacWineProfiles"
          :key="profile.id"
          class="zodiac-option"
          :class="{ 'zodiac-option--selected': selectedSign === profile.id }"
          type="button"
          :aria-pressed="selectedSign === profile.id"
          :disabled="isLoading"
          @click="handleSignSelected(profile.id)"
        >
          <ZodiacMark :symbol="profile.symbol" />
          <strong>{{ profile.name }}</strong>
          <small>{{ profile.dates }}</small>
        </button>
      </div>
    </section>

    <div ref="output">
      <div v-if="isLoading" class="astro-state" role="status">
        <RefreshCw class="spin" :size="28" aria-hidden="true" />
        <p>Ищем подходящие вина в каталоге…</p>
      </div>

      <div v-else-if="errorMessage" class="astro-state astro-state--error" role="alert">
        <TriangleAlert :size="28" aria-hidden="true" />
        <p>{{ errorMessage }}</p>
        <button class="button button--secondary" type="button" @click="retry">Повторить</button>
      </div>

      <section v-else-if="response" class="astro-results" aria-live="polite">
        <header class="astro-result-heading">
          <ZodiacMark :symbol="response.profile.symbol" size="large" />
          <div>
            <p class="eyebrow">{{ response.profile.element }} · {{ response.profile.name }}</p>
            <h2>{{ response.profile.tagline }}</h2>
            <p>{{ response.profile.description }}</p>
            <p class="astro-styles">Ищем: {{ response.profile.wineStyles.join(' · ') }}</p>
          </div>
        </header>

        <div v-if="response.wines.length" class="astro-wine-grid">
          <article v-for="wine in response.wines" :key="wine.slug" class="astro-wine-card">
            <div class="astro-wine-card__media">
              <img v-if="wine.imagePreviewUrl || wine.imageUrl" :src="wine.imagePreviewUrl || wine.imageUrl || undefined" :alt="`Бутылка ${wine.name}`">
              <Grape v-else :size="36" aria-hidden="true" />
            </div>
            <div class="astro-wine-card__body">
              <p>{{ wine.producer }}</p>
              <h3>{{ wine.name }}</h3>
              <span>{{ [wine.color, wine.region].filter(Boolean).join(' · ') }}</span>
              <strong v-if="wine.grapeVarieties.length">{{ wine.grapeVarieties.join(', ') }}</strong>
              <NuxtLink
                class="button button--quiet"
                :to="pairingLocation(wine, { tastes: detectPairingTastes(wine.category, wine.description) })"
              >
                <BookmarkPlus :size="17" aria-hidden="true" /> В сочетания
              </NuxtLink>
            </div>
          </article>
        </div>
        <div v-else class="astro-state">
          <p>В каталоге пока нет вин, соответствующих выбранному стилю.</p>
        </div>

        <p class="astro-disclaimer">Астрологическая рекомендация основана на стилях и характеристиках вин из каталога.</p>
      </section>
    </div>
  </div>
</template>
