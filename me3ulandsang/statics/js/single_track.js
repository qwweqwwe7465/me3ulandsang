  // ---- tracklist for the current album, current track highlighted ----
  try {
    const tracklistEl = document.getElementById('tracklist');
    if (tracklistEl && typeof tracklist !== 'undefined' && Array.isArray(tracklist)) {
      tracklist.forEach(t => {
        const row = document.createElement('div');
        row.className = 'tracklist-row' + (t.current ? ' is-current' : '');
        row.innerHTML = `
          <span class="tracklist-num">${String(t.num).padStart(2,'0')}</span>
          <span class="tracklist-title">${t.title}</span>
          ${t.current ? '<span class="tracklist-tag">Now</span>' : ''}
        `;
        tracklistEl.appendChild(row);
      });
    }
  } catch (e) {
    console.error('Tracklist error:', e);
  }


  function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
  }

  // ---- like button ----
  try {
    const likeBtn = document.getElementById('likeBtn');
    const likeCount = document.getElementById('likeCount');
    if (likeBtn && likeCount) {
      const trackId = likeBtn.dataset.trackId;
      likeBtn.addEventListener('click', () => {
        likeBtn.disabled = true;
        fetch(`/track/${trackId}/like`, {
          method: 'POST',
          headers: {
            'X-CSRFToken': getCookie('csrftoken'),
          },
        })
          .then((res) => res.json())
          .then((data) => {
            likeBtn.classList.toggle('is-liked', data.liked);
            likeCount.textContent = data.likes;
          })
          .catch((err) => console.error('Like request failed:', err))
          .finally(() => {
            likeBtn.disabled = false;
          });
      });
    }
  } catch (e) {
    console.error('Like button error:', e);
  }


  // ---- add to playlist toast ----
  try {
    const addPlaylistBtn = document.getElementById('addPlaylistBtn');
    const toast = document.getElementById('toast');
    const toastText = document.getElementById('toastText');
    if (addPlaylistBtn && toast && toastText) {
      addPlaylistBtn.addEventListener('click', () => {
        toastText.textContent = '"Paper Moths" added to your playlist';
        toast.classList.add('is-visible');
        setTimeout(() => toast.classList.remove('is-visible'), 2400);
      });
    }
  } catch (e) {
    console.error('Toast error:', e);
  }


  // ---- nav scroll shadow ----
  try {
    const nav = document.getElementById('nav');
    if (nav) {
      window.addEventListener('scroll', () => nav.classList.toggle('is-scrolled', window.scrollY > 12));
    }
  } catch (e) {
    console.error('Nav scroll error:', e);
  }


  // ---- audio player ----
  try {
    const audio = document.getElementById('trackAudio');
    const playBtn = document.getElementById('playBtn');
    const progressBar = document.getElementById('progressBar');
    const progressFill = document.getElementById('progressFill');
    const currentTimeEl = document.getElementById('currentTime');
    const durationTimeEl = document.getElementById('durationTime');

    if (audio && playBtn && progressBar && progressFill && currentTimeEl && durationTimeEl) {
      const formatTime = (secs) => {
        if (!isFinite(secs)) return '0:00';
        const m = Math.floor(secs / 60);
        const s = Math.floor(secs % 60).toString().padStart(2, '0');
        return `${m}:${s}`;
      };

      playBtn.addEventListener('click', () => {
        if (audio.paused) {
          audio.play().catch(err => console.warn('Playback failed:', err));
          playBtn.classList.add('is-playing');
        } else {
          audio.pause();
          playBtn.classList.remove('is-playing');
        }
      });

      audio.addEventListener('loadedmetadata', () => {
        durationTimeEl.textContent = formatTime(audio.duration);
      });

      audio.addEventListener('timeupdate', () => {
        const pct = (audio.currentTime / audio.duration) * 100 || 0;
        progressFill.style.width = pct + '%';
        currentTimeEl.textContent = formatTime(audio.currentTime);
      });

      audio.addEventListener('ended', () => {
        playBtn.classList.remove('is-playing');
        progressFill.style.width = '0%';
      });

      progressBar.addEventListener('click', (e) => {
        const rect = progressBar.getBoundingClientRect();
        const ratio = (e.clientX - rect.left) / rect.width;
        if (isFinite(audio.duration)) {
          audio.currentTime = ratio * audio.duration;
        }
      });
    }
  } catch (e) {
    console.error('Player error:', e);
  }
