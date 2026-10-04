// ---- bug report form ----
const bugForm = document.getElementById('bugForm');
if (bugForm) {
  bugForm.addEventListener('submit', () => {
    setTimeout(() => bugForm.reset(), 0);
  });
}

// ---- nav scroll shadow ----
const nav = document.getElementById('nav');
if (nav) {
  window.addEventListener('scroll', () => nav.classList.toggle('is-scrolled', window.scrollY > 12));
}
