<script setup lang="ts">
import {
  CalendarDays,
  LoaderCircle,
  MessageCircle,
  RotateCcw,
  Route,
  Send,
  Trash2,
  WalletCards,
} from '@lucide/vue'
import type { WineTour, WineTourFormat, WineTourRegion } from '#shared/tours/catalog'
import { wineTours } from '#shared/tours/catalog'

type RegionFilter = 'all' | WineTourRegion
type FormatFilter = 'all' | WineTourFormat
type BudgetFilter = 'all' | 2000 | 4000 | 6000

const emit = defineEmits<{
  tourOpened: [tour: WineTour]
}>()

const assistant = useTourRouteAssistant()
const prompt = ref('')
const regionFilter = ref<RegionFilter>('all')
const formatFilter = ref<FormatFilter>('all')
const budgetFilter = ref<BudgetFilter>('all')

const regionOptions: Array<{ value: RegionFilter, label: string }> = [
  { value: 'all', label: 'Все регионы' },
  { value: 'crimea', label: 'Крым' },
  { value: 'krasnodar', label: 'Краснодарский край' },
]

const formatOptions: Array<{ value: FormatFilter, label: string }> = [
  { value: 'all', label: 'Любой формат' },
  { value: 'tasting', label: 'С дегустацией' },
  { value: 'excursion', label: 'Экскурсия' },
  { value: 'sunset', label: 'На закате' },
]

const budgetOptions: Array<{ value: BudgetFilter, label: string }> = [
  { value: 'all', label: 'Любой бюджет' },
  { value: 2000, label: 'До 2 000 ₽' },
  { value: 4000, label: 'До 4 000 ₽' },
  { value: 6000, label: 'До 6 000 ₽' },
]

const suggestions = [
  'Крым на 2 дня: Инкерман, Новый Свет и игристое, до 6 тысяч',
  'Один день по подземным погребам до 3 тысяч',
  'Крым на 2 дня: биодинамика и современная архитектура',
]

const filteredTours = computed(() => wineTours.filter((tour) => {
  const isRegionMatch = regionFilter.value === 'all' || tour.region === regionFilter.value
  const isFormatMatch = formatFilter.value === 'all' || tour.format === formatFilter.value
  const isBudgetMatch = budgetFilter.value === 'all' || tour.price <= budgetFilter.value
  return isRegionMatch && isFormatMatch && isBudgetMatch
}))

const routeTours = computed(() => {
  if (!assistant.currentRoute.value) return []
  const toursById = new Map(wineTours.map(tour => [tour.id, tour]))
  return assistant.currentRoute.value.tourIds.flatMap((id) => {
    const tour = toursById.get(id)
    return tour ? [tour] : []
  })
})

const mapTours = computed(() => {
  const tourIds = new Set(filteredTours.value.map(tour => tour.id))
  for (const tour of routeTours.value) tourIds.add(tour.id)
  return wineTours.filter(tour => tourIds.has(tour.id))
})

const routePrice = computed(() => assistant.currentRoute.value
  ? new Intl.NumberFormat('ru-RU').format(assistant.currentRoute.value.estimatedPricePerPerson)
  : '')

const locationCount = computed(() => new Set(filteredTours.value.map(tour => tour.location)).size)
const hasActiveFilters = computed(() => (
  regionFilter.value !== 'all'
  || formatFilter.value !== 'all'
  || budgetFilter.value !== 'all'
))

const resultLabel = computed(() => {
  const tourCount = filteredTours.value.length
  const tourSuffix = tourCount === 1 ? 'программа' : tourCount >= 2 && tourCount <= 4 ? 'программы' : 'программ'
  const locations = locationCount.value
  const locationSuffix = locations === 1 ? 'точка' : locations >= 2 && locations <= 4 ? 'точки' : 'точек'
  return `${tourCount} ${tourSuffix} · ${locations} ${locationSuffix}`
})

async function handleSubmit() {
  const value = prompt.value
  if (!value.trim()) return
  prompt.value = ''
  await assistant.send(value)
}

