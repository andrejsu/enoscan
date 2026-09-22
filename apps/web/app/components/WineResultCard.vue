<script setup lang="ts">
import type { ScanResponse, WineCard } from '#shared/contracts'
import { matchScanWineToZodiac } from '#shared/contracts'
import { ArrowRight, CircleAlert, Grape, Info, MapPin, Palette, RotateCcw, Sparkles, Tags, ThermometerSun, Utensils } from '@lucide/vue'
import { isFeatureEnabled } from '#shared/utils/feature-flags'

const props = defineProps<{
  result: ScanResponse
}>()

const emit = defineEmits<{
  resetRequested: []
}>()

const selectedWine = ref<WineCard | null>(null)
const displayedWine = computed(() => selectedWine.value ?? props.result.wine)
watch(() => props.result, () => { selectedWine.value = null })

const config = useRuntimeConfig()
const isAstroEnabled = computed(() => isFeatureEnabled(config.public.astroEnabled))

const pairingQuery = computed(() => ({
  slug: displayedWine.value?.slug,
  name: displayedWine.value?.name,
  producer: displayedWine.value?.producer,
}))

const zodiacMatch = computed(() => matchScanWineToZodiac(props.result))
</script>

<template>
  <section class="result-section" aria-live="polite">
    <div v-if="result.isMock" class="demo-banner">
      Демонстрационные данные — настоящее CV-распознавание ещё не подключено
    </div>

    <article v-if="displayedWine" class="wine-card">
      <figure class="wine-card__visual">
        <img
          v-if="displayedWine.imageUrl"
          class="wine-card__image"
          :src="displayedWine.imageUrl"
          :alt="`Эталонная бутылка ${displayedWine.name}`"
          decoding="async"
        >
        <span v-else class="wine-card__bottle" aria-hidden="true">
          <span>СВ</span>
        </span>
        <figcaption v-if="displayedWine.imageUrl">Фото из каталога</figcaption>
      </figure>

      <div class="wine-card__content">
        <p class="eyebrow">{{ selectedWine ? 'Вы выбрали это вино' : 'Совпадение найдено' }}</p>
        <p class="wine-card__producer">{{ displayedWine.producer }}</p>
        <h2>{{ displayedWine.name }}</h2>
        <p v-if="displayedWine.year" class="wine-card__year">{{ displayedWine.year }}</p>
        <p v-if="displayedWine.description" class="wine-card__description">
          {{ displayedWine.description }}
        </p>

        <details v-if="isAstroEnabled && zodiacMatch" class="zodiac-popover">
          <summary aria-label="Узнать винный знак этой бутылки">
            <Sparkles :size="18" aria-hidden="true" />
            Если бы у этого вина был знак…
            <Info :size="16" aria-hidden="true" />
          </summary>
          <div class="zodiac-popover__panel">
            <ZodiacMark :symbol="zodiacMatch.profile.symbol" size="compact" />
            <div>
              <p class="eyebrow">{{ zodiacMatch.profile.element }} · {{ zodiacMatch.profile.name }}</p>
              <h3>{{ zodiacMatch.profile.tagline }}</h3>
              <p>{{ zodiacMatch.profile.description }}</p>
              <small>Рекомендация на основе описания и сорта вина.</small>
            </div>
          </div>
        </details>

        <dl class="wine-facts">
          <div v-if="displayedWine.category">
            <dt><Tags :size="17" aria-hidden="true" /> Категория</dt>
            <dd>{{ displayedWine.category }}</dd>
          </div>
          <div v-if="displayedWine.color">
            <dt><Palette :size="17" aria-hidden="true" /> Цвет</dt>
            <dd>{{ displayedWine.color }}</dd>
          </div>
          <div v-if="displayedWine.region">
            <dt><MapPin :size="17" aria-hidden="true" /> Регион</dt>
            <dd>{{ displayedWine.region }}</dd>
          </div>
          <div v-if="displayedWine.grapeVarieties.length">
            <dt><Grape :size="17" aria-hidden="true" /> Сорта</dt>
            <dd>{{ displayedWine.grapeVarieties.join(', ') }}</dd>
          </div>
          <div v-if="displayedWine.servingTemperature">
            <dt><ThermometerSun :size="17" aria-hidden="true" /> Подача</dt>
            <dd>{{ displayedWine.servingTemperature }}</dd>
          </div>
        </dl>

        <div class="wine-card__actions">
          <NuxtLink class="button button--primary" :to="{ path: '/pairings/new', query: pairingQuery }">
            <Utensils :size="19" aria-hidden="true" />
            Подобрать к ужину
            <ArrowRight :size="18" aria-hidden="true" />
          </NuxtLink>
          <button class="button button--quiet" type="button" @click="emit('resetRequested')">
            <RotateCcw :size="18" aria-hidden="true" />
            Сканировать ещё
          </button>
        </div>
      </div>
    </article>

    <article v-else class="result-notice">
      <CircleAlert :size="28" aria-hidden="true" />
      <div>
        <p class="eyebrow">
          {{ result.status === 'uncertain' ? 'Нужно уточнить' : 'В каталоге не найдено' }}
        </p>
        <h2>
          {{ result.status === 'uncertain' ? 'Проверьте название и год' : 'Мы не можем подтвердить совпадение' }}
        </h2>
        <p>{{ result.guidance || 'Попробуйте снять этикетку ближе и без бликов.' }}</p>
        <div v-if="result.status === 'uncertain'" class="scanner__actions" aria-label="Кандидаты из каталога">
          <template v-for="candidate in result.candidates" :key="candidate.slug">
            <button
              v-if="candidate.wine"
              class="button button--secondary"
              type="button"
              @click="selectedWine = candidate.wine"
            >
              {{ candidate.wine.name }} · {{ candidate.wine.producer }}
            </button>
          </template>
        </div>
        <button class="button button--primary" type="button" @click="emit('resetRequested')">
          <RotateCcw :size="18" aria-hidden="true" />
          Сделать другое фото
        </button>
      </div>
    </article>
  </section>
</template>
