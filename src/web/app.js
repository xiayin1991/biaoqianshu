const state = {
  data: null,
  currentPage: 1,
  currentQuestion: 1,
  viewMode: 'page',
  framing: false,
  selection: null,
  treeScope: 'whole',
  metricMode: 'count',
  pendingCrop: null,
  questionUpdating: false,
  tagSuggestionIndex: -1,
  tagSuggestionTags: [],
};

const $ = (id) => document.getElementById(id);

function showToast(message) {
  const el = $('toast');
  el.textContent = message;
  el.classList.add('show');
  window.clearTimeout(showToast._t);
  showToast._t = window.setTimeout(() => el.classList.remove('show'), 2200);
}

async function apiGet(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}

async function apiPost(url, payload) {
  const r = await fetch(url, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload || {})
  });
  const data = await r.json();
  if (!r.ok || data.ok === false) throw new Error(data.error || '请求失败');
  return data;
}

async function refreshState() {
  const data = await apiGet('/api/state');
  state.data = data;
  if (data.has_project) {
    renderTagTotals();
    if (state.currentPage > data.pages.length) state.currentPage = Math.max(1, data.pages.length);
    if (state.currentQuestion > data.questions.length) state.currentQuestion = Math.max(1, data.questions.length);
  } else {
    state.currentPage = 1;
    state.currentQuestion = 1;
  }
  renderAll();
  applyLayout();
}

function projectFolderName(data) {
  const root = String(data?.project?.root || '').replace(/[\\/]+$/, '');
  const folder = root.split(/[\\/]/).filter(Boolean).pop();
  return folder || data?.project?.name || '未打开项目';
}

function renderProjectName() {
  const label = $('projectName');
  if (!state.data?.has_project) {
    label.textContent = '未打开项目';
    label.title = '';
    return;
  }
  const folder = projectFolderName(state.data);
  label.textContent = folder;
  label.title = folder;
}

function currentPage() {
  if (!state.data?.has_project) return null;
  return state.data.pages[state.currentPage - 1] || null;
}

function currentQuestion() {
  if (!state.data?.has_project) return null;
  return state.data.questions[state.currentQuestion - 1] || null;
}

function renderAll() {
  renderNav();
  renderPreview();
  renderTags();
  renderModeSwitches();
  renderTagTotals();
  renderTree();
}

function renderModeSwitches() {
  const scopeSwitch = $('treeScopeSwitch');
  const metricSwitch = $('metricModeSwitch');
  if (!scopeSwitch || !metricSwitch) return;
  scopeSwitch.dataset.value = state.treeScope;
  metricSwitch.dataset.value = state.metricMode;
  scopeSwitch.querySelectorAll('.mode-option').forEach(button => {
    button.classList.toggle('active', button.dataset.value === state.treeScope);
  });
  metricSwitch.querySelectorAll('.mode-option').forEach(button => {
    button.classList.toggle('active', button.dataset.value === state.metricMode);
  });
}

function setTreeScope(value) {
  state.treeScope = value === 'single' ? 'single' : 'whole';
  renderModeSwitches();
  renderTree();
}

function setMetricMode(value) {
  state.metricMode = value === 'score' ? 'score' : 'count';
  renderModeSwitches();
  renderTree();
}

function renderTagTotals() {
  const has = !!state.data?.has_project;
  const assignmentTotal = has ? (state.data.tag_assignment_total ?? state.data.tag_total ?? 0) : 0;
  const uniqueTotal = has ? (state.data.tag_unique_total ?? 0) : 0;
  $('tagAssignmentTotal').textContent = String(assignmentTotal);
  $('tagUniqueTotal').textContent = String(uniqueTotal);
}

function knownTagCounts() {
  const counts = new Map();
  (state.data?.questions || []).forEach(question => {
    (question.tags || []).forEach(raw => {
      const tag = String(raw || '').trim();
      if (tag) counts.set(tag, (counts.get(tag) || 0) + 1);
    });
  });
  return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'zh-Hans-CN'));
}

function normalizeTagSearchText(value) {
  return String(value || '').toLowerCase().replace(/[\s/\\|]+/g, '');
}

