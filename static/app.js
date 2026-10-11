const state = {
  topics: [],
  selected: new Set(),
  contentScope: "combined",
  mode: "quiz",
  currentQuestion: null,
  busy: false,
  libraryBusy: false,
  answerShown: false,
  questionOrdinal: 0,
  history: [],
  historyIndex: -1,
  completed: false,
  progress: null,
  globalStats: null,
  roundFilter: 'remaining',
  libraryFilter: 'all',
  drawerReturnFocus: null,
};

const elements = {
  setupView: document.querySelector("#setupView"),
  quizView: document.querySelector("#quizView"),
  libraryView: document.querySelector("#libraryView"),
  quizModeButton: document.querySelector("#quizModeButton"),
  libraryModeButton: document.querySelector("#libraryModeButton"),
  foundationScopeButton: document.querySelector("#foundationScopeButton"),
  combinedScopeButton: document.querySelector("#combinedScopeButton"),
  topicGrid: document.querySelector("#topicGrid"),
  selectionSummary: document.querySelector("#selectionSummary"),
  saveStatus: document.querySelector("#saveStatus"),
  startButton: document.querySelector("#startButton"),
  startButtonLabel: document.querySelector("#startButtonLabel"),
  selectAllButton: document.querySelector("#selectAllButton"),
  clearButton: document.querySelector("#clearButton"),
  brandMarkButton: document.querySelector("#brandMarkButton"),
  backButton: document.querySelector("#backButton"),
  libraryBackButton: document.querySelector("#libraryBackButton"),
  studiedCount: document.querySelector("#studiedCount"),
  wrongCount: document.querySelector("#wrongCount"),
  totalCount: document.querySelector("#totalCount"),
  resetProgressButton: document.querySelector("#resetProgressButton"),
  cycleLabel: document.querySelector("#cycleLabel"),
  questionNumber: document.querySelector("#questionNumber"),
  difficultyPill: document.querySelector("#difficultyPill"),
  kindPill: document.querySelector("#kindPill"),
  questionTopics: document.querySelector("#questionTopics"),
  questionText: document.querySelector("#questionText"),
  answerPanel: document.querySelector("#answerPanel"),
  answerContent: document.querySelector("#answerContent"),
  sourceText: document.querySelector("#sourceText"),
  answerButton: document.querySelector("#answerButton"),
  nextButton: document.querySelector("#nextButton"),
  previousButton: document.querySelector("#previousButton"),
  correctButton: document.querySelector("#correctButton"),
  wrongButton: document.querySelector("#wrongButton"),
  ratingActions: document.querySelector("#ratingActions"),
  resultStatus: document.querySelector("#resultStatus"),
  completionHomeButton: document.querySelector("#completionHomeButton"),
  reviewActions: document.querySelector("#reviewActions"),
  reviewWrongButton: document.querySelector("#reviewWrongButton"),
  reviewRemainingButton: document.querySelector("#reviewRemainingButton"),
  loadingLayer: document.querySelector("#loadingLayer"),
  poolStatus: document.querySelector("#poolStatus"),
  libraryCount: document.querySelector("#libraryCount"),
  libraryScopeLabel: document.querySelector("#libraryScopeLabel"),
  libraryList: document.querySelector("#libraryList"),
  libraryState: document.querySelector("#libraryState"),
  directoryDrawer: document.querySelector("#directoryDrawer"),
  drawerHomeButton: document.querySelector("#drawerHomeButton"),
  directoryCloseButton: document.querySelector("#directoryCloseButton"),
  directoryNav: document.querySelector("#directoryNav"),
  drawerBackdrop: document.querySelector("#drawerBackdrop"),
  toast: document.querySelector("#toast"),
};

const topicInitials = {
  python: "Py",
  algorithm: "O(n)",
  fundamentals: "HTTP",
  ml: "ML",
  transformer: "Tr",
  llm: "LLM",
  rag: "RAG",
  backend: "API",
  database: "DB",
  agent: "Ag",
  deployment: "CD",
  ops: "Ops",
  system_design: "SD",
  advanced: "+",
};

