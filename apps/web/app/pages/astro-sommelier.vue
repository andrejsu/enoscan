<script setup lang="ts">
import { zodiacWineProfiles } from '#shared/contracts'
import { ArrowRight, Grape, RefreshCw, Sparkles, TriangleAlert } from '@lucide/vue'

definePageMeta({ middleware: 'astro-enabled' })

const { errorMessage, isLoading, response, retry, selectedSign, selectSign } = useAstroRecommendations()
</script>

<template>
  <div class="page-container secondary-page astro-page">
    <header class="astro-hero">
      <div>
        <p class="eyebrow">Подбор по характеру вина</p>
        <h1>Астро-сомелье</h1>
        <p>Выберите знак — мы найдём в каталоге вина с подходящим стилевым профилем и объясним выбор через реальные сорта и характеристики.</p>
      </div>
      <Sparkles :size="58" aria-hidden="true" />
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
          @click="selectSign(profile.id)"
        >
          <ZodiacMark :symbol="profile.symbol" />
          <strong>{{ profile.name }}</strong>
          <small>{{ profile.dates }}</small>
        </button>
      </div>
    </section>

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
              :to="{ path: '/pairings/new', query: { slug: wine.slug, name: wine.name, producer: wine.producer } }"
            >
              К ужину <ArrowRight :size="17" aria-hidden="true" />
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
</template>
