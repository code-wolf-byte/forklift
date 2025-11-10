(function () {
  function moveFooterToBody() {
    var footer = document.querySelector('[data-static-footer]');
    if (!footer || !document.body) return;

    // Mark the footer as managed so hydration scripts ignore it.
    footer.setAttribute('data-static-footer-ready', 'true');

    if (footer.parentNode !== document.body) {
      document.body.appendChild(footer);
    }
  }

  function initFooterGuard() {
    moveFooterToBody();

    if (!('MutationObserver' in window)) {
      return;
    }

    var observer = new MutationObserver(function () {
      moveFooterToBody();
    });

    observer.observe(document.body, { childList: true });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initFooterGuard);
  } else {
    initFooterGuard();
  }

  window.addEventListener('load', moveFooterToBody);
})();
