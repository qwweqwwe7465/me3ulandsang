function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  return parts.length === 2 ? parts.pop().split(';').shift() : '';
}

(() => {
  const rows = [...document.querySelectorAll('#playlistTracklist .tracklist-row[data-audio-url]')];
  if (rows.length) {
    const audio = new Audio();
    let currentIndex = -1;

    const updateButtons = () => rows.forEach((row, index) => {
      const button = row.querySelector('.track-play');
      if (button) button.classList.toggle('is-playing', index === currentIndex && !audio.paused);
    });

    const playAt = (index) => {
      if (index < 0 || index >= rows.length || !rows[index].dataset.audioUrl) return;
      currentIndex = index;
      audio.src = rows[index].dataset.audioUrl;
      audio.play().catch(() => updateButtons());
      updateButtons();
    };

    rows.forEach((row, index) => {
      const button = row.querySelector('.track-play');
      if (button && !button.disabled) {
        button.addEventListener('click', () => {
          if (currentIndex === index && !audio.paused) audio.pause();
          else if (currentIndex === index) audio.play();
          else playAt(index);
          updateButtons();
        });
      }
    });

    audio.addEventListener('ended', () => {
      let next = currentIndex + 1;
      while (next < rows.length && !rows[next].dataset.audioUrl) next += 1;
      if (next < rows.length) playAt(next);
      else { currentIndex = -1; updateButtons(); }
    });
    audio.addEventListener('pause', updateButtons);
    audio.addEventListener('play', updateButtons);
  }

  const likeBtn = document.getElementById('likeBtn');
  const likeCount = document.getElementById('likeCount');
  if (likeBtn && likeCount) {
    likeBtn.addEventListener('click', () => {
      likeBtn.disabled = true;
      fetch(`/playlist/${likeBtn.dataset.trackId}/like`, {
        method: 'POST',
        headers: { 'X-CSRFToken': getCookie('csrftoken') },
      })
        .then((response) => response.json())
        .then((data) => {
          likeBtn.classList.toggle('is-liked', data.liked);
          likeCount.textContent = data.likes;
        })
        .catch((error) => console.error('Like request failed:', error))
        .finally(() => { likeBtn.disabled = false; });
    });
  }
})();