async function handleSuggestion(suggestion: string) {
  prompt.value = suggestion
  await handleSubmit()
}

function resetFilters() {
  regionFilter.value = 'all'
  formatFilter.value = 'all'
  budgetFilter.value = 'all'
}
</script>

<template>
  <section class="route-studio" aria-labelledby="route-studio-title">
    <header class="route-studio__heading">
      <div>
        <h1 id="route-studio-title">Винные маршруты</h1>
      </div>
      <p>
        Выберите точки фильтрами или опишите поездку ассистенту — он соберёт маршрут по реальным винодельням.
      </p>
    </header>

    <section class="route-filters" aria-labelledby="route-filters-title">
      <div class="route-filters__title">
        <strong id="route-filters-title">Фильтры карты</strong>
        <span aria-live="polite">{{ resultLabel }}</span>
      </div>

      <label>
        <span>Регион</span>
        <select v-model="regionFilter">
          <option v-for="option in regionOptions" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </label>

      <label>
        <span>Формат</span>
        <select v-model="formatFilter">
          <option v-for="option in formatOptions" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </label>

      <label>
        <span>Цена за человека</span>
        <select v-model="budgetFilter">
          <option v-for="option in budgetOptions" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </label>

      <button
        v-if="hasActiveFilters"
        type="button"
        class="route-filters__reset"
        @click="resetFilters"
      >
        <RotateCcw :size="17" aria-hidden="true" />
        Сбросить
      </button>
    </section>

    <p v-if="!filteredTours.length" class="route-filters__empty" role="status">
      По этим условиям точек нет.
      <button type="button" @click="resetFilters">Показать все</button>
    </p>

    <div class="route-studio__grid">
      <WineTourRouteMap
        class="route-studio__map"
        :tours="mapTours"
        :route-ids="assistant.currentRoute.value?.tourIds ?? []"
        @opened="emit('tourOpened', $event)"
      />

      <section class="route-assistant" aria-label="ИИ-ассистент винных маршрутов">
        <header class="route-assistant__header">
          <MessageCircle :size="22" aria-hidden="true" />
          <div>
            <h2>Проводник по терруарам</h2>
            <span>{{ assistant.isMock.value ? 'Демо-режим' : 'ИИ-ассистент' }}</span>
          </div>
          <button
            v-if="assistant.messages.value.length"
            class="icon-button"
            type="button"
            aria-label="Очистить диалог и маршрут"
            title="Очистить диалог и маршрут"
            @click="assistant.clear"
          >
            <Trash2 :size="19" aria-hidden="true" />
          </button>
        </header>

        <div class="route-assistant__messages" aria-live="polite">
          <div class="route-message route-message--assistant">
            <p>Опишите поездку обычными словами: регион, дни, бюджет и что хочется увидеть.</p>
          </div>

          <div
            v-for="message in assistant.messages.value"
            :key="message.id"
            class="route-message"
            :class="`route-message--${message.role}`"
          >
            <p>{{ message.content }}</p>
          </div>

          <div v-if="assistant.isSubmitting.value" class="route-message route-message--assistant route-message--loading" role="status">
            <LoaderCircle :size="18" aria-hidden="true" />
            <span>Собираю точки и порядок поездки…</span>
          </div>
        </div>

        <div v-if="!assistant.messages.value.length" class="route-assistant__suggestions" aria-label="Примеры запросов">
          <button
            v-for="suggestion in suggestions"
            :key="suggestion"
            type="button"
            :disabled="assistant.isSubmitting.value"
            @click="handleSuggestion(suggestion)"
          >
            {{ suggestion }}
          </button>
        </div>

        <article v-if="assistant.currentRoute.value" class="route-summary" aria-label="Построенный маршрут">
          <div class="route-summary__title">
            <Route :size="20" aria-hidden="true" />
            <div>
              <span>Готовый маршрут</span>
              <h2>{{ assistant.currentRoute.value.title }}</h2>
            </div>
          </div>
          <p>{{ assistant.currentRoute.value.summary }}</p>
          <div class="route-summary__facts">
            <span><CalendarDays :size="16" aria-hidden="true" />{{ assistant.currentRoute.value.days }} дн.</span>
            <span><WalletCards :size="16" aria-hidden="true" />≈ {{ routePrice }} ₽ / человек</span>
          </div>
          <ol>
            <li v-for="(tour, index) in routeTours" :key="tour.id">
              <button type="button" @click="emit('tourOpened', tour)">
                <span>{{ index + 1 }}</span>
                <span><strong>{{ tour.location }}</strong><small>{{ tour.title }}</small></span>
              </button>
            </li>
          </ol>
        </article>

        <div v-if="assistant.errorMessage.value" class="route-assistant__error" role="alert">
          <span>{{ assistant.errorMessage.value }}</span>
          <button type="button" @click="assistant.retry">Повторить</button>
        </div>

        <form class="route-assistant__form" @submit.prevent="handleSubmit">
          <label class="sr-only" for="route-prompt">Опишите желаемый винный маршрут</label>
          <textarea
            id="route-prompt"
            v-model="prompt"
            rows="2"
            maxlength="800"
            placeholder="Например: Крым, два дня, до 8 тысяч…"
            :disabled="assistant.isSubmitting.value"
            @keydown.enter.exact.prevent="handleSubmit"
          />
          <button
            type="submit"
            :disabled="!assistant.isHydrated.value || assistant.isSubmitting.value || !prompt.trim()"
            aria-label="Построить маршрут"
          >
            <LoaderCircle v-if="assistant.isSubmitting.value" class="spin" :size="20" aria-hidden="true" />
            <Send v-else :size="20" aria-hidden="true" />
          </button>
        </form>
        <p class="route-assistant__disclaimer">План не является бронью. Даты и доступность подтверждаются у винодельни.</p>
      </section>
    </div>
  </section>
