<script setup lang="ts">
import type { PairingTaste } from '#shared/contracts'
import { pairingTastes } from '#shared/contracts'
import { BookmarkCheck, ChevronLeft, Grape, ScanLine } from '@lucide/vue'
import { parsePairingTastes, restorePairingWine } from '~/utils/pairings'

const route = useRoute()
const router = useRouter()
const { save } = useSavedPairings()

// Сочетание всегда привязано к вину из каталога: без него форме нечего сохранять.
const wine = computed(() => restorePairingWine(route.query))
const wineMeta = computed(() => [wine.value?.year, wine.value?.color, wine.value?.region].filter(Boolean).join(' · '))

const pairing = ref(typeof route.query.pairing === 'string' ? route.query.pairing.slice(0, 120) : '')
const tastes = ref<PairingTaste[]>(parsePairingTastes(route.query.tastes))
const isSaved = ref(false)

function handleBack() {
  if (window.history.state?.back) {
    router.back()
  }
  else {
    void router.push('/')
  }
}

async function handleSave() {
  if (!wine.value) return

  save({
    id: crypto.randomUUID(),
    wine: wine.value,
    pairing: pairing.value,
    tastes: pairingTastes.filter(taste => tastes.value.includes(taste)),
    savedAt: new Date().toISOString(),
  })
  isSaved.value = true

  await router.push('/pairings')
}
</script>

<template>
  <div class="page-container secondary-page pairing-page">
    <button class="back-link" type="button" @click="handleBack">
      <ChevronLeft :size="18" aria-hidden="true" />
      Назад
    </button>

    <template v-if="wine">
      <header class="pairing-wine">
        <div class="pairing-wine__media">
          <img v-if="wine.imagePreviewUrl" :src="wine.imagePreviewUrl" :alt="`Бутылка ${wine.name}`">
          <Grape v-else :size="32" aria-hidden="true" />
        </div>
        <div>
          <h1>{{ wine.name }}</h1>
          <p v-if="wine.producer">{{ wine.producer }}</p>
          <p v-if="wineMeta" class="pairing-wine__meta">{{ wineMeta }}</p>
        </div>
      </header>

      <form class="pairing-form" @submit.prevent="handleSave">
        <label class="field">
          <span>С чем сочетается</span>
          <input
            v-model.trim="pairing"
            type="text"
            maxlength="120"
            placeholder="Например: к запечённой рыбе, к сырам, для аперитива"
          >
        </label>

        <fieldset>
          <legend>Вкусы</legend>
          <div class="taste-chips">
            <label
              v-for="taste in pairingTastes"
              :key="taste"
              class="taste-chip"
              :class="{ 'taste-chip--selected': tastes.includes(taste) }"
            >
              <input v-model="tastes" class="sr-only" type="checkbox" :value="taste">
              {{ taste }}
            </label>
          </div>
        </fieldset>

        <button class="button button--primary button--wide" type="submit" :disabled="isSaved">
          <BookmarkCheck :size="20" aria-hidden="true" />
          Сохранить в сочетания
        </button>
      </form>
    </template>

    <section v-else class="saved-empty">
      <h1>Вино не выбрано</h1>
      <p>Найдите вино сканером, у сомелье или в астро-сомелье и нажмите «В сочетания».</p>
      <NuxtLink class="button button--primary" to="/">
        <ScanLine :size="19" aria-hidden="true" />
        Открыть сканер
      </NuxtLink>
    </section>
  </div>
</template>
