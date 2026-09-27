<script setup lang="ts">
import { Menu, X } from '@lucide/vue'
import { isFeatureEnabled } from '#shared/utils/feature-flags'
import { isScannerRestart } from '~/utils/scanner-nav'

const config = useRuntimeConfig()
const route = useRoute()
const scannerReset = useScannerReset()
const isMenuOpen = ref(false)
const isAstroEnabled = computed(() => isFeatureEnabled(config.public.astroEnabled))
const isSommelierEnabled = computed(() => config.public.sommelierMode !== 'off')
const isCatalogEnabled = computed(() => isFeatureEnabled(config.public.catalogEnabled))

const navItems = computed(() => [
  { to: '/', label: 'Сканер', isVisible: true },
  { to: '/pairings', label: 'Мои сочетания', isVisible: true },
  { to: '/sommelier', label: 'Сомелье', isVisible: isSommelierEnabled.value },
  { to: '/tours', label: 'Винные туры', isVisible: true },
  { to: '/astro-sommelier', label: 'Астро-сомелье', isVisible: isAstroEnabled.value },
  { to: '/admin', label: 'Каталог', isVisible: isCatalogEnabled.value },
].filter(item => item.isVisible))
// Каталог — инструмент разработчиков, в мобильное меню не выводим.
const mobileNavItems = computed(() => navItems.value.filter(item => item.to !== '/admin'))

watch(isMenuOpen, (isOpen) => {
  document.body.classList.toggle('is-scroll-locked', isOpen)
})

watch(() => route.path, () => {
  isMenuOpen.value = false
})

onBeforeUnmount(() => {
  document.body.classList.remove('is-scroll-locked')
})

function handleNavClick(to: string) {
  isMenuOpen.value = false
  if (isScannerRestart(to, route.path)) {
    scannerReset.request()
  }
}
</script>

<template>
  <header class="site-header" @keydown.esc="isMenuOpen = false">
    <div class="page-container">
      <div class="site-header__bar" :class="{ 'site-header__bar--open': isMenuOpen }">
        <div class="site-header__top">
          <NuxtLink
            class="brand"
            to="/"
            aria-label="Своё Вино — на главную"
            @click="handleNavClick('/')"
          >
            <img src="/svg/svoe-vino-logo.svg" width="160" height="40" alt="">
          </NuxtLink>

          <nav class="site-nav" aria-label="Основная навигация">
            <NuxtLink
              v-for="item in navItems"
              :key="item.to"
              class="site-nav__link"
              :to="item.to"
              @click="handleNavClick(item.to)"
            >
              {{ item.label }}
            </NuxtLink>
          </nav>

          <button
            class="site-header__menu-button"
            type="button"
            :aria-label="isMenuOpen ? 'Закрыть меню' : 'Открыть меню'"
            :aria-expanded="isMenuOpen"
            aria-controls="mobile-nav"
            @click="isMenuOpen = !isMenuOpen"
          >
            <X v-if="isMenuOpen" :size="24" aria-hidden="true" />
            <Menu v-else :size="24" aria-hidden="true" />
          </button>
        </div>

        <nav
          v-if="isMenuOpen"
          id="mobile-nav"
          class="mobile-nav"
          aria-label="Меню"
        >
          <NuxtLink
            v-for="item in mobileNavItems"
            :key="item.to"
            class="mobile-nav__link"
            :to="item.to"
            @click="handleNavClick(item.to)"
          >
            {{ item.label }}
          </NuxtLink>
        </nav>
      </div>
    </div>
  </header>
</template>
