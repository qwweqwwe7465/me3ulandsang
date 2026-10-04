  // ---- shared catalog data ----
  // const songs = [
  //   { title:"Halfway to Ceres", artist:"Nova Marlowe", c1:"#8b6bff", c2:"#ff5fa2", logs:"12 logs", ago:"4d ago" },
  //   { title:"Static Bloom", artist:"The Filament", c1:"#2fe6c0", c2:"#8b6bff", logs:"9 logs", ago:"yesterday" },
  //   { title:"Low Tide Radio", artist:"Kite String Collective", c1:"#ff5fa2", c2:"#2fe6c0", logs:"8 logs", ago:"5d ago" },
  //   { title:"Amber Hallways", artist:"Six Rooms", c1:"#8b6bff", c2:"#2fe6c0", logs:"7 logs", ago:"3d ago" },
  //   { title:"Paper Moths", artist:"Delphine Ash", c1:"#ff5fa2", c2:"#8b6bff", logs:"6 logs", ago:"2h ago" },
  //   { title:"Concrete Bloom", artist:"Harbor Lines", c1:"#2fe6c0", c2:"#ff5fa2", logs:"5 logs", ago:"2d ago" },
  // ];

  const lyricsIcon = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 19v3M8 22h8"/><path d="M12 15a4 4 0 0 0 4-4V6a4 4 0 0 0-8 0v5a4 4 0 0 0 4 4z"/><path d="M19 10a7 7 0 0 1-14 0"/></svg>`;


  
  // ---- render top songs chart ----
  // const chartList = document.getElementById('chartList');
  // songs.forEach((s, i) => {
  //   const row = document.createElement('button');
  //   row.className = 'chart-row glass';
  //   row.setAttribute('aria-label', `${s.title} by ${s.artist}`);
  //   row.innerHTML = `
  //     <span class="chart-rank mono">${String(i+1).padStart(2,'0')}</span>
  //     <span class="chart-cover" style="--c1:${s.c1};--c2:${s.c2}"></span>
  //     <span class="chart-info">
  //       <span class="chart-title" style="display:block;">${s.title}</span>
  //       <span class="chart-artist" style="display:block;">${s.artist}</span>
  //     </span>
  //     <span class="chart-lyrics">${lyricsIcon}<span style="font-size:11px;">lyrics</span></span>
  //     <span class="chart-logs">${s.logs}</span>
  //   `;
  //   chartList.appendChild(row);
  // });

  // ---- render recently logged (reordered by "ago") ----
  // const recentRow = document.getElementById('recentRow');
  // const recentOrder = [4,1,5,3,0,2];
  // recentOrder.forEach(idx => {
  //   const s = songs[idx];
  //   const card = document.createElement('div');
  //   card.className = 'recent-card glass';
  //   card.innerHTML = `
  //     <span class="recent-cover" style="--c1:${s.c1};--c2:${s.c2}"></span>
  //     <span>
  //       <span class="recent-title" style="display:block;">${s.title}</span>
  //       <span class="recent-meta">${s.ago}</span>
  //     </span>
  //   `;
  //   recentRow.appendChild(card);
  // });

  // ---- render playlists ----
  // const playlists = [
  //   { title:"Late Night Drives", mood:"Chill", count:"24 tracks", updated:"3d ago",
  //     swatches:["#8b6bff,#ff5fa2","#2fe6c0,#8b6bff","#ff5fa2,#2fe6c0","#8b6bff,#2fe6c0"] },
  //   { title:"Study Sessions", mood:"Focus", count:"18 tracks", updated:"1w ago",
  //     swatches:["#2fe6c0,#8b6bff","#ff5fa2,#8b6bff","#2fe6c0,#ff5fa2","#8b6bff,#ff5fa2"] },
  //   { title:"Sunday Reset", mood:"Calm", count:"15 tracks", updated:"5d ago",
  //     swatches:["#8b6bff,#2fe6c0","#ff5fa2,#2fe6c0","#8b6bff,#ff5fa2","#2fe6c0,#8b6bff"] },
  //   { title:"Basement Tapes", mood:"Lo-fi", count:"30 tracks", updated:"2d ago",
  //     swatches:["#ff5fa2,#8b6bff","#8b6bff,#2fe6c0","#2fe6c0,#ff5fa2","#ff5fa2,#2fe6c0"] },
  // ];
  // const playlistGrid = document.getElementById('playlistGrid');
  // playlists.forEach(p => {
  //   const card = document.createElement('div');
  //   card.className = 'playlist-card glass';
  //   const thumb = p.swatches.map(pair => {
  //     const [c1,c2] = pair.split(',');
  //     return `<span style="background:linear-gradient(135deg,${c1},${c2})"></span>`;
  //   }).join('');
  //   card.innerHTML = `
  //     <div class="playlist-thumb">${thumb}</div>
  //     <p class="playlist-title">${p.title}</p>
  //     <p class="playlist-meta">${p.mood} · ${p.count}</p>
  //     <p class="playlist-updated">Updated ${p.updated}</p>
  //   `;
  //   playlistGrid.appendChild(card);
  // });

  // ---- nav scroll shadow ----
  const nav = document.getElementById('nav');
  window.addEventListener('scroll', () => {
    nav.classList.toggle('is-scrolled', window.scrollY > 12);
  });

  // ---- scroll reveal ----
  const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if(!prefersReduced && 'IntersectionObserver' in window){
    const io = new IntersectionObserver((entries) => {
      entries.forEach(e => { if(e.isIntersecting){ e.target.classList.add('is-visible'); io.unobserve(e.target); } });
    }, { threshold:0.15 });
    document.querySelectorAll('.section.reveal').forEach(el => io.observe(el));
  } else {
    document.querySelectorAll('.section.reveal').forEach(el => el.classList.add('is-visible'));
  }

  // // ---- log a track modal ----
  // const modalOverlay = document.getElementById('modalOverlay');
  // const openBtns = [document.getElementById('openLogBtn'), document.getElementById('openLogBtn2')];
  // const cancelBtn = document.getElementById('cancelLogBtn');
  // const logForm = document.getElementById('logForm');
  // const songTitleInput = document.getElementById('songTitle');
  // const toast = document.getElementById('toast');
  // const toastText = document.getElementById('toastText');
  // let lastFocused = null;

  // function openModal(){
  //   lastFocused = document.activeElement;
  //   modalOverlay.classList.add('is-open');
  //   setTimeout(() => songTitleInput.focus(), 50);
  // }
  // function closeModal(){
  //   modalOverlay.classList.remove('is-open');
  //   logForm.reset();
  //   if(lastFocused) lastFocused.focus();
  // }
  // openBtns.forEach(btn => btn && btn.addEventListener('click', openModal));
  // cancelBtn.addEventListener('click', closeModal);
  // modalOverlay.addEventListener('click', (e) => { if(e.target === modalOverlay) closeModal(); });
  // document.addEventListener('keydown', (e) => { if(e.key === 'Escape' && modalOverlay.classList.contains('is-open')) closeModal(); });

  // logForm.addEventListener('submit', (e) => {
  //   e.preventDefault();
  //   const title = songTitleInput.value.trim() || 'Track';
  //   closeModal();
  //   toastText.textContent = `“${title}” added to your log`;
  //   toast.classList.add('is-visible');
  //   setTimeout(() => toast.classList.remove('is-visible'), 2600);
  // });


const genreMoreBtn = document.getElementById('genreMoreBtn');
if (genreMoreBtn) {
  genreMoreBtn.addEventListener('click', () => {
    const hiddenTiles = document.querySelectorAll('.genre-tile--hidden');
    hiddenTiles.forEach(tile => tile.classList.remove('genre-tile--hidden'));
    genreMoreBtn.style.display = 'none';
  });
}