function tagMatchScore(rawTag, rawQuery) {
  const tag = normalizeTagSearchText(rawTag);
  const query = normalizeTagSearchText(rawQuery);
  if (!tag || !query) return -1;
  if (tag === query) return 1000;
  if (tag.startsWith(query)) return 800 - tag.length * 0.01;
  const substringIndex = tag.indexOf(query);
  if (substringIndex >= 0) return 600 - substringIndex * 0.1 - tag.length * 0.01;

  // Characters may appear in order, but not necessarily as one contiguous phrase.
  let cursor = -1;
  let ordered = true;
  for (const char of query) {
    const at = tag.indexOf(char, cursor + 1);
    if (at < 0) { ordered = false; break; }
    cursor = at;
  }
  if (ordered) return 400 - tag.length * 0.01;

  // Final fallback: all characters exist in any order, with multiset counting.
  const counts = new Map();
  for (const char of tag) counts.set(char, (counts.get(char) || 0) + 1);
  for (const char of query) {
    const remaining = counts.get(char) || 0;
    if (remaining <= 0) return -1;
    counts.set(char, remaining - 1);
  }
  return 200 - tag.length * 0.01;
}

function hideTagSuggestions() {
  const box = $('tagSuggestions');
  if (!box) return;
  box.classList.add('hidden');
  box.innerHTML = '';
  state.tagSuggestionIndex = -1;
  state.tagSuggestionTags = [];
}

function renderTagSuggestions() {
  const input = $('tagInput');
  const box = $('tagSuggestions');
  const query = input.value.trim().toLowerCase();
  if (!query) {
    hideTagSuggestions();
    return;
  }
  const matches = knownTagCounts()
    .map(([tag, count]) => ({tag, count, score: tagMatchScore(tag, query)}))
    .filter(item => item.score >= 0)
    .sort((a, b) => b.score - a.score || b.count - a.count || a.tag.localeCompare(b.tag, 'zh-Hans-CN'))
    .slice(0, 50);
  state.tagSuggestionTags = matches.map(item => item.tag);
  state.tagSuggestionIndex = matches.length ? 0 : -1;
  box.innerHTML = '';
  matches.forEach(({tag, count}, index) => {
    const row = document.createElement('div');
    row.className = `tag-suggestion${index === 0 ? ' active' : ''}`;
    row.setAttribute('role', 'option');
    row.dataset.index = String(index);
    const label = document.createElement('span');
    label.textContent = tag;
    const counter = document.createElement('span');
    counter.className = 'tag-suggestion-count';
    counter.textContent = `${count} 题`;
    row.append(label, counter);
    row.addEventListener('mousedown', event => event.preventDefault());
    row.addEventListener('click', () => applyTagSuggestion(index));
    box.appendChild(row);
  });
  box.classList.toggle('hidden', !matches.length);
}

function updateTagSuggestionSelection(delta) {
  if (!state.tagSuggestionTags.length) return;
  const total = state.tagSuggestionTags.length;
  state.tagSuggestionIndex = (state.tagSuggestionIndex + delta + total) % total;
  $('tagSuggestions').querySelectorAll('.tag-suggestion').forEach((row, index) => {
    row.classList.toggle('active', index === state.tagSuggestionIndex);
  });
}

function applyTagSuggestion(index) {
  const tag = state.tagSuggestionTags[index];
  if (!tag) return;
  $('tagInput').value = tag;
  hideTagSuggestions();
  $('tagInput').focus();
}

function handleTagInputKeydown(event) {
  if (event.key === 'ArrowDown' && state.tagSuggestionTags.length) {
    event.preventDefault();
    updateTagSuggestionSelection(1);
    return;
  }
  if (event.key === 'ArrowUp' && state.tagSuggestionTags.length) {
    event.preventDefault();
    updateTagSuggestionSelection(-1);
    return;
  }
  if (event.key === 'Escape') {
    hideTagSuggestions();
    return;
  }
  if (event.key === 'Enter') {
    if (state.tagSuggestionTags.length) {
      event.preventDefault();
      applyTagSuggestion(state.tagSuggestionIndex);
    } else {
      addCurrentTag();
    }
  }
}

