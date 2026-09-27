<script setup lang="ts">
import { Bookmark, Database, Map, ScanLine, Sparkles, Wine } from '@lucide/vue'
import { isFeatureEnabled } from '#shared/utils/feature-flags'
import { isScannerRestart } from '~/utils/scanner-nav'

const config = useRuntimeConfig()
const route = useRoute()
const scannerReset = useScannerReset()
const isAstroEnabled = computed(() => isFeatureEnabled(config.public.astroEnabled))
const isSommelierEnabled = computed(() => config.public.sommelierMode !== 'off')
const isCatalogEnabled = computed(() => isFeatureEnabled(config.public.catalogEnabled))

const navItems = computed(() => [
  { to: '/', icon: ScanLine, ariaLabel: 'Сканер', label: 'Сканер', shortLabel: 'Сканер', isVisible: true },
  { to: '/pairings', icon: Bookmark, ariaLabel: 'Мои сочетания', label: 'Мои сочетания', shortLabel: 'Сочетания', isVisible: true },
  { to: '/sommelier', icon: Wine, ariaLabel: 'Цифровой сомелье', label: 'Сомелье', shortLabel: 'Сомелье', isVisible: isSommelierEnabled.value },
  { to: '/tours', icon: Map, ariaLabel: 'Винные туры', label: 'Винные туры', shortLabel: 'Туры', isVisible: true },
  { to: '/astro-sommelier', icon: Sparkles, ariaLabel: 'Астро-сомелье', label: 'Астро-сомелье', shortLabel: 'Астро', isVisible: isAstroEnabled.value },
  { to: '/admin', icon: Database, ariaLabel: 'Каталог', label: 'Каталог', shortLabel: 'Каталог', isVisible: isCatalogEnabled.value },
].filter(item => item.isVisible))

function handleNavClick(to: string) {
  if (isScannerRestart(to, route.path)) {
    scannerReset.request()
  }
}
</script>

<template>
  <header class="site-header">
    <div class="page-container site-header__inner">
      <NuxtLink
        class="brand"
        to="/"
        aria-label="Сканер российских вин — на главную"
        @click="handleNavClick('/')"
      >
        <span class="brand__mark" aria-hidden="true">СВ</span>
        <span class="brand__text">
          <strong>Своё вино</strong>
          <small>сканер этикеток</small>
        </span>
      </NuxtLink>

      <nav class="site-nav" aria-label="Основная навигация">
        <NuxtLink
          v-for="item in navItems"
          :key="item.to"
          class="site-nav__link"
          :class="{ 'site-nav__link--desktop-only': item.to === '/admin' }"
          :to="item.to"
          :aria-label="item.ariaLabel"
          @click="handleNavClick(item.to)"
        >
          <component :is="item.icon" class="site-nav__icon" :size="20" aria-hidden="true" />
          <span class="site-nav__label site-nav__label--short" aria-hidden="true">{{ item.shortLabel }}</span>
          <span class="site-nav__label site-nav__label--full" aria-hidden="true">{{ item.label }}</span>
        </NuxtLink>
      </nav>
    </div>
  </header>
</template>