</template>

<style scoped>
.route-studio {
  min-width: 0;
}

.route-studio__heading {
  display: grid;
  grid-template-columns: minmax(0, 1.25fr) minmax(280px, .75fr);
  align-items: end;
  gap: 32px;
  margin-bottom: 24px;
}

.route-studio__heading h1 {
  margin: 0;
}

.route-studio__heading > p {
  max-width: 470px;
  margin: 0 0 7px;
  color: var(--color-muted);
  font-size: 16px;
  line-height: 1.5;
}

.route-filters {
  min-width: 0;
  display: grid;
  grid-template-columns: minmax(180px, 1fr) repeat(3, minmax(150px, .72fr)) auto;
  align-items: end;
  gap: 12px;
  padding: 16px 20px;
  margin-bottom: 16px;
  border: 1px solid rgb(143 61 66 / 12%);
  border-radius: 24px;
  background: var(--color-paper);
  box-shadow: var(--shadow-paper);
}

.route-filters__title {
  min-width: 0;
  min-height: 44px;
  display: grid;
  align-content: center;
}

.route-filters__title strong {
  color: var(--color-ink);
  font-family: var(--font-display);
  font-size: 20px;
  font-weight: 500;
  line-height: 1.25;
}

.route-filters__title span {
  color: var(--color-muted);
  font-size: 14px;
}

.route-filters label {
  min-width: 0;
  display: grid;
  gap: 6px;
}

.route-filters label > span {
  color: var(--color-muted);
  font-size: 13px;
  font-weight: 600;
}

.route-filters select {
  width: 100%;
  min-height: 44px;
  padding: 9px 34px 9px 12px;
  border: 1px solid var(--color-chip-line);
  border-radius: 12px;
  color: var(--color-ink);
  background-color: var(--color-paper);
  cursor: pointer;
  transition: border-color 0.3s ease-in;
}

.route-filters select:hover {
  border-color: var(--color-wine);
}

.route-filters__reset {
  min-height: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  padding: 0 12px;
  border: 0;
  border-radius: 12px;
  color: var(--color-wine);
  background: transparent;
  font-weight: 600;
  cursor: pointer;
  transition: color 0.3s ease-in;
}