function renderNav() {
  renderProjectName();
  const has = !!state.data?.has_project;
  $('totalPages').textContent = has ? String(state.data.pages.length) : '0';
  $('totalQuestions').textContent = has ? String(state.data.questions.length) : '0';
  $('currentPage').value = String(state.currentPage || 1);
  $('currentQuestion').value = String(state.currentQuestion || 1);
}

function setPage(index) {
  if (!state.data?.has_project || !state.data.pages.length) return;
  state.currentPage = Math.max(1, Math.min(state.data.pages.length, Number(index) || 1));
  state.viewMode = 'page';
  state.framing = false;
  clearCropBox();
  renderAll();
}

function setQuestion(index) {
  if (!state.data?.has_project || !state.data.questions.length) {
    showToast('还没有已框题目');
    return;
  }
  state.currentQuestion = Math.max(1, Math.min(state.data.questions.length, Number(index) || 1));
  state.viewMode = 'question';
  const q = currentQuestion();
  if (q && q.page) state.currentPage = Math.max(1, Math.min(state.data.pages.length, q.page));
  state.framing = false;
  clearCropBox();
  renderAll();
}

function renderPreview() {
  const img = $('questionImage');
  const empty = $('imageEmpty');
  const q = currentQuestion();
  const page = currentPage();
  if (!state.data?.has_project || (state.viewMode === 'page' && !page) || (state.viewMode === 'question' && !q)) {
    img.classList.add('hidden');
    empty.style.display = 'grid';
    renderQuestionMeta(null);
    return;
  }
  empty.style.display = 'none';
  img.classList.remove('hidden');
  if (state.viewMode === 'question') {
    img.src = `/api/image?qid=${encodeURIComponent(q.qid)}&v=${Date.now()}`;
    renderQuestionMeta(q);
  } else {
    img.src = `/api/page?index=${state.currentPage - 1}&v=${Date.now()}`;
    renderQuestionMeta(null);
  }
  img.onload = () => {
    const stage = $('imageStage');
    stage.style.width = `${img.clientWidth}px`;
    stage.style.height = `${img.clientHeight}px`;
  };
}

function formatScoreValue(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '';
  return Number.isInteger(number) ? String(number) : String(Number(number.toFixed(2)));
}

function renderQuestionMeta(q) {
  const qidInput = $('questionQidInput');
  const scoreInput = $('questionScoreInput');
  const editable = !!q && state.viewMode === 'question';
  qidInput.disabled = !editable;
  scoreInput.disabled = !editable;

  if (!editable) {
    qidInput.value = '';
    scoreInput.value = '';
    qidInput.dataset.saved = '';
    scoreInput.dataset.saved = '';
    $('questionTagCount').textContent = '本题已打 0 个标签';
    return;
  }

  const savedScore = formatScoreValue(q.score);
  if (document.activeElement !== qidInput || qidInput.dataset.saved !== q.qid) {
    qidInput.value = q.qid;
  }
  if (document.activeElement !== scoreInput || scoreInput.dataset.saved !== savedScore) {
    scoreInput.value = savedScore;
  }
  qidInput.dataset.saved = q.qid;
  scoreInput.dataset.saved = savedScore;
  $('questionTagCount').textContent = `本题已打 ${q.tags?.length || 0} 个标签`;
}

