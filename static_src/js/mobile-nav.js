// Keep the dock inside the visible viewport during mobile zoom/emulation.
(() => {
  const viewport = window.visualViewport;
  if (!viewport) return;

  const updatePosition = () => {
    const offset = Math.max(0, window.innerHeight - viewport.height - viewport.offsetTop);
    document.documentElement.style.setProperty('--mobile-nav-viewport-offset', `${offset}px`);
  };

  viewport.addEventListener('resize', updatePosition);
  viewport.addEventListener('scroll', updatePosition);
  window.addEventListener('resize', updatePosition);
  updatePosition();
})();