.route-filters__reset:hover {
  color: var(--color-wine-hover);
}

.route-filters__empty {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px 14px;
  margin: -4px 0 16px;
  border-radius: var(--radius-sm);
  color: var(--color-attention-ink);
  background: var(--color-attention-surface);
  font-size: 14px;
}

.route-filters__empty button {
  min-height: 44px;
  border: 0;
  color: var(--color-wine);
  background: transparent;
  font-weight: 600;
  cursor: pointer;
}

.route-studio__grid {
  display: grid;
  grid-template-areas: 'map assistant';
  grid-template-columns: minmax(0, 1.3fr) minmax(340px, .7fr);
  gap: 18px;
  align-items: start;
}

.route-studio__map {
  grid-area: map;
}

.route-assistant {
  grid-area: assistant;
  min-width: 0;
  min-height: 664px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid rgb(143 61 66 / 12%);
  border-radius: var(--radius-lg);
  background: var(--color-paper);
  box-shadow: var(--shadow-paper);
}

/* Как шапка чата сомелье. */
.route-assistant__header {
  min-height: 64px;
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 10px;
  padding: 10px 16px 10px 20px;
  border-bottom: 1px solid var(--color-line);
  color: var(--color-wine);
}

.route-assistant__header > div {
  min-width: 0;
  display: grid;
}

.route-assistant__header h2 {
  margin: 0;
  overflow: hidden;
  color: var(--color-ink);
  font-size: 20px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.route-assistant__header span {
  color: var(--color-muted);
  font-size: 13px;
}

.route-assistant__messages {
  min-height: 116px;
  max-height: 240px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 18px;
  overflow-y: auto;
}

/* Пузыри как в чате сомелье: ответ — светлый, вопрос пользователя — зелёный. */
.route-message {
  max-width: 88%;
  padding: 12px 15px;
  border: 1px solid rgb(84 89 95 / 16%);
  border-radius: var(--radius-sm);
}

.route-message p {
  margin: 0;
  font-size: 15px;
  line-height: 1.5;
}

.route-message--assistant {
  align-self: flex-start;
  background: var(--color-canvas);
}

.route-message--user {
  align-self: flex-end;
  border-color: rgb(98 145 64 / 24%);
  color: var(--color-green-dark);
  background: var(--color-soft-green);
}

.route-message--loading {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--color-muted);
}

/* Чипы как подсказки сомелье; ::after добирает область касания до 44px. */
.route-assistant__suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 0 18px 18px;
}

.route-assistant__suggestions button {
  position: relative;
  min-height: 32px;
  max-width: 100%;
  padding: 5px 12px;
  border: 1px solid var(--color-chip-line);
  border-radius: 16px;
  color: var(--color-wine);
  background: var(--color-paper);
  font-size: 14px;
  font-weight: 600;
  line-height: 20px;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.3s ease-in;
}

.route-assistant__suggestions button::after {
  content: '';
  position: absolute;
  inset: -6px 0;
}

.route-assistant__suggestions button:hover {
  border-color: var(--color-wine);
}

.route-summary {
  margin: 0 18px 18px;
  padding: 16px;
  border: 1px solid var(--color-line);
  border-radius: var(--radius-md);
  background: var(--color-scanner-surface);
}

.route-summary__title {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  color: var(--color-wine);
}

.route-summary__title > div {
  min-width: 0;
}

.route-summary__title span {
  color: var(--color-muted);
  font-size: 13px;
}

.route-summary h2 {
  margin: 2px 0 0;
  color: var(--color-ink);
  font-size: 22px;
}

.route-summary > p {
  margin: 12px 0;
  color: var(--color-muted);
  font-size: 14px;
}