async function commitQuestionMeta(field) {
  const q = currentQuestion();
  if (!q || state.viewMode !== 'question') return;
  if (state.questionUpdating) {
    renderQuestionMeta(q);
    showToast('正在保存，请稍后再试');
    return;
  }

  const qidInput = $('questionQidInput');
  const scoreInput = $('questionScoreInput');
  const savedQid = q.qid;
  const savedScore = formatScoreValue(q.score);
  const payload = {qid: savedQid};

  if (field === 'qid') {
    const nextQid = qidInput.value.trim().toUpperCase();
    if (nextQid === savedQid) {
      qidInput.value = savedQid;
      return;
    }
    if (!/^P[12]-\d{1,3}$/.test(nextQid)) {
      qidInput.value = savedQid;
      showToast('题号格式错误，已回退；请使用 P2-17 或 P1-03');
      return;
    }
    payload.question_number = nextQid;
  } else {
    const rawScore = scoreInput.value.trim();
    const nextScore = Number(rawScore);
    if (!rawScore || !Number.isFinite(nextScore) || nextScore <= 0) {
      scoreInput.value = savedScore;
      showToast('分值必须是大于 0 的数字，已回退');
      return;
    }
    if (nextScore === Number(q.score)) {
      scoreInput.value = savedScore;
      return;
    }
    payload.score = nextScore;
  }

  state.questionUpdating = true;
  qidInput.disabled = true;
  scoreInput.disabled = true;
  try {
    state.data = await apiPost('/api/question/update', payload);
    state.questionUpdating = false;
    renderAll();
  } catch (error) {
    state.questionUpdating = false;
    qidInput.value = savedQid;
    scoreInput.value = savedScore;
    renderQuestionMeta(q);
    showToast(`${error.message}，已回退`);
  }
}

function renderTags() {
  const q = currentQuestion();
  const list = $('tagList');
  list.innerHTML = '';
  if (!q || state.viewMode !== 'question') {
    $('tagCount').textContent = '0 行标签';
    return;
  }
  q.tags.forEach(tag => {
    const row = document.createElement('div');
    row.className = 'tag-row';
    const text = document.createElement('div');
    text.className = 'tag-text';
    text.textContent = tag;
    const del = document.createElement('button');
    del.className = 'delete-tag';
    del.textContent = '✕';
    del.title = '删除这个标签';
    del.addEventListener('click', async () => {
      try {
        state.data = await apiPost('/api/tag/remove', {qid: q.qid, tag});
        renderAll();
      } catch (e) { showToast(e.message); }
    });
    row.append(text, del);
    list.appendChild(row);
  });
  $('tagCount').textContent = `${q.tags.length} 行标签`;
}

function maxDepth(node) {
  if (!node.children || node.children.length === 0) return 0;
  return 1 + Math.max(...node.children.map(maxDepth));
}

function leafCount(node) {
  if (!node.children || node.children.length === 0) return 1;
  return node.children.reduce((sum, child) => sum + leafCount(child), 0);
}

function layoutTreeBottomUp(root, width, height) {
  const maxD = Math.max(1, maxDepth(root));
  const leaves = Math.max(1, leafCount(root));
  const marginX = 70, marginBottom = 80, marginTop = 70;
  const xGap = leaves > 1 ? (width - marginX * 2) / (leaves - 1) : 0;
  const yGap = (height - marginBottom - marginTop) / maxD;
  let cursor = marginX;
  function walk(node, depth) {
    node._y = height - marginBottom - depth * yGap;
    if (!node.children || node.children.length === 0) {
      node._x = cursor;
      cursor += xGap;
    } else {
      node.children.forEach(c => walk(c, depth + 1));
      node._x = node.children.reduce((sum, c) => sum + c._x, 0) / node.children.length;
    }
  }
  walk(root, 0);
}

function buildClientTree(questions, metricMode) {
  const rootLabel = state.treeScope === 'single' && questions?.length === 1
    ? questions[0].qid
    : (state.data?.project?.name || '标签树');
  const root = {label: rootLabel, path: [], indices: [], children: [], count: 0, score: 0, code: '0'};
  for (const q of questions || []) {
    const qScore = Number(q.score || 0);
    for (const tag of q.tags || []) {
      const parts = String(tag).split('/').map(x => x.trim()).filter(Boolean);
      let node = root;
      for (const part of parts) {
        let child = node.children.find(x => x.label === part);
        if (!child) {
          child = {label: part, path: [...node.path, part], indices: [...node.indices, node.children.length + 1], children: [], count: 0, score: 0, code: ''};
          node.children.push(child);
        }
        node = child;
        node.count += 1;
        node.score += qScore;
      }
    }
  }
  root.count = root.children.reduce((sum, child) => sum + Number(child.count || 0), 0);
  root.score = root.children.reduce((sum, child) => sum + Number(child.score || 0), 0);
  return root;
}