async function request(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    let message = `请求失败（${response.status}）`;
    try {
      const body = await response.json();
      message = body.detail || message;
    } catch (_) {
      // 非 JSON 错误也保留 HTTP 状态，避免解析错误掩盖真正问题。
    }
    throw new Error(message);
  }
  return response.json();
}

async function initialize() {
  try {
    const data = await request("/api/bootstrap");
    state.topics = data.topics;
    state.selected = new Set(data.selected_topics);
    state.contentScope = data.content_scope || "combined";
    updateHeaderStats(data.stats);
    renderTopics();
    setMode("quiz");
    setContentScope(state.contentScope, false);
  } catch (error) {
    showToast(`题库载入失败：${error.message}`);
    elements.selectionSummary.textContent = "无法连接本地题库，请重新启动应用。";
  }
}

function setMode(mode) {
  state.mode = mode;
  const isQuiz = mode === "quiz";
  elements.quizModeButton.setAttribute("aria-pressed", String(isQuiz));
  elements.libraryModeButton.setAttribute("aria-pressed", String(!isQuiz));
  elements.startButtonLabel.textContent = isQuiz ? "开始答题" : "查看题库";
}

function setContentScope(scope, shouldSave = true) {
  state.contentScope = scope;
  elements.foundationScopeButton.setAttribute("aria-pressed", String(scope === "foundation"));
  elements.combinedScopeButton.setAttribute("aria-pressed", String(scope === "combined"));
  updateTopicCounts();
  updateSelectionSummary();
  if (shouldSave) persistSelection();
}

function renderTopics() {
  elements.topicGrid.replaceChildren();
  for (const topic of state.topics) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "topic-card";
    button.style.setProperty("--topic-accent", topic.accent);
    button.dataset.slug = topic.slug;
    button.setAttribute("aria-pressed", String(state.selected.has(topic.slug)));

    const icon = document.createElement("span");
    icon.className = "topic-icon";
    icon.textContent = topicInitials[topic.slug] || topic.label.slice(0, 2);
    const copy = document.createElement("span");
    copy.className = "topic-copy";
    const title = document.createElement("strong");
    title.textContent = topic.label;
    const description = document.createElement("small");
    description.textContent = `${topic.stage} · ${topic.description}`;
    copy.append(title, description);
    const count = document.createElement("span");
    count.className = "topic-count";
    count.dataset.role = "count";
    const check = document.createElement("span");
    check.className = "topic-check";
    check.setAttribute("aria-hidden", "true");
    button.append(icon, copy, count, check);
    button.addEventListener("click", () => toggleTopic(topic.slug));
    elements.topicGrid.append(button);
  }
  updateTopicCounts();
}

function updateTopicCounts() {
  for (const button of elements.topicGrid.querySelectorAll(".topic-card")) {
    const topic = state.topics.find((item) => item.slug === button.dataset.slug);
    if (!topic) continue;
    const count = state.contentScope === "foundation" ? topic.foundation_count : topic.question_count;
    const countElement = button.querySelector('[data-role="count"]');
    countElement.textContent = `${count} 条`;
    countElement.title = state.contentScope === "foundation"
      ? `${topic.foundation_count} 条基础知识`
      : `${topic.foundation_count} 条基础知识 + ${topic.interview_count} 道面试题`;
  }
}

function toggleTopic(slug) {
  if (state.selected.has(slug)) state.selected.delete(slug);
  else state.selected.add(slug);
  updateTopicButtons();
  updateSelectionSummary();
  persistSelection();
}

function updateTopicButtons() {
  for (const button of elements.topicGrid.querySelectorAll(".topic-card")) {
    button.setAttribute("aria-pressed", String(state.selected.has(button.dataset.slug)));
  }
}

function updateSelectionSummary() {
  const selectedTopics = state.topics.filter((topic) => state.selected.has(topic.slug));
  const scopeLabel = state.contentScope === "foundation" ? "仅基础知识" : "综合学习";
  elements.selectionSummary.replaceChildren();
  const strong = document.createElement("strong");
  if (!selectedTopics.length) {
    strong.textContent = "全部方向";
    elements.selectionSummary.append(`${scopeLabel} · `, strong, "（未选方向时自动使用全部方向）");
  } else {
    strong.textContent = `${selectedTopics.length} 个方向`;
    elements.selectionSummary.append(`${scopeLabel} · 已选择 `, strong);
  }
  elements.startButton.disabled = false;
}

