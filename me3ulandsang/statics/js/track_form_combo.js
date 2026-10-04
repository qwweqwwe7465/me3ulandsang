// Searchable artist / album picker.
// Reads the full lists from json_script tags (id="artist-data", id="album-data")
// rendered by the server, then does the filtering client-side.
//
// When you swap this for the real "hybrid" search later, all you have to do is
// replace loadDataset() with a fetch() call to your JSON search endpoint -
// everything else (rendering, selection, chips) stays the same.

(function () {
  function loadDataset(elementId) {
    var el = document.getElementById(elementId);
    if (!el) return [];
    try {
      return JSON.parse(el.textContent);
    } catch (e) {
      return [];
    }
  }

  window.datasets = {
    artist: loadDataset('artist-data'),
    featured_artist: loadDataset('artist-data'),
    album: loadDataset('album-data'),
  };
  var datasets = window.datasets;

  function filterItems(items, query, excludeIds) {
    var q = query.trim().toLowerCase();
    return items
      .filter(function (item) {
        if (excludeIds && excludeIds.indexOf(item.id) !== -1) return false;
        return !q || item.name.toLowerCase().indexOf(q) !== -1;
      })
      .slice(0, 20);
  }

  function initSingleCombo(root) {
    var name = root.dataset.combo;
    var input = root.querySelector('.combo__input');
    var hidden = root.querySelector('.combo__value');
    var panel = root.querySelector('.combo__panel');
    var items = datasets[name] || [];

    var initialId = root.dataset.initial;
    if (initialId) {
      var match = items.find(function (item) { return String(item.id) === String(initialId); });
      if (match) input.value = match.name;
    }

    function renderPanel(list) {
      panel.innerHTML = '';
      if (list.length === 0) {
        var empty = document.createElement('div');
        empty.className = 'combo__empty';
        empty.textContent = 'No matches.';
        panel.appendChild(empty);
      } else {
        list.forEach(function (item) {
          var opt = document.createElement('button');
          opt.type = 'button';
          opt.className = 'combo__option';
          opt.textContent = item.name;
          opt.addEventListener('click', function () {
            input.value = item.name;
            hidden.value = item.id;
            closePanel();
          });
          panel.appendChild(opt);
        });
      }
      panel.hidden = false;
    }

    function closePanel() {
      panel.hidden = true;
    }

    input.addEventListener('focus', function () {
      renderPanel(filterItems(items, input.value));
    });
    input.addEventListener('input', function () {
      hidden.value = '';
      renderPanel(filterItems(items, input.value));
    });
    document.addEventListener('click', function (e) {
      if (!root.contains(e.target)) closePanel();
    });
  }

  function initMultiCombo(root) {
    var name = root.dataset.combo;
    var input = root.querySelector('.combo__input');
    var panel = root.querySelector('.combo__panel');
    var chipsWrap = root.querySelector('.combo__chips');
    var items = datasets[name] || [];
    var selected = [];

    var initialIds = (root.dataset.initial || '')
      .split(',')
      .map(function (s) { return s.trim(); })
      .filter(Boolean);
    if (initialIds.length) {
      selected = items.filter(function (item) { return initialIds.indexOf(String(item.id)) !== -1; });
    }

    function renderChips() {
      chipsWrap.innerHTML = '';
      selected.forEach(function (item) {
        var chip = document.createElement('span');
        chip.className = 'combo__chip';
        chip.textContent = item.name;

        var remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'combo__chip-remove';
        remove.setAttribute('aria-label', 'Remove ' + item.name);
        remove.textContent = 'x';
        remove.addEventListener('click', function () {
          selected = selected.filter(function (s) { return s.id !== item.id; });
          renderChips();
        });

        var hidden = document.createElement('input');
        hidden.type = 'hidden';
        hidden.name = name;
        hidden.value = item.id;

        chip.appendChild(remove);
        chipsWrap.appendChild(chip);
        chipsWrap.appendChild(hidden);
      });
    }

    function renderPanel(list) {
      panel.innerHTML = '';
      if (list.length === 0) {
        var empty = document.createElement('div');
        empty.className = 'combo__empty';
        empty.textContent = 'No matches.';
        panel.appendChild(empty);
      } else {
        list.forEach(function (item) {
          var opt = document.createElement('button');
          opt.type = 'button';
          opt.className = 'combo__option';
          opt.textContent = item.name;
          opt.addEventListener('click', function () {
            selected.push(item);
            renderChips();
            input.value = '';
            renderPanel(filterItems(items, '', selected.map(function (s) { return s.id; })));
          });
          panel.appendChild(opt);
        });
      }
      panel.hidden = false;
    }

    function closePanel() {
      panel.hidden = true;
    }

    input.addEventListener('focus', function () {
      renderPanel(filterItems(items, input.value, selected.map(function (s) { return s.id; })));
    });
    input.addEventListener('input', function () {
      renderPanel(filterItems(items, input.value, selected.map(function (s) { return s.id; })));
    });
    document.addEventListener('click', function (e) {
      if (!root.contains(e.target)) closePanel();
    });

    renderChips();
  }

  document.querySelectorAll('.combo').forEach(function (root) {
    if (root.dataset.multi === 'true') {
      initMultiCombo(root);
    } else {
      initSingleCombo(root);
    }
  });
})();