function flattenTree(node, out = [], parent = null) {
  const copy = {...node, parent};
  out.push(copy);
  for (const child of node.children || []) flattenTree(child, out, node);
  return out;
}

function autoNodeColor(indices, topCount) {
  const topIndex = Math.max(0, (indices[0] || 1) - 1);
  let hue = (topIndex * 360 / Math.max(1, topCount) + 8) % 360;
  const level = Math.max(0, indices.length - 1);
  if (indices.length > 1) {
    let offset = 0;
    for (let i = 1; i < indices.length; i++) offset += (((indices[i] - 1) % 3) - 1) * 8;
    hue = (hue + offset + 360) % 360;
  }
  const light = Math.max(38, 66 - Math.min(level, 4) * 6);
  const sat = Math.max(54, 76 - Math.min(level, 3) * 5);
  return `hsl(${hue}, ${sat}%, ${light}%)`;
}

function metricValue(node) {
  return state.metricMode === 'score' ? Number(node.score || 0) : Number(node.count || 0);
}

function edgeWidth(value) {
  return Math.max(1.2, Math.min(14, Math.sqrt(Math.max(1, value)) * 2));
}

function nodeRadius(value, isRoot = false) {
  const r = 6 + Math.sqrt(Math.max(1, value)) * 3.4;
  return isRoot ? Math.max(13, Math.min(30, r)) : Math.max(7, Math.min(26, r));
}

function hideTreeTooltip() {
  const tooltip = $('treeTooltip');
  if (!tooltip) return;
  tooltip.classList.add('hidden');
  tooltip.textContent = '';
}

function showTreeTooltip(target, text) {
  const tooltip = $('treeTooltip');
  if (!tooltip || !target) return;
  tooltip.textContent = text;
  tooltip.classList.remove('hidden');
  const targetRect = target.getBoundingClientRect();
  const tooltipRect = tooltip.getBoundingClientRect();
  const pad = 8;
  let left = targetRect.left - tooltipRect.width - 12;
  let top = targetRect.top - tooltipRect.height - 12;
  if (left < pad) left = targetRect.right + 12;
  if (top < pad) top = targetRect.bottom + 12;
  left = Math.max(pad, Math.min(left, window.innerWidth - tooltipRect.width - pad));
  top = Math.max(pad, Math.min(top, window.innerHeight - tooltipRect.height - pad));
  tooltip.style.left = `${Math.round(left)}px`;
  tooltip.style.top = `${Math.round(top)}px`;
}