let saveSequence = 0;
async function persistSelection() {
  const sequence = ++saveSequence;
  elements.saveStatus.lastChild.textContent = " 正在保存…";
  try {
    await request("/api/settings/selection", {
      method: "PUT",
      body: JSON.stringify({ topics: [...state.selected], content_scope: state.contentScope }),
    });
    if (sequence === saveSequence) elements.saveStatus.lastChild.textContent = " 已保存到本地";
  } catch (error) {
    if (sequence === saveSequence) elements.saveStatus.lastChild.textContent = " 保存失败";
    showToast(`选择未保存：${error.message}`);
  }
}

function selectAllTopics() {
  state.selected = new Set(state.topics.map((topic) => topic.slug));
  updateTopicButtons();
  updateSelectionSummary();
  persistSelection();
}

function clearTopics() {
  state.selected.clear();
  updateTopicButtons();
  updateSelectionSummary();
  persistSelection();
}

async function openSelectedMode() {
  if (state.mode === "library") await openLibrary();
  else await startQuiz();
}

async function startQuiz(roundFilter = 'remaining') {
  if (state.busy) return;
  state.history = [];
  state.historyIndex = -1;
  state.currentQuestion = null;
  state.completed = false;
  state.roundFilter = roundFilter;
  closeDirectory(false);
  setBrandAction("home");
  elements.setupView.classList.add("is-hidden");
  elements.libraryView.classList.add("is-hidden");
  elements.quizView.classList.remove("is-hidden");
  window.scrollTo({ top: 0, behavior: "smooth" });
  await loadNextQuestion();
}

