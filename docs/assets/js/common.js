(() => {
  const selectedTags = new Set();
  let tagMode = 'AND';
  let catsCollapsed = false;
  let currentQuery = '';

  function renderStateChips(states){
    return states.map(([label, value]) => `<span class="state-chip"><b>${label}</b>${value}</span>`).join('');
  }

  function updateTagActiveView(){
    const box = document.getElementById('tag-active');
    if (!box) return;
    const states = [];
    if (currentQuery) states.push(['検索', `「${currentQuery}」`]);
    if (selectedTags.size > 0) states.push(['タグ', [...selectedTags].join(', ')]);
    if (selectedTags.size > 1) states.push(['モード', tagMode]);
    if (states.length === 0){ box.style.display = 'none'; box.textContent = ''; return; }
    box.style.display = '';
    box.innerHTML = renderStateChips(states);
  }

  function toggleTag(tg){
    selectedTags.has(tg) ? selectedTags.delete(tg) : selectedTags.add(tg);
    document.querySelectorAll(`[data-tag-btn="${tg}"]`).forEach(b => b.classList.toggle('active', selectedTags.has(tg)));
    syncTagMoreLabel();
    updateTagActiveView();
    applyFilter();
  }

  function clearTagFilter(){
    selectedTags.clear();
    document.querySelectorAll('[data-tag-btn]').forEach(b => b.classList.remove('active'));
    syncTagMoreLabel();
    updateTagActiveView();
    applyFilter();
  }

  function applyFilter(){
    const q = (document.getElementById('q')?.value || '').toLowerCase();
    currentQuery = q.trim();
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
      const byQuery = !!currentQuery;
      const byTag = selectedTags.size > 0;
      const isFiltering = byQuery || byTag;
      if (isFiltering) {
        const mode = byQuery && byTag ? '（検索＋タグ）' : byQuery ? '（検索）' : '（タグ）';
        box.textContent = `該当 ${hit} / 全 ${rows.length}${mode}`;
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
    updateTagActiveView();
  }

  function syncStickyOffsets(){
    const summary = document.querySelector('.summary-card');
    const category = document.querySelector('.category-header');
    const root = document.documentElement;
    if (summary) root.style.setProperty('--mobile-summary-height', `${Math.ceil(summary.getBoundingClientRect().height)}px`);
    if (category) root.style.setProperty('--mobile-category-height', `${Math.ceil(category.getBoundingClientRect().height)}px`);
  }

  function syncToggleAllCatsLabel(){
    const label = catsCollapsed ? 'すべて開く' : 'すべて閉じる';
    document.querySelectorAll('[data-toggle-all-cats]').forEach(btn => { btn.textContent = label; });
  }

  function toggleCat(id){ const sec = document.getElementById('cat-' + id); if (sec) sec.classList.toggle('collapsed'); }
  function toggleAllCats(){
    catsCollapsed = !catsCollapsed;
    document.querySelectorAll('.category-section').forEach(sec => sec.classList.toggle('collapsed', catsCollapsed));
    syncToggleAllCatsLabel();
  }
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

  function openTopZoneFor(el){
    const fold = el?.closest('details[data-top-zone-details]');
    if (fold) fold.open = true;
  }

  function collapseTopZonesOnFirstView(){
    const folds = document.querySelectorAll('details[data-top-zone-details]');
    if (!folds.length) return;
    if (location.hash) return;
    let seen = false;
    try { seen = sessionStorage.getItem('dtt-top-zone-seen') === '1'; } catch (_) {}
    if (seen) return;
    folds.forEach(f => { f.open = false; });
    try { sessionStorage.setItem('dtt-top-zone-seen', '1'); } catch (_) {}
  }

  function enableMobileTopZoneAccordion(){
    const folds = [...document.querySelectorAll('details[data-top-zone-details]')];
    if (!folds.length) return;
    folds.forEach(fold => {
      fold.addEventListener('toggle', () => {
        if (!fold.open || window.innerWidth > 640) return;
        folds.forEach(other => {
          if (other !== fold) other.open = false;
        });
      });
    });
  }

  function revealHashTarget(prefix, hash){
    if (!hash) return;
    if (scrollToHash(prefix, hash)) {
      const topicEl = document.querySelector(hash);
      if (topicEl) openTopZoneFor(topicEl);
      return;
    }
    if (hash.startsWith('#cat-')) {
      const sec = document.querySelector(hash);
      if (sec) {
        sec.classList.remove('collapsed');
        requestAnimationFrame(() => sec.scrollIntoView({ behavior: 'smooth', block: 'start' }));
      }
    }
  }

  function bindHashNavigation(prefix){
    document.addEventListener('click', e => {
      const a = e.target.closest(`a[href^="#${prefix}-"], a[href^="#cat-"]`);
      if (!a) return;
      const hash = a.getAttribute('href');
      revealHashTarget(prefix, hash);
      e.preventDefault();
      history.replaceState(null, '', hash);
    });
    window.addEventListener('load', () => { if (location.hash) revealHashTarget(prefix, location.hash); });
  }

  function syncTagMoreLabel(){
    const bar = document.getElementById('tagBar');
    const more = document.getElementById('tagMore');
    if (!bar || !more) return;
    more.textContent = bar.classList.contains('collapsed') ? '＋ よく使うタグ以外も表示' : '− タグ一覧をたたむ';
  }


  function setupCategoryToc(){
    const toc = document.querySelector('.category-toc');
    if (!toc) return;

    const links = [...toc.querySelectorAll('[data-category-link]')];
    const select = toc.querySelector('#category-toc-select');
    const sections = links
      .map(link => document.getElementById(`cat-${link.dataset.categoryLink}`))
      .filter(Boolean);

    const setActive = (id) => {
      links.forEach(link => {
        const active = link.dataset.categoryLink === id;
        link.classList.toggle('active', active);
      });
      if (select) {
        const nextValue = id ? `#cat-${id}` : '';
        if (select.value !== nextValue) select.value = nextValue;
      }
    };

    if (select) {
      select.addEventListener('change', e => {
        const hash = e.target.value;
        if (!hash) return;
        revealHashTarget('topic', hash);
        history.replaceState(null, '', hash);
      });
    }

    if (!sections.length || !('IntersectionObserver' in window)) {
      const first = links[0]?.dataset.categoryLink;
      if (first) setActive(first);
      return;
    }

    const observer = new IntersectionObserver(entries => {
      const visible = entries
        .filter(entry => entry.isIntersecting)
        .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
      if (!visible.length) return;
      const id = visible[0].target.id.replace('cat-', '');
      setActive(id);
    }, {
      rootMargin: '-20% 0px -60% 0px',
      threshold: [0.1, 0.25, 0.5],
    });

    sections.forEach(sec => observer.observe(sec));
    const first = links[0]?.dataset.categoryLink;
    if (first) setActive(first);
  }

  function setupCommon(pagePrefix){
    document.getElementById('q')?.addEventListener('input', applyFilter);
    document.getElementById('tagModeOr')?.addEventListener('change', e => { tagMode = e.target.checked ? 'OR' : 'AND'; updateTagActiveView(); applyFilter(); });
    document.getElementById('tagMore')?.addEventListener('click', () => {
      const bar = document.getElementById('tagBar'); if (!bar) return;
      bar.classList.toggle('collapsed');
      syncTagMoreLabel();
      syncStickyOffsets();
    });
    window.addEventListener('resize', syncStickyOffsets);
    window.addEventListener('load', syncStickyOffsets);
    initSortUI();
    collapseTopZonesOnFirstView();
    enableMobileTopZoneAccordion();
    bindHashNavigation(pagePrefix);
    setupCategoryToc();
    syncToggleAllCatsLabel();
    syncTagMoreLabel();
    updateTagActiveView();
    applyFilter();
  }

  window.toggleTag = toggleTag;
  window.clearTagFilter = clearTagFilter;
  window.applyFilter = applyFilter;
  window.toggleCat = toggleCat;
  window.toggleAllCats = toggleAllCats;
  window.applySort = applySort;
  window.DTTCommon = { setupCommon };
})();