.route-summary__facts {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.route-summary__facts span {
  min-height: 32px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border: 1px solid var(--color-chip-line);
  border-radius: 16px;
  color: var(--color-ink);
  background: var(--color-paper);
  font-size: 14px;
  font-weight: 600;
}

.route-summary ol {
  display: grid;
  gap: 6px;
  padding: 0;
  margin: 0;
  list-style: none;
}

.route-summary li button {
  width: 100%;
  min-height: 48px;
  display: grid;
  grid-template-columns: 30px 1fr;
  align-items: center;
  gap: 9px;
  padding: 7px 10px;
  border: 1px solid var(--color-chip-line);
  border-radius: 12px;
  background: var(--color-paper);
  text-align: left;
  cursor: pointer;
  transition: border-color 0.3s ease-in;
}

.route-summary li button:hover {
  border-color: var(--color-wine);
}

.route-summary li button > span:first-child {
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  color: var(--color-paper);
  background: var(--color-wine);
  font-size: 12px;
  font-weight: 600;
}

.route-summary li button > span:last-child {
  min-width: 0;
  display: grid;
}

.route-summary li small {
  overflow: hidden;
  color: var(--color-muted);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.route-assistant__error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 18px;
  color: var(--color-wine-dark);
  background: var(--color-soft-wine);
  font-size: 14px;
}

.route-assistant__error button {
  min-height: 44px;
  border: 0;
  color: var(--color-wine);
  background: transparent;
  font-weight: 600;
  cursor: pointer;
}

.route-assistant__form {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 48px;
  align-items: end;
  gap: 8px;
  padding: 14px 16px;
  margin-top: auto;
  border-top: 1px solid var(--color-line);
}

.route-assistant__form textarea {
  width: 100%;
  min-height: 52px;
  max-height: 120px;
  resize: none;
  padding: 12px 13px;
  border: 1px solid var(--color-line);
  border-radius: var(--radius-sm);
  color: var(--color-ink);
  background: var(--color-paper);
  font-size: 16px;
  line-height: 1.35;
}

.route-assistant__form textarea:focus {
  border-color: var(--color-green);
}

.route-assistant__form button {
  width: 48px;
  height: 48px;
  display: grid;
  place-items: center;
  border: 0;
  border-radius: 50%;
  color: var(--color-paper);
  background: var(--color-wine);
  cursor: pointer;
  transition: background-color 0.3s ease-in;
}

.route-assistant__form button:hover:not(:disabled) {
  background: var(--color-wine-hover);
}

.route-assistant__form button:disabled,
.route-assistant__suggestions button:disabled {
  cursor: not-allowed;
  opacity: .46;
}

.route-assistant__disclaimer {
  padding: 0 18px 14px;
  margin: 0;
  color: var(--color-muted);
  font-size: 12px;
  text-align: center;
}

.route-assistant button:active,
.route-filters button:active {
  opacity: .82;
}

@media (max-width: 1080px) {
  .route-filters {
    grid-template-columns: repeat(3, minmax(0, 1fr)) auto;
  }

  .route-filters__title {
    grid-column: 1 / -1;
  }
}

@media (max-width: 980px) {
  .route-studio__heading {
    grid-template-columns: 1fr;
    gap: 10px;
  }

  .route-studio__grid {
    grid-template-areas:
      'map'
      'assistant';
    grid-template-columns: minmax(0, 1fr);
  }

  .route-assistant {
    min-height: 0;
  }
}

@media (max-width: 680px) {
  .route-studio__heading > p {
    font-size: 15px;
  }

  .route-filters {
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    padding: 12px;
  }

  .route-filters__title,
  .route-filters label:first-of-type,
  .route-filters__reset {
    grid-column: 1 / -1;
  }

  .route-filters__reset {
    width: 100%;
  }

  .route-filters__empty {
    align-items: flex-start;
    flex-direction: column;
  }

  .route-assistant,
  .route-studio__map {
    border-radius: 24px;
  }
}

@media (max-width: 390px) {
  .route-filters {
    grid-template-columns: 1fr;
  }

  .route-filters__title,
  .route-filters label:first-of-type,
  .route-filters__reset {
    grid-column: auto;
  }
}
</style>
