  // ---- tracklist ----
  const tracks = [
    { num:1, title:'Low Ceilings' },
    { num:2, title:'Paper Moths', hasLyrics:true },
    { num:3, title:'The Long Hallway' },
    { num:4, title:'Static Windows' },
    { num:5, title:'Old Radiators' },
    { num:6, title:'Slow Rooms' },
  ];
  const lyricsIcon = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 19v3M8 22h8"/><path d="M12 15a4 4 0 0 0 4-4V6a4 4 0 0 0-8 0v5a4 4 0 0 0 4 4z"/><path d="M19 10a7 7 0 0 1-14 0"/></svg>`;
  const plusIcon = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>`;

  const tracklistEl = document.getElementById('tracklist');
  tracks.forEach(t => {
    const row = document.createElement('div');
    row.className = 'tracklist-row';
    row.innerHTML = `
      <span class="tracklist-num">${String(t.num).padStart(2,'0')}</span>
      <span class="tracklist-info">
        <span class="tracklist-title"><a href="#">${t.title}</a>${t.hasLyrics ? `<span class="tracklist-lyrics">${lyricsIcon}</span>` : ''}</span>
      </span>
      <button class="btn btn--ghost btn--icon" data-title="${t.title}" aria-label="Add ${t.title} to playlist">${plusIcon}</button>
    `;
    tracklistEl.appendChild(row);
  });

  // ---- like button ----
  const likeBtn = document.getElementById('likeBtn');
  const likeCount = document.getElementById('likeCount');
  let liked = false;
  const baseLikes = 428;
  likeBtn.addEventListener('click', () => {
    liked = !liked;
    likeBtn.classList.toggle('is-liked', liked);
    likeCount.textContent = liked ? baseLikes + 1 : baseLikes;
  });

  // ---- toast ----
  const toast = document.getElementById('toast');
  const toastText = document.getElementById('toastText');
  function showToast(text){
    toastText.textContent = text;
    toast.classList.add('is-visible');
    setTimeout(() => toast.classList.remove('is-visible'), 2400);
  }

  document.getElementById('addAllBtn').addEventListener('click', () => {
    showToast('All 6 tracks added to your playlist');
  });

  tracklistEl.addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-title]');
    if(!btn) return;
    showToast(`"${btn.dataset.title}" added to your playlist`);
  });

  // ---- nav scroll shadow ----
  const nav = document.getElementById('nav');
  window.addEventListener('scroll', () => nav.classList.toggle('is-scrolled', window.scrollY > 12));