const zone = document.getElementById('mp3-dropzone');
const input = document.getElementById('mp3-input');
const fileLabel = document.getElementById('mp3-filename');
const extractBtn = document.getElementById('extract-btn');

function setFile(file){
  if(!file || !file.name.toLowerCase().endsWith('.mp3')) return;

  fileLabel.textContent = file.name;
  fileLabel.hidden = false;
  zone.classList.add('has-file');
  extractBtn.disabled = false;

  // for drag-and-drop, manually assign the file to the input
  const dt = new DataTransfer();
  dt.items.add(file);
  input.files = dt.files;

  // also carry the same file into the actual "audio_file" upload field,
  // so the user doesn't have to pick the mp3 twice
  const audioFileInput = document.getElementById('id_audio_file');
  if (audioFileInput) {
    const dt2 = new DataTransfer();
    dt2.items.add(file);
    audioFileInput.files = dt2.files;
  }
}

['dragenter','dragover'].forEach(ev =>
  zone.addEventListener(ev, e => { e.preventDefault(); zone.classList.add('is-dragover'); }));
['dragleave','drop'].forEach(ev =>
  zone.addEventListener(ev, e => { e.preventDefault(); zone.classList.remove('is-dragover'); }));

zone.addEventListener('drop', e => setFile(e.dataTransfer.files[0]));
input.addEventListener('change', () => setFile(input.files[0]));







extractBtn.addEventListener('click', async () => {
  if (!input.files.length) return;

  const formData = new FormData();
  formData.append('audio_file', input.files[0]);

  extractBtn.disabled = true;
  const originalText = extractBtn.textContent;
  extractBtn.textContent = 'Extracting…';

  try {
    const response = await fetch('/extract-metadata/', {
      method: 'POST',
      headers: {
        'X-CSRFToken': getCookie('csrftoken'),
      },
      body: formData,
    });

    const data = await response.json();

    if (data.error) {
      console.error('Extraction error:', data.error);
      return;
    }

    // plain text fields
    if (data.title) document.getElementById('id_title').value = data.title;
    if (data.release_date) document.getElementById('id_release_date').value = data.release_date;
    if (data.lyrics) document.getElementById('id_lyrics').value = data.lyrics;
    document.getElementById('id_has_lyrics').checked = !!data.has_lyrics;
    if (data.track_number) document.getElementById('id_album_order').value = data.track_number;

    // combo fields: try to find a matching artist/album already in the database
    if (data.artist) fillCombo('artist', data.artist);
    if (data.album) fillCombo('album', data.album);

    // embedded cover art comes back as a data URL - turn it into a File
    // and assign it to the cover file input so it gets uploaded on submit
    if (data.cover) {
      const coverInput = document.getElementById('id_cover');
      const coverFile = await dataUrlToFile(data.cover, data.cover_filename || 'cover.jpg');
      const dt = new DataTransfer();
      dt.items.add(coverFile);
      coverInput.files = dt.files;
    }

  } catch (err) {
    console.error('Extraction failed:', err);
  } finally {
    extractBtn.disabled = false;
    extractBtn.textContent = originalText;
  }
});

async function dataUrlToFile(dataUrl, filename) {
  const res = await fetch(dataUrl);
  const blob = await res.blob();
  return new File([blob], filename, { type: blob.type });
}

function fillCombo(comboName, extractedName) {
  const root = document.querySelector('.combo[data-combo="' + comboName + '"]');
  if (!root) return;

  const visibleInput = root.querySelector('.combo__input');
  const hiddenInput = root.querySelector('.combo__value');
  const items = datasets[comboName] || [];

  // try to find an exact (case-insensitive) match already in the database
  const match = items.find(item => item.name.toLowerCase() === extractedName.toLowerCase());

  if (match) {
    visibleInput.value = match.name;
    hiddenInput.value = match.id;
  } else {
    // no match in the database yet — just show the extracted name as text,
    // the user will need to add this artist/album first
    visibleInput.value = extractedName;
    hiddenInput.value = '';
  }
}

function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop().split(';').shift();
}
