<template>
  <div class="app-shell">
    <a class="skip-link" href="#main-content">К основному содержимому</a>
    <AppHeader />
    <main id="main-content" tabindex="-1">
      <slot />
    </main>
    <footer class="site-footer">
      <div class="page-container site-footer__inner">
        <p>Продуктовый прототип для кейса РСХБ Цифра</p>
        <p>Сделано командой Винозавры</p>
      </div>
    </footer>
  </div>
</template>