function renderTree() {
  const svg = $('treeSvg');
  const empty = $('treeEmpty');
  hideTreeTooltip();
  renderTagTotals();
  svg.innerHTML = '';
  const q = currentQuestion();
  if (state.treeScope === 'single' && (state.viewMode !== 'question' || !q)) {
    empty.textContent = '请选择某个单题查看标签树';
    empty.style.display = 'grid';
    return;
  }
  const selected = state.treeScope === 'single' ? [q] : (state.data?.questions || []);
  const distinctTags = new Set();
  selected.forEach(item => (item.tags || []).forEach(tag => distinctTags.add(tag)));
  const root = buildClientTree(selected, state.metricMode);
  if (!root.children.length) {
    empty.textContent = '暂无标签数据';
    empty.style.display = 'grid';
    return;
  }
  empty.style.display = 'none';
  const box = svg.getBoundingClientRect();
  const width = Math.max(700, box.width || 760);
  const height = Math.max(540, box.height || 620);
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  layoutTreeBottomUp(root, width, height);
  const fresh = flattenTree(root);
  const ns = 'http://www.w3.org/2000/svg';
  const topCount = Math.max(1, root.children.length);
  fresh.forEach(n => {
    if (!n.parent) return;
    const line = document.createElementNS(ns, 'line');
    line.setAttribute('x1', n.parent._x); line.setAttribute('y1', n.parent._y);
    line.setAttribute('x2', n._x); line.setAttribute('y2', n._y);
    line.setAttribute('stroke', autoNodeColor(n.indices, topCount));
    line.setAttribute('stroke-width', edgeWidth(metricValue(n)));
    line.setAttribute('stroke-linecap', 'round');
    svg.appendChild(line);
  });
  fresh.forEach(n => {
    const g = document.createElementNS(ns, 'g');
    const value = metricValue(n);
    const radius = nodeRadius(value, !n.parent);
    const circle = document.createElementNS(ns, 'circle');
    circle.setAttribute('cx', n._x); circle.setAttribute('cy', n._y);
    circle.setAttribute('r', radius);
    circle.setAttribute('fill', n.parent ? autoNodeColor(n.indices, topCount) : '#172b45');
    circle.setAttribute('stroke', '#fff'); circle.setAttribute('stroke-width', '3');
    const label = document.createElementNS(ns, 'text');
    label.setAttribute('x', n._x);
    label.setAttribute('y', n.parent ? (n._y - radius - 8) : (n._y + radius + 16));
    label.setAttribute('text-anchor', 'middle');
    label.setAttribute('font-size', n.parent ? '13' : '15');
    label.setAttribute('fill', '#26374d'); label.setAttribute('font-weight', '700');
    label.textContent = `${n.label} (${value})`;
    const tooltipText = n.path.length ? n.path.join(' / ') : n.label;
    g.addEventListener('mouseenter', () => showTreeTooltip(g, tooltipText));
    g.addEventListener('mouseleave', hideTreeTooltip);
    g.append(circle, label);
    svg.appendChild(g);
  });
}
function clearCropBox() {
  state.selection = null;
  const box = $('cropBox');
  const layer = $('cropLayer');
  if (box) { box.classList.remove('show'); box.style.display = 'none'; }
  if (layer) layer.classList.remove('active');
  const btn = $('btnFrame');
  if (btn) btn.classList.remove('active');
}

function startFraming() {
  if (!state.data?.has_project || !state.data.pages.length) {
    showToast('请先导入试卷');
    return;
  }
  if (state.viewMode !== 'page') setPage(state.currentPage);
  state.framing = true;
  clearCropBox();
  state.framing = true;
  $('cropLayer').classList.add('active');
  $('btnFrame').classList.add('active');
  showToast('请在试卷上拖拽框选题目，然后点击右下角“确定”');
}

function cropPointFromEvent(e) {
  const img = $('questionImage');
  const rect = img.getBoundingClientRect();
  return {x: Math.max(0, Math.min(rect.width, e.clientX - rect.left)), y: Math.max(0, Math.min(rect.height, e.clientY - rect.top)), w: rect.width, h: rect.height};
}

async function confirmCrop() {
  const s = state.selection;
  const img = $('questionImage');
  if (!s || !img.naturalWidth || !img.naturalHeight) return;
  const imgRect = img.getBoundingClientRect();
  const w = s.w || imgRect.width;
  const h = s.h || imgRect.height;
  const xScale = img.naturalWidth / w;
  const yScale = img.naturalHeight / h;
  state.pendingCrop = {
    page_index: state.currentPage - 1,
    bbox: [Math.min(s.x1, s.x2) * xScale, Math.min(s.y1, s.y2) * yScale, Math.max(s.x1, s.x2) * xScale, Math.max(s.y1, s.y2) * yScale]
  };
  $('cropQnum').value = '';
  $('cropScore').value = '';
  $('cropModal').classList.remove('hidden');
  window.setTimeout(() => $('cropQnum').focus(), 50);
}

function hideCropModal() {
  $('cropModal').classList.add('hidden');
  state.pendingCrop = null;
}