function showSetup() {
  closeDirectory(false);
  setBrandAction("home");
  elements.quizView.classList.add("is-hidden");
  elements.libraryView.classList.add("is-hidden");
  elements.setupView.classList.remove("is-hidden");
  updateHeaderStats();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function openLibrary() {
  if (state.libraryBusy) return;
  state.libraryFilter = 'all';
  updateLibraryFilterButtons();
  elements.setupView.classList.add("is-hidden");
  elements.quizView.classList.add("is-hidden");
  elements.libraryView.classList.remove("is-hidden");
  setBrandAction("directory");
  window.scrollTo({ top: 0, behavior: "smooth" });
  await loadLibrarySections();
}

async function loadLibrarySections() {
  if (state.libraryBusy) return;
  setLibraryBusy(true);
  elements.libraryState.classList.add("is-hidden");
  try {
    const data = await request("/api/library/sections", {
      method: "POST",
      body: JSON.stringify({ topics: [...state.selected], content_scope: state.contentScope, result_filter: state.libraryFilter }),
    });
    renderLibrary(data);
    state.progress = data.progress;
    updateHeaderStats(data.stats);
  } catch (error) {
    elements.libraryList.replaceChildren();
    elements.directoryNav.replaceChildren();
    elements.libraryState.textContent = `题库载入失败：${error.message}`;
    elements.libraryState.classList.remove("is-hidden");
    showToast(`题库载入失败：${error.message}`);
  } finally {
    setLibraryBusy(false);
  }
}

function renderLibrary(data) {
  elements.libraryList.replaceChildren();
  elements.libraryCount.textContent = `筛选结果 ${data.total} 条`;
  elements.libraryScopeLabel.textContent = state.contentScope === "foundation" ? "仅基础知识" : "基础知识与面试题";
  renderDirectory(data.sections);
  if (!data.sections.length) {
    elements.libraryState.textContent = "当前筛选条件没有题目，可切换全部、正确或错误查看。";
    elements.libraryState.classList.remove("is-hidden");
    return;
  }

  let ordinal = 0;
  for (const section of data.sections) {
    const topicSection = document.createElement("section");
    topicSection.className = "library-topic-section";
    topicSection.style.setProperty("--section-accent", section.topic.accent);
    const heading = document.createElement("div");
    heading.className = "library-topic-heading";
    const copy = document.createElement("div");
    const eyebrow = document.createElement("small");
    eyebrow.textContent = section.topic.stage;
    const title = document.createElement("h2");
    title.textContent = section.topic.label;
    copy.append(eyebrow, title);
    const count = document.createElement("span");
    count.textContent = `${section.count} 条`;
    heading.append(copy, count);
    topicSection.append(heading);

    for (const group of section.groups) {
      const groupSection = document.createElement("section");
      groupSection.className = `library-group library-group-${group.content_type}`;
      groupSection.id = group.anchor_id;
      const groupHeading = document.createElement("div");
      groupHeading.className = "library-group-heading";
      const groupTitle = document.createElement("h3");
      groupTitle.textContent = group.label;
      const groupCount = document.createElement("span");
      groupCount.textContent = `${group.count} 条`;
      groupHeading.append(groupTitle, groupCount);
      groupSection.append(groupHeading);
      const cards = document.createElement("div");
      cards.className = "library-group-cards";
      for (const question of group.items) {
        ordinal += 1;
        cards.append(createLibraryCard(question, ordinal));
      }
      groupSection.append(cards);
      topicSection.append(groupSection);
    }
    elements.libraryList.append(topicSection);
  }
}

function renderDirectory(sections) {
  elements.directoryNav.replaceChildren();
  for (const section of sections) {
    const block = document.createElement("section");
    block.className = "directory-topic";
    const title = document.createElement("h3");
    title.textContent = section.topic.label;
    block.append(title);
    const list = document.createElement("ul");
    for (const group of section.groups) {
      const item = document.createElement("li");
      const link = document.createElement("a");
      link.href = `#${group.anchor_id}`;
      const label = document.createElement("span");
      label.textContent = group.label;
      const count = document.createElement("small");
      count.textContent = group.count;
      link.append(label, count);
      link.addEventListener("click", (event) => {
        event.preventDefault();
        closeDirectory(false);
        scrollToLibraryAnchor(group.anchor_id);
      });
      item.append(link);
      list.append(item);
    }
    block.append(list);
    elements.directoryNav.append(block);
  }
}

function scrollToLibraryAnchor(anchorId) {
  const target = document.getElementById(anchorId);
  if (!target) return;
  target.scrollIntoView({ behavior: "smooth", block: "start" });
  // content-visibility 会在长距离滚动时逐步修正前方卡片高度；布局稳定后
  // 再校准两次，避免目录第一次点击停在目标分组上方。
  window.setTimeout(() => target.scrollIntoView({ behavior: "auto", block: "start" }), 450);
  window.setTimeout(() => target.scrollIntoView({ behavior: "auto", block: "start" }), 1100);
}

function createLibraryCard(question, ordinal) {
  const card = document.createElement("article");
  card.className = "library-card";
  const meta = document.createElement("div");
  meta.className = "question-meta";
  const number = document.createElement("span");
  number.className = "question-number";
  number.textContent = `${question.content_type === "foundation" ? "KNOWLEDGE" : "QUESTION"} ${String(ordinal).padStart(2, "0")}`;
  const pills = document.createElement("div");
  pills.className = "meta-pills";
  for (const text of [question.stage, question.difficulty, question.kind]) {
    const pill = document.createElement("span");
    pill.textContent = text;
    pills.append(pill);
  }
  if (question.result === 'correct' || question.result === 'wrong') {
    const badge = document.createElement('span');
    badge.className = `result-badge result-${question.result}`;
    badge.textContent = question.result === 'correct' ? '正确' : '错误';
    pills.append(badge);
  }
  meta.append(number, pills);
  const tags = document.createElement("div");
  tags.className = "topic-tags";
  for (const slug of question.topics) {
    const topic = state.topics.find((item) => item.slug === slug);
    if (!topic) continue;
    const tag = document.createElement("span");
    tag.className = "topic-tag";
    tag.textContent = topic.label;
    tags.append(tag);
  }
  const prompt = document.createElement("h3");
  prompt.className = "library-question";
  prompt.textContent = question.prompt;
  const answerPanel = document.createElement("div");
  answerPanel.className = "library-answer";
  const divider = document.createElement("div");
  divider.className = "answer-divider";
  const dividerLabel = document.createElement("span");
  dividerLabel.textContent = question.content_type === "foundation" ? "知识详解" : "参考答案";
  divider.append(dividerLabel);
  const answerContent = document.createElement("div");
  answerContent.className = "answer-content";
  renderAnswerInto(answerContent, question.answer);
  answerPanel.append(divider, answerContent);
  const source = document.createElement("details");
  source.className = "source-details";
  const summary = document.createElement("summary");
  summary.textContent = "内容来源";
  const sourceText = document.createElement("p");
  sourceText.textContent = `${question.source_name} · ${question.source_ref}`;
  source.append(summary, sourceText);
  card.append(meta, tags, prompt, answerPanel, source);
  return card;
}

function setLibraryBusy(busy) {
  state.libraryBusy = busy;
  for (const button of document.querySelectorAll('[data-result-filter]')) button.disabled = busy;
  if (busy) elements.libraryCount.textContent = "正在读取题库…";
}

function updateLibraryFilterButtons() {
  for (const button of document.querySelectorAll('[data-result-filter]')) {
    button.setAttribute('aria-pressed', String(button.dataset.resultFilter === state.libraryFilter));
  }
}

async function loadNextQuestion() {
  if (state.busy) return;
  setBusy(true);
  try {
    await advanceQuestion();
  } catch (error) {
    showToast(`无法抽取内容：${error.message}`);
  } finally {
    setBusy(false);
  }
}

async function advanceQuestion() {
    if (state.historyIndex + 1 < state.history.length) {
      state.historyIndex += 1;
      displayHistoryQuestion();
      return;
    }
    const data = await request("/api/quiz/next", {
      method: "POST",
      body: JSON.stringify({
        topics: [...state.selected],
        content_scope: state.contentScope,
        previous_id: state.currentQuestion?.stable_id || null,
        excluded_ids: state.history.map(question => question.stable_id),
        round_filter: state.roundFilter,
      }),
    });
    state.progress = data.progress;
    updateHeaderStats(data.stats);
    if (!data.question) {
      state.completed = true;
      state.historyIndex = state.history.length;
      state.currentQuestion = null;
      hideAnswer();
      elements.questionText.textContent = data.completed ? "全部完成！当前范围内的题目已全部答对。" : data.progress.total ? "本轮结束" : "当前范围没有题目，请修改方向。";
      elements.questionTopics.replaceChildren();
      elements.questionNumber.textContent = data.completed ? "COMPLETED" : "ROUND FINISHED";
      elements.cycleLabel.textContent = "";
      elements.resultStatus.textContent = "";
      elements.difficultyPill.textContent = "—";
      elements.kindPill.textContent = "—";
      elements.poolStatus.textContent = `当前范围：正确 ${data.progress.correct} · 错误 ${data.progress.wrong} · 未答 ${data.progress.remaining - data.progress.wrong}`;
      return;
    }
    state.history.push(data.question);
    state.historyIndex = state.history.length - 1;
    displayHistoryQuestion();
}

function displayHistoryQuestion() {
  state.completed = false;
  state.currentQuestion = state.history[state.historyIndex];
  state.questionOrdinal = state.historyIndex + 1;
  hideAnswer();
  renderQuestion(state.currentQuestion);
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function previousQuestion() {
  if (state.busy || state.historyIndex <= 0) return;
  state.historyIndex -= 1;
  displayHistoryQuestion();
}

async function evaluateAndAdvance(result) {
  if (state.busy || !state.answerShown || !state.currentQuestion) return;
  setBusy(true);
  const id = state.currentQuestion.stable_id;
  try {
    const data = await request(`/api/questions/${encodeURIComponent(id)}/result`, {
      method: "PUT", body: JSON.stringify({ result, topics: [...state.selected], content_scope: state.contentScope }),
    });
    state.progress = data.progress;
    updateHeaderStats(data.stats);
    for (const question of state.history) {
      if (question.stable_id === id) question.result = result;
    }
    renderQuestion(state.currentQuestion);
    // 保存成功后才前进；抽题失败仍保留当前题和已保存评价，可再次操作。
    await advanceQuestion();
  } catch (error) {
    showToast(`操作未完成：${error.message}`);
  } finally {
    setBusy(false);
  }
}

function updateQuizControls() {
  const hasQuestion = Boolean(state.currentQuestion);
  elements.previousButton.classList.toggle("is-hidden", state.answerShown);
  elements.previousButton.disabled = state.busy || state.historyIndex <= 0;
  elements.answerButton.classList.toggle("is-hidden", !hasQuestion);
  elements.nextButton.classList.toggle("is-hidden", !state.answerShown || !hasQuestion);
  elements.ratingActions.classList.toggle("is-hidden", !state.answerShown || !hasQuestion);
  elements.completionHomeButton.classList.toggle("is-hidden", !state.completed);
  elements.reviewActions.classList.toggle('is-hidden', !state.completed);
  elements.reviewWrongButton.disabled = state.busy || !state.progress?.wrong;
  elements.reviewRemainingButton.disabled = state.busy || !state.progress?.remaining;
  for (const button of [elements.answerButton, elements.nextButton, elements.correctButton, elements.wrongButton]) button.disabled = state.busy;
  elements.resetProgressButton.disabled = state.busy;
  elements.backButton.disabled = state.busy;
  elements.brandMarkButton.disabled = state.busy;
}

function renderQuestion(question) {
  elements.questionNumber.textContent = `${state.contentScope === "foundation" ? "KNOWLEDGE" : "QUESTION"} ${String(state.questionOrdinal).padStart(2, "0")}`;
  elements.difficultyPill.textContent = question.difficulty;
  elements.kindPill.textContent = question.kind;
  elements.questionText.textContent = question.prompt;
  elements.cycleLabel.textContent = `第 ${state.questionOrdinal} 题`;
  elements.sourceText.textContent = `${question.source_name} · ${question.source_ref}`;
  elements.poolStatus.textContent = "每轮题目不重复 · 本轮结束后可复习错题 · 下一题表示跳过并撤销本题评价";
  elements.resultStatus.dataset.result = question.result || 'unrated';
  elements.resultStatus.textContent = `最近评价：${({ correct: "正确", wrong: "错误", unrated: "未评价 / 已跳过" })[question.result || "unrated"]}`;
  elements.questionTopics.replaceChildren();
  for (const slug of question.topics) {
    const topic = state.topics.find((item) => item.slug === slug);
    if (!topic) continue;
    const tag = document.createElement("span");
    tag.className = "topic-tag";
    tag.textContent = topic.label;
    elements.questionTopics.append(tag);
  }
}

async function revealAnswer() {
  if (state.busy || !state.currentQuestion) return;
  if (state.answerShown) { hideAnswer(); return; }
  setBusy(true);
  elements.answerButton.firstChild.textContent = "加载中… ";
  try {
    const data = await request(`/api/questions/${encodeURIComponent(state.currentQuestion.stable_id)}/answer`);
    renderAnswerInto(elements.answerContent, data.answer);
    state.answerShown = true;
    elements.answerPanel.classList.remove("is-collapsed");
    elements.answerButton.firstChild.textContent = "不显示答案 ";
  } catch (error) {
    elements.answerButton.disabled = false;
    elements.answerButton.firstChild.textContent = "显示答案 ";
    showToast(`答案载入失败：${error.message}`);
  } finally {
    setBusy(false);
  }
}

function hideAnswer() {
  state.answerShown = false;
  elements.answerPanel.classList.add("is-collapsed");
  elements.answerContent.replaceChildren();
  elements.answerButton.disabled = false;
  elements.answerButton.firstChild.textContent = "显示答案 ";
  updateQuizControls();
}

function renderAnswerInto(container, answer) {
  container.replaceChildren();
  const lines = answer.split("\n");
  let list = null;
  let listType = null;
  let codeLanguage = null;
  let codeLines = [];

  const flushCode = () => {
    const pre = document.createElement("pre");
    const code = document.createElement("code");
    code.className = `language-${codeLanguage || "text"}`;
    code.textContent = codeLines.join("\n");
    pre.className = codeLanguage === "text" ? "example-output" : "code-example";
    pre.append(code);
    container.append(pre);
    codeLanguage = null;
    codeLines = [];
  };

  for (const rawLine of lines) {
    const fence = rawLine.trim().match(/^```([\w+-]*)$/);
    if (fence) {
      if (codeLanguage !== null) flushCode();
      else {
        codeLanguage = fence[1] || "text";
        codeLines = [];
      }
      list = null;
      continue;
    }
    if (codeLanguage !== null) {
      codeLines.push(rawLine);
      continue;
    }
    const line = rawLine.trim();
    if (!line) {
      list = null;
      listType = null;
      continue;
    }
    const unordered = line.match(/^[-*]\s+(.+)$/);
    const ordered = line.match(/^\d+[.、]\s*(.+)$/);
    if (unordered || ordered) {
      const nextType = ordered ? "ol" : "ul";
      if (!list || listType !== nextType) {
        list = document.createElement(nextType);
        listType = nextType;
        container.append(list);
      }
      const item = document.createElement("li");
      item.textContent = (ordered || unordered)[1];
      list.append(item);
      continue;
    }
    list = null;
    listType = null;
    const markdownHeading = line.match(/^\*\*(.+?)\*\*(?::|：)?\s*(.*)$/);
    const labeled = line.match(/^(简答|要点|关键点|选型|完整链路|措施|方法|设计|防线|排查|回答框架|推荐结构|证据|例子|边界|处理方式|工程原则|注意|代价)：(.*)$/);
    if (markdownHeading || labeled) {
      const match = markdownHeading || labeled;
      const heading = document.createElement("h3");
      heading.textContent = match[1];
      container.append(heading);
      if (match[2].trim()) {
        const paragraph = document.createElement("p");
        paragraph.textContent = match[2].trim();
        container.append(paragraph);
      }
      continue;
    }
    const paragraph = document.createElement("p");
    paragraph.textContent = line;
    container.append(paragraph);
  }
  if (codeLanguage !== null) flushCode();
}

function openDirectory() {
  if (elements.libraryView.classList.contains("is-hidden")) return;
  state.drawerReturnFocus = document.activeElement;
  elements.directoryDrawer.classList.add("is-open");
  elements.directoryDrawer.setAttribute("aria-hidden", "false");
  elements.drawerBackdrop.classList.remove("is-hidden");
  elements.brandMarkButton.setAttribute("aria-expanded", "true");
  document.body.classList.add("drawer-open");
  elements.directoryCloseButton.focus();
}

function closeDirectory(restoreFocus = true) {
  const wasOpen = elements.directoryDrawer.classList.contains("is-open");
  elements.directoryDrawer.classList.remove("is-open");
  elements.directoryDrawer.setAttribute("aria-hidden", "true");
  elements.drawerBackdrop.classList.add("is-hidden");
  elements.brandMarkButton.setAttribute("aria-expanded", "false");
  document.body.classList.remove("drawer-open");
  if (wasOpen && restoreFocus) state.drawerReturnFocus?.focus();
}

function setBrandAction(action) {
  const opensDirectory = action === "directory";
  elements.brandMarkButton.setAttribute(
    "aria-label",
    opensDirectory ? "打开题库目录" : "返回方向选择",
  );
}

function handleBrandMarkClick() {
  if (elements.libraryView.classList.contains("is-hidden")) showSetup();
  else openDirectory();
}

function updateHeaderStats(stats) {
  if (stats) state.globalStats = stats;
  const shown = elements.setupView.classList.contains('is-hidden') ? state.progress : state.globalStats;
  if (!shown) return;
  elements.studiedCount.textContent = shown.correct;
  elements.wrongCount.textContent = shown.wrong;
  elements.totalCount.textContent = shown.total;
}

async function resetProgress() {
  if (state.busy || elements.resetProgressButton.disabled) return;
  const confirmed = window.confirm("确定清空全部练习进度吗？");
  if (!confirmed) return;
  setBusy(true);
  try {
    const data = await request("/api/progress/reset", { method: "POST" });
    if (state.progress) state.progress = {...state.progress, correct: 0, wrong: 0, remaining: state.progress.total};
    updateHeaderStats(data.stats);
    for (const question of state.history) question.result = "unrated";
    if (state.currentQuestion) renderQuestion(state.currentQuestion);
    if (state.completed) {
      state.completed = false;
      state.history = [];
      state.historyIndex = -1;
      state.roundFilter = 'remaining';
      await advanceQuestion();
    }
    if (!elements.libraryView.classList.contains('is-hidden')) await loadLibrarySections();
    showToast("练习进度已清零");
  } catch (error) {
    showToast(`练习进度清零失败：${error.message}`);
  } finally {
    setBusy(false);
  }
}

function trapDrawerFocus(event) {
  if (event.key !== "Tab" || !elements.directoryDrawer.classList.contains("is-open")) return;
  const focusable = [...elements.directoryDrawer.querySelectorAll("button, a[href]")];
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

function setBusy(busy) {
  state.busy = busy;
  elements.loadingLayer.classList.toggle("is-hidden", !busy);
  elements.loadingLayer.setAttribute("aria-hidden", String(!busy));
  updateQuizControls();
}

let toastTimer;
function showToast(message) {
  clearTimeout(toastTimer);
  elements.toast.textContent = message;
  elements.toast.classList.remove("is-hidden");
  toastTimer = setTimeout(() => elements.toast.classList.add("is-hidden"), 3600);
}

elements.startButton.addEventListener("click", openSelectedMode);
elements.quizModeButton.addEventListener("click", () => setMode("quiz"));
elements.libraryModeButton.addEventListener("click", () => setMode("library"));
elements.foundationScopeButton.addEventListener("click", () => setContentScope("foundation"));
elements.combinedScopeButton.addEventListener("click", () => setContentScope("combined"));
elements.selectAllButton.addEventListener("click", selectAllTopics);
elements.clearButton.addEventListener("click", clearTopics);
elements.backButton.addEventListener("click", showSetup);
elements.libraryBackButton.addEventListener("click", showSetup);
elements.brandMarkButton.addEventListener("click", handleBrandMarkClick);
elements.resetProgressButton.addEventListener("click", resetProgress);
elements.answerButton.addEventListener("click", revealAnswer);
elements.nextButton.addEventListener("click", () => evaluateAndAdvance("unrated"));
elements.correctButton.addEventListener("click", () => evaluateAndAdvance("correct"));
elements.wrongButton.addEventListener("click", () => evaluateAndAdvance("wrong"));
elements.previousButton.addEventListener("click", previousQuestion);
elements.completionHomeButton.addEventListener("click", showSetup);
elements.reviewWrongButton.addEventListener('click', () => startQuiz('wrong'));
elements.reviewRemainingButton.addEventListener('click', () => startQuiz('remaining'));
for (const button of document.querySelectorAll('[data-result-filter]')) {
  button.addEventListener('click', async () => {
    if (state.libraryBusy) return;
    state.libraryFilter = button.dataset.resultFilter;
    updateLibraryFilterButtons();
    await loadLibrarySections();
  });
}
elements.drawerHomeButton.addEventListener("click", showSetup);
elements.directoryCloseButton.addEventListener("click", () => closeDirectory());
elements.drawerBackdrop.addEventListener("click", () => closeDirectory());
elements.directoryDrawer.addEventListener("keydown", trapDrawerFocus);

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && elements.directoryDrawer.classList.contains("is-open")) {
    closeDirectory();
    return;
  }
  if (elements.quizView.classList.contains("is-hidden") || event.repeat) return;
  const tag = document.activeElement?.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA") return;
  if (event.key.toLowerCase() === "a") revealAnswer();
  if (event.key.toLowerCase() === "n" && state.answerShown) evaluateAndAdvance("unrated");
});

initialize();
