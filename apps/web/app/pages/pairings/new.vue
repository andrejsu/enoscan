<script setup lang="ts">
import type { SavedPairing } from '#shared/contracts'
import { BookmarkCheck, ChevronLeft } from '@lucide/vue'

const route = useRoute()
const router = useRouter()
const { save } = useSavedPairings()

const wine = computed(() => ({
  slug: typeof route.query.slug === 'string' ? route.query.slug : 'demo-wine',
  name: typeof route.query.name === 'string' ? route.query.name : 'Выбранное вино',
  producer: typeof route.query.producer === 'string' ? route.query.producer : 'Производитель',
}))

const dish = ref('Стейк или запечённое мясо')
const preference = ref<SavedPairing['preference']>('richer')
const isSaved = ref(false)

const verdict = computed(() => preference.value === 'richer'
  ? 'Хорошее сочетание: насыщенность блюда поддерживает структуру вина.'
  : 'Подойдёт, если выбрать более лёгкий соус и умеренную подачу.')

async function handleSave() {
  const id = typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : String(Date.now())

  save({
    id,
    wine: wine.value,
    dish: dish.value,
    preference: preference.value,
    verdict: verdict.value,
    savedAt: new Date().toISOString(),
  })
  isSaved.value = true

  await router.push('/pairings')
}
</script>

<template>
  <div class="page-container secondary-page pairing-page">
    <NuxtLink class="back-link" to="/">
      <ChevronLeft :size="18" aria-hidden="true" />
      К найденному вину
    </NuxtLink>

    <header class="page-heading">
      <p class="eyebrow">Подойдёт ли к моему ужину</p>
      <h1>{{ wine.name }}</h1>
      <p>{{ wine.producer }}</p>
    </header>

    <form class="pairing-form" @submit.prevent="handleSave">
      <fieldset>
        <legend>Что будет на ужин?</legend>
        <label class="field">
          <span>Блюдо</span>
          <input v-model.trim="dish" type="text" maxlength="120" required>
        </label>
      </fieldset>

      <fieldset>
        <legend>Какой вкус хочется сегодня?</legend>
        <div class="choice-grid">
          <label :class="{ 'choice--selected': preference === 'softer' }">
            <input v-model="preference" type="radio" value="softer">
            <strong>Помягче</strong>
            <span>Деликатный вкус и лёгкая подача</span>
          </label>
          <label :class="{ 'choice--selected': preference === 'richer' }">
            <input v-model="preference" type="radio" value="richer">
            <strong>Понасыщеннее</strong>
            <span>Выраженный вкус и плотная текстура</span>
          </label>
        </div>
      </fieldset>

      <section class="pairing-verdict" aria-live="polite">
        <p class="eyebrow">Предварительный ответ</p>
        <h2>{{ verdict }}</h2>
        <p>Демо использует простое правило. Реальные гастросочетания будут рассчитаны по полям каталога.</p>
      </section>

      <button class="button button--primary button--wide" type="submit" :disabled="isSaved">
        <BookmarkCheck :size="20" aria-hidden="true" />
        Сохранить сочетание
      </button>
    </form>
  </div>
</template>