async function doCropConfirm() {
  const qnum = $('cropQnum').value.trim().toUpperCase();
  const score = Number($('cropScore').value);
  if (!/^P[12]-\d{1,3}$/.test(qnum)) {
    showToast('题号格式错误，请使用 P2-17 或 P1-03');
    return;
  }
  if (!Number.isFinite(score) || score <= 0) {
    showToast('请输入大于 0 的分值');
    return;
  }
  if (!state.pendingCrop) return;
  try {
    state.data = await apiPost('/api/question/crop', {...state.pendingCrop, question_number: qnum, score});
    state.currentQuestion = state.data.questions.length;
    state.viewMode = 'question';
    state.treeScope = 'single';
    hideCropModal();
    clearCropBox();
    state.framing = false;
    renderAll();
    showToast('已框题，可以开始打标');
  } catch (e) {
    showToast(e.message);
  }
}
async function addCurrentTag() {
  const q = currentQuestion();
  const raw = $('tagInput').value.trim();
  if (!q || state.viewMode !== 'question') { showToast('请先框题并进入题目打标'); return; }
  if (!raw) return;
  try {
    state.data = await apiPost('/api/tag/add', {qid: q.qid, tag: raw});
    $('tagInput').value = '';
    hideTagSuggestions();
    renderAll();
  } catch (e) { showToast(e.message); }
}

function bridgeAvailable() { return !!(window.pywebview && window.pywebview.api); }

async function callBridge(fn, okMessage) {
  if (!bridgeAvailable()) { showToast('浏览器模式不支持文件对话框，请从标签树 EXE 启动'); return; }
  const result = await window.pywebview.api[fn]();
  if (result?.state) {
    state.data = result.state;
    state.currentPage = 1;
    state.currentQuestion = result.state.questions?.length ? 1 : 0;
    state.viewMode = 'page';
    renderAll();
  }
  if (result?.ok) showToast(okMessage || '操作完成');
  else if (result?.error) showToast(result.error);
}

function bindEvents() {
  $('btnPagePrev').onclick = () => setPage(state.currentPage - 1);
  $('btnPageNext').onclick = () => setPage(state.currentPage + 1);
  $('currentPage').addEventListener('change', e => setPage(e.target.value));
  $('btnQuestionPrev').onclick = () => setQuestion(state.currentQuestion - 1);
  $('btnQuestionNext').onclick = () => setQuestion(state.currentQuestion + 1);
  $('currentQuestion').addEventListener('change', e => setQuestion(e.target.value));
  $('questionQidInput').addEventListener('change', () => commitQuestionMeta('qid'));
  $('questionScoreInput').addEventListener('change', () => commitQuestionMeta('score'));
  $('questionQidInput').addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); e.currentTarget.blur(); } });
  $('questionScoreInput').addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); e.currentTarget.blur(); } });
  $('btnFrame').onclick = startFraming;
  $('btnAddTag').onclick = addCurrentTag;
  $('tagInput').addEventListener('input', renderTagSuggestions);
  $('tagInput').addEventListener('focus', renderTagSuggestions);
  $('tagInput').addEventListener('keydown', handleTagInputKeydown);
  $('tagInput').addEventListener('blur', () => window.setTimeout(hideTagSuggestions, 120));
  $('btnImport').onclick = () => callBridge('import_paper', '试卷导入完成');
  $('btnOpen').onclick = () => callBridge('open_project', '项目已打开');
  $('btnExportPng').onclick = () => callBridge('export_png', 'PNG 已导出');
  $('btnExportMd').onclick = () => callBridge('export_md', 'Markdown 已导出');
  $('btnExportPdf').onclick = () => callBridge('export_pdf', 'PDF 已导出');
  $('btnCropConfirm').onclick = confirmCrop;
  $('btnCropOk').onclick = doCropConfirm;
  $('btnCropCancel').onclick = hideCropModal;
  $('cropModal').addEventListener('click', e => { if (e.target.id === 'cropModal') hideCropModal(); });
  $('treeScopeSwitch').querySelectorAll('.mode-option').forEach(button => {
    button.onclick = () => setTreeScope(button.dataset.value);
  });
  $('metricModeSwitch').querySelectorAll('.mode-option').forEach(button => {
    button.onclick = () => setMetricMode(button.dataset.value);
  });
  $('treeStage').addEventListener('scroll', hideTreeTooltip, {passive: true});
  $('btnCropConfirm').addEventListener('mousedown', e => e.stopPropagation());

  const layer = $('cropLayer');
  let selecting = false;
  layer.addEventListener('mousedown', e => {
    if (!state.framing || state.viewMode !== 'page') return;
    if (e.target.closest && e.target.closest('#cropBox')) return;
    selecting = true;
    const p = cropPointFromEvent(e);
    state.selection = {x1:p.x, y1:p.y, x2:p.x, y2:p.y, w:p.w, h:p.h};
    const box = $('cropBox');
    box.classList.add('show');
    box.style.display = 'block';
    box.style.left = `${p.x}px`; box.style.top = `${p.y}px`; box.style.width = '0px'; box.style.height = '0px';
    e.preventDefault();
  });
  window.addEventListener('mousemove', e => {
    if (!selecting || !state.selection) return;
    const p = cropPointFromEvent(e);
    const s = state.selection; s.x2 = p.x; s.y2 = p.y;
    const left = Math.min(s.x1,s.x2), top = Math.min(s.y1,s.y2), width = Math.abs(s.x2-s.x1), height = Math.abs(s.y2-s.y1);
    const box = $('cropBox');
    box.style.left = `${left}px`; box.style.top = `${top}px`; box.style.width = `${width}px`; box.style.height = `${height}px`;
  });
  window.addEventListener('mouseup', () => selecting = false);

  const viewport = $('imageViewport');
  let dragging = false, sx = 0, sy = 0, sl = 0, st = 0;
  viewport.addEventListener('mousedown', e => {
    if (state.framing || e.target.id !== 'questionImage') return;
    dragging = true; sx = e.clientX; sy = e.clientY; sl = viewport.scrollLeft; st = viewport.scrollTop; e.preventDefault();
  });
  window.addEventListener('mousemove', e => {
    if (!dragging) return;
    viewport.scrollLeft = sl - (e.clientX - sx);
    viewport.scrollTop = st - (e.clientY - sy);
  });
  window.addEventListener('mouseup', () => dragging = false);
  viewport.addEventListener('wheel', e => { if (e.shiftKey) { viewport.scrollLeft += e.deltaY; e.preventDefault(); } }, {passive:false});
}

