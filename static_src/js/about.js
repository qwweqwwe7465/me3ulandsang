const toast = document.getElementById('toast');
const toastText = document.getElementById('toastText');

if (window.SUGGESTION_SUBMITTED && toast && toastText) {
  toastText.textContent = "Thanks - Feedback sent";
  toast.classList.add('is-visible');
  setTimeout(() => toast.classList.remove('is-visible'), 2600);
}

const nav = document.getElementById('nav');
if (nav) {
  window.addEventListener('scroll', () => nav.classList.toggle('is-scrolled', window.scrollY > 12));
}
