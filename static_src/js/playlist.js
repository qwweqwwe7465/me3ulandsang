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
        fetch(`/playlist/${trackId}/like`, { 
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