window.addEventListener('load', async () => {
  bindEvents();
  bindSplitters();
  try { await refreshState(); } catch (e) { showToast(e.message); }
});
window.addEventListener('resize', () => { renderPreview(); renderTree(); });









function applyLayout() {
  const settings = state.data?.project?.settings || {};
  const left = Number(settings.left_width || 55);
  const preview = Number(settings.preview_height || 72);
  document.documentElement.style.setProperty('--left-width', `${left}%`);
  document.documentElement.style.setProperty('--preview-height', `${preview}%`);
}

function bindSplitters() {
  const workspace = document.querySelector('.workspace');
  const right = document.querySelector('.right-column');
  let mode = null;
  const save = async () => {
    if (!state.data?.has_project) return;
    const left = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--left-width')) || 55;
    const preview = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--preview-height')) || 72;
    try { state.data = await apiPost('/api/settings/layout', {left_width: left, preview_height: preview}); } catch (e) {}
  };
  $('splitVertical').addEventListener('pointerdown', e => { mode = 'vertical'; e.currentTarget.setPointerCapture(e.pointerId); });
  $('splitHorizontal').addEventListener('pointerdown', e => { mode = 'horizontal'; e.currentTarget.setPointerCapture(e.pointerId); });
  window.addEventListener('pointermove', e => {
    if (mode === 'vertical' && workspace) {
      const rect = workspace.getBoundingClientRect();
      const pct = Math.max(30, Math.min(75, ((e.clientX - rect.left) / rect.width) * 100));
      document.documentElement.style.setProperty('--left-width', `${pct}%`);
      renderTree();
    } else if (mode === 'horizontal' && right) {
      const rect = right.getBoundingClientRect();
      const pct = Math.max(45, Math.min(85, ((e.clientY - rect.top) / rect.height) * 100));
      document.documentElement.style.setProperty('--preview-height', `${pct}%`);
    }
  });
  window.addEventListener('pointerup', () => { if (mode) { mode = null; save(); } });
}







