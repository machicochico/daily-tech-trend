(() => {
  const selectedTags = new Set();
  let tagMode = 'AND';
  let catsCollapsed = false;

  function updateTagActiveView(){
    const box = document.getElementById('tag-active');
    if (!box) return;
    if (selectedTags.size === 0){ box.style.display = 'none'; box.textContent = ''; return; }
    box.style.display = '';
    box.textContent = `tags: ${[...selectedTags].join(', ')} (${tagMode})`;
  }

  function toggleTag(tg){
    selectedTags.has(tg) ? selectedTags.delete(tg) : selectedTags.add(tg);
    document.querySelectorAll(`[data-tag-btn="${tg}"]`).forEach(b => b.classList.toggle('active', selectedTags.has(tg)));
    updateTagActiveView();
    applyFilter();
  }

  function clearTagFilter(){
    selectedTags.clear();
    document.querySelectorAll('[data-tag-btn]').forEach(b => b.classList.remove('active'));
    updateTagActiveView();
    applyFilter();
  }

  function applyFilter(){
    const q = (document.getElementById('q')?.value || '').toLowerCase();
    const rows = document.querySelectorAll('.category-body .topic-row, .top-zone .topic-row');
    let hit = 0;

    rows.forEach(el => {
      const title = (el.dataset.title || '').toLowerCase();
      const summary = (el.dataset.summary || '').toLowerCase();
      const tags = (el.dataset.tags || '');
      const hitQ = !q || title.includes(q) || summary.includes(q);
      const itemTags = tags.split(',').map(s => s.trim()).filter(Boolean);
      const sel = [...selectedTags];
      const hitTag = sel.length === 0 || (tagMode === 'AND' ? sel.every(t => itemTags.includes(t)) : sel.some(t => itemTags.includes(t)));
      const show = hitQ && hitTag;
      el.style.display = show ? '' : 'none';
      if (show) hit++;
    });

    const box = document.getElementById('filter-count');
    if (box){
      const isFiltering = q || selectedTags.size > 0;
      if (isFiltering) {
        box.textContent = document.body.dataset.filterTotal === '1' ? `該当: ${hit}件 / 全${rows.length}件` : `該当: ${hit}件`;
        box.style.display = '';
      } else box.style.display = 'none';
    }

    const hint = document.getElementById('filter-hint');
    if (hint){
      if ((q || selectedTags.size > 0) && hit === 0) {
        hint.innerHTML = '該当なし。<strong>条件を緩めてください：</strong> 検索語を短くする／別表現にする・フィルタをすべてリセットする';
        hint.style.display = '';
      } else hint.style.display = 'none';
    }
  }

  function toggleCat(id){ const sec = document.getElementById('cat-' + id); if (sec) sec.classList.toggle('collapsed'); }
  function toggleAllCats(){ catsCollapsed = !catsCollapsed; document.querySelectorAll('.category-section').forEach(sec => sec.classList.toggle('collapsed', catsCollapsed)); }
  function parseDateValue(v){ const t = Date.parse(String(v || '').replace(' ', 'T')); return Number.isNaN(t) ? 0 : t; }

  function applySort(){
    const key = document.getElementById('sortKey')?.value || 'date';
    const dir = document.getElementById('sortDir')?.value || 'desc';
    const sign = dir === 'asc' ? 1 : -1;
    const lists = [...document.querySelectorAll('ol.top-list'), ...document.querySelectorAll('.category-body > ul'), ...document.querySelectorAll('.topbox > ul')];
    for (const list of lists){
      const items = [...list.querySelectorAll(':scope > li.topic-row')];
      items.sort((a,b) => {
        const av = key === 'importance' ? (parseInt(a.dataset.imp || '0', 10) || 0) : parseDateValue(a.dataset.date);
        const bv = key === 'importance' ? (parseInt(b.dataset.imp || '0', 10) || 0) : parseDateValue(b.dataset.date);
        if (av !== bv) return (av - bv) * sign;
        return (a.dataset.title || '').localeCompare(b.dataset.title || '');
      });
      items.forEach(li => list.appendChild(li));
    }
    try { localStorage.setItem('sortKey', key); localStorage.setItem('sortDir', dir); } catch (_) {}
  }

  function initSortUI(){
    try {
      const k = localStorage.getItem('sortKey');
      const d = localStorage.getItem('sortDir');
      if (k && document.getElementById('sortKey')) document.getElementById('sortKey').value = k;
      if (d && document.getElementById('sortDir')) document.getElementById('sortDir').value = d;
    } catch (_) {}
    applySort();
  }

  function openSectionFor(el){ const sec = el.closest('.category-section'); if (sec) sec.classList.remove('collapsed'); }
  function ensureVisible(el){ if (el.style.display === 'none') el.style.display = ''; }
  function scrollToHash(prefix, hash){
    if (!hash || !hash.startsWith(`#${prefix}-`)) return false;
    const el = document.querySelector(hash);
    if (!el) return false;
    openSectionFor(el); ensureVisible(el);
    const det = el.querySelector('details.insight'); if (det && !det.open) det.open = true;
    requestAnimationFrame(() => el.scrollIntoView({ behavior: 'smooth', block: 'start' }));
    return true;
  }

  function bindHashNavigation(prefix){
    document.addEventListener('click', e => {
      const a = e.target.closest(`a[href^="#${prefix}-"]`);
      if (!a) return;
      const hash = a.getAttribute('href');
      if (scrollToHash(prefix, hash)) { e.preventDefault(); history.replaceState(null, '', hash); }
    });
    window.addEventListener('load', () => { if (location.hash) scrollToHash(prefix, location.hash); });
  }

  function setupCommon(pagePrefix){
    document.getElementById('q')?.addEventListener('input', applyFilter);
    document.getElementById('tagModeOr')?.addEventListener('change', e => { tagMode = e.target.checked ? 'OR' : 'AND'; updateTagActiveView(); applyFilter(); });
    document.getElementById('tagMore')?.addEventListener('click', () => {
      const bar = document.getElementById('tagBar'); if (!bar) return;
      bar.classList.toggle('collapsed');
      const more = document.getElementById('tagMore'); if (more) more.textContent = bar.classList.contains('collapsed') ? '＋ もっと見る' : '− 閉じる';
    });
    initSortUI();
    bindHashNavigation(pagePrefix);
  }

  window.toggleTag = toggleTag;
  window.clearTagFilter = clearTagFilter;
  window.applyFilter = applyFilter;
  window.toggleCat = toggleCat;
  window.toggleAllCats = toggleAllCats;
  window.applySort = applySort;
  window.DTTCommon = { setupCommon };
})();
