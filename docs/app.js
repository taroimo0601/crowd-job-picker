(() => {
  const STORAGE_KEYS = {
    THEME: "cjp_theme",
    AUTH_HASH: "cjp_auth_hash",
    JOB_STATUS: "cjp_job_status_map",
    CUSTOM_PRESETS: "cjp_custom_presets",
    ACTIVE_PRESET: "cjp_active_preset_id",
    EXCLUDE_KEYWORDS: "cjp_exclude_keywords_v1",
  };

  const CATEGORY_LABELS = {
    development: "💻 システム開発・AI",
    design: "🎨 Web制作・デザイン",
    video: "🎬 動画編集・制作",
    writing: "✍️ ライティング",
    business: "📊 事務・データ入力",
    other: "📁 その他",
  };

  const CLOSED_PATTERNS = [
    "募集終了",
    "受付終了",
    "応募終了",
    "終了しました",
    "募集期間が終了",
    "締切済",
    "締め切りました",
    "成約済",
    "選定中",
    "キャンセル",
    "残り0日",
    "あと0日",
    "残り0時間",
  ];

  let rawData = null;
  let allJobs = [];
  let presets = [];
  let activePresetId = "preset_all";
  let currentStatusTab = "all";
  let jobStatusMap = loadJsonStorage(STORAGE_KEYS.JOB_STATUS, {});
  let persistentExcludeKeywords = [];

  // DOM Elements
  const lastUpdatedEl = document.getElementById("last-updated");
  const presetTabsEl = document.getElementById("preset-tabs");
  const savePresetBtn = document.getElementById("save-preset-btn");
  const resetFilterBtn = document.getElementById("reset-filter-btn");
  const toggleFilterBodyBtn = document.getElementById("toggle-filter-body-btn");
  const filterBodyEl = document.getElementById("filter-body");
  const activeFilterSummaryEl = document.getElementById("active-filter-summary");

  const platformCheckboxes = Array.from(
    document.querySelectorAll('#platform-checkboxes input[type="checkbox"]')
  );
  const categoryRadios = Array.from(
    document.querySelectorAll('#category-radios input[name="category"]')
  );
  const includeKeywordsInput = document.getElementById("include-keywords");
  const keywordModeSelect = document.getElementById("keyword-mode");
  const addExcludeInput = document.getElementById("add-exclude-input");
  const addExcludeBtn = document.getElementById("add-exclude-btn");
  const excludeSummaryLabel = document.getElementById("exclude-summary-label");
  const excludeChipsContainer = document.getElementById("exclude-chips-container");
  const autoExcludeBadge = document.getElementById("auto-exclude-badge");

  const rewardTypeSelect = document.getElementById("reward-type-select");
  const minFixedInput = document.getElementById("min-fixed-input");
  const minHourlyInput = document.getElementById("min-hourly-input");
  const maxProposalsInput = document.getElementById("max-proposals-input");
  const includeUnspecifiedCheck = document.getElementById("include-unspecified-check");
  const hideDismissedCheck = document.getElementById("hide-dismissed-check");
  const directSearchLinksEl = document.getElementById("direct-search-links");

  const statusTabBtns = Array.from(document.querySelectorAll(".status-tab"));
  const sortSelect = document.getElementById("sort-select");
  const jobsContainer = document.getElementById("jobs-container");

  const themeToggleBtn = document.getElementById("theme-toggle");
  const exportConfigBtn = document.getElementById("export-config-btn");
  const configModal = document.getElementById("config-modal");
  const closeModalBtn = document.getElementById("close-modal-btn");
  const configTextarea = document.getElementById("config-json-textarea");
  const copyConfigBtn = document.getElementById("copy-config-btn");

  function loadJsonStorage(key, fallback) {
    try {
      const val = localStorage.getItem(key);
      return val ? JSON.parse(val) : fallback;
    } catch {
      return fallback;
    }
  }

  function saveJsonStorage(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      // ignore storage errors
    }
  }

  function initTheme() {
    const saved = localStorage.getItem(STORAGE_KEYS.THEME) || "dark";
    document.documentElement.setAttribute("data-theme", saved);
    themeToggleBtn.addEventListener("click", () => {
      const current = document.documentElement.getAttribute("data-theme") || "dark";
      const next = current === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      localStorage.setItem(STORAGE_KEYS.THEME, next);
    });
  }

  async function sha256Hex(text) {
    const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
    return Array.from(new Uint8Array(buf))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");
  }

  async function checkPasswordIfNeeded(data) {
    if (!data.password_required || !data.password_hash) {
      return;
    }
    const savedHash = localStorage.getItem(STORAGE_KEYS.AUTH_HASH);
    if (savedHash === data.password_hash) {
      return;
    }
    const overlay = document.getElementById("auth-overlay");
    const form = document.getElementById("auth-form");
    const input = document.getElementById("auth-password-input");
    const errorEl = document.getElementById("auth-error");
    overlay.hidden = false;

    await new Promise((resolve) => {
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const enteredHash = await sha256Hex(input.value.trim());
        if (enteredHash === data.password_hash) {
          localStorage.setItem(STORAGE_KEYS.AUTH_HASH, enteredHash);
          overlay.hidden = true;
          resolve();
        } else {
          errorEl.hidden = false;
        }
      });
    });
  }

  function splitKeywords(raw) {
    if (!raw) return [];
    return raw
      .split(/[,、\s]+/)
      .map((s) => s.trim())
      .filter(Boolean);
  }

  function initPersistentExcludeKeywords(defaultList) {
    const stored = loadJsonStorage(STORAGE_KEYS.EXCLUDE_KEYWORDS, null);
    if (Array.isArray(stored) && stored.length > 0) {
      persistentExcludeKeywords = stored;
    } else {
      persistentExcludeKeywords = Array.isArray(defaultList) ? [...defaultList] : [];
      saveJsonStorage(STORAGE_KEYS.EXCLUDE_KEYWORDS, persistentExcludeKeywords);
    }
    renderExcludeChips();
  }

  function renderExcludeChips() {
    excludeSummaryLabel.textContent = `常時除外ワード一覧を確認・編集（${persistentExcludeKeywords.length}件を自動ブロック中）`;
    excludeChipsContainer.innerHTML = "";
    persistentExcludeKeywords.forEach((kw) => {
      const chip = document.createElement("span");
      chip.className = "exclude-chip";
      chip.textContent = kw;
      const delBtn = document.createElement("button");
      delBtn.type = "button";
      delBtn.title = "この除外ワードを削除";
      delBtn.textContent = "✕";
      delBtn.addEventListener("click", () => {
        persistentExcludeKeywords = persistentExcludeKeywords.filter((item) => item !== kw);
        saveJsonStorage(STORAGE_KEYS.EXCLUDE_KEYWORDS, persistentExcludeKeywords);
        renderExcludeChips();
        updateAll();
      });
      chip.appendChild(delBtn);
      excludeChipsContainer.appendChild(chip);
    });
  }

  function addExcludeKeywordsFromInput() {
    const raw = addExcludeInput.value.trim();
    if (!raw) return;
    const words = splitKeywords(raw);
    let added = false;
    words.forEach((w) => {
      if (w && !persistentExcludeKeywords.includes(w)) {
        persistentExcludeKeywords.push(w);
        added = true;
      }
    });
    addExcludeInput.value = "";
    if (added) {
      saveJsonStorage(STORAGE_KEYS.EXCLUDE_KEYWORDS, persistentExcludeKeywords);
      renderExcludeChips();
      updateAll();
    }
  }

  function getCurrentFilterState() {
    const selectedPlatforms = platformCheckboxes
      .filter((cb) => cb.checked)
      .map((cb) => cb.value);
    const selectedCatRadio = categoryRadios.find((r) => r.checked);
    return {
      platforms: selectedPlatforms,
      category: selectedCatRadio ? selectedCatRadio.value : "all",
      include_keywords: includeKeywordsInput.value.trim(),
      keyword_mode: keywordModeSelect.value,
      reward_type: rewardTypeSelect.value,
      min_fixed_reward: Math.max(0, Number(minFixedInput.value) || 0),
      min_hourly_reward: Math.max(0, Number(minHourlyInput.value) || 0),
      max_proposals: Number(maxProposalsInput.value) || 999,
      include_unspecified: includeUnspecifiedCheck.checked,
      hide_dismissed: hideDismissedCheck.checked,
      sort_by: sortSelect.value,
    };
  }

  function applyFilterStateToUI(preset) {
    const plats = preset.platforms || ["crowdworks", "lancers", "coconala", "shufti", "mamaworks"];
    platformCheckboxes.forEach((cb) => {
      cb.checked = plats.includes(cb.value);
    });
    const cat = preset.category || "all";
    categoryRadios.forEach((r) => {
      r.checked = r.value === cat;
    });
    includeKeywordsInput.value = preset.include_keywords || "";
    keywordModeSelect.value = preset.keyword_mode || "OR";
    rewardTypeSelect.value = preset.reward_type || "all";
    minFixedInput.value = String(preset.min_fixed_reward ?? 0);
    minHourlyInput.value = String(preset.min_hourly_reward ?? 0);
    maxProposalsInput.value = String(preset.max_proposals ?? 999);
    includeUnspecifiedCheck.checked = preset.include_unspecified ?? true;
    if (preset.sort_by) {
      sortSelect.value = preset.sort_by;
    }
  }

  function renderPresetBar() {
    presetTabsEl.innerHTML = "";
    presets.forEach((p) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `preset-btn ${p.id === activePresetId ? "active" : ""}`;
      btn.textContent = p.name;

      if (p.isCustom) {
        const delSpan = document.createElement("span");
        delSpan.className = "preset-delete";
        delSpan.textContent = "✕";
        delSpan.title = "このマイ条件を削除";
        delSpan.addEventListener("click", (e) => {
          e.stopPropagation();
          deleteCustomPreset(p.id);
        });
        btn.appendChild(delSpan);
      }

      btn.addEventListener("click", () => {
        activePresetId = p.id;
        localStorage.setItem(STORAGE_KEYS.ACTIVE_PRESET, activePresetId);
        applyFilterStateToUI(p);
        renderPresetBar();
        updateAll();
      });

      presetTabsEl.appendChild(btn);
    });
  }

  function saveCurrentAsPreset() {
    const name = window.prompt("現在の絞り込み条件の名前を入力してください:", "マイ条件（カスタム）");
    if (!name || !name.trim()) return;
    const state = getCurrentFilterState();
    const newPreset = {
      id: `custom_${Date.now()}`,
      name: name.trim(),
      isCustom: true,
      ...state,
    };
    const customList = loadJsonStorage(STORAGE_KEYS.CUSTOM_PRESETS, []);
    customList.push(newPreset);
    saveJsonStorage(STORAGE_KEYS.CUSTOM_PRESETS, customList);

    presets.push(newPreset);
    activePresetId = newPreset.id;
    localStorage.setItem(STORAGE_KEYS.ACTIVE_PRESET, activePresetId);
    renderPresetBar();
  }

  function deleteCustomPreset(id) {
    const customList = loadJsonStorage(STORAGE_KEYS.CUSTOM_PRESETS, []).filter(
      (item) => item.id !== id
    );
    saveJsonStorage(STORAGE_KEYS.CUSTOM_PRESETS, customList);
    presets = presets.filter((p) => p.id !== id);
    if (activePresetId === id && presets.length > 0) {
      activePresetId = presets[0].id;
      applyFilterStateToUI(presets[0]);
    }
    renderPresetBar();
    updateAll();
  }

  function renderDirectSearchLauncher(state) {
    const kwList = splitKeywords(state.include_keywords);
    const queryStr = kwList.length > 0 ? kwList.slice(0, 3).join(" ") : "";
    const encoded = encodeURIComponent(queryStr);

    const links = [
      {
        id: "crowdworks",
        name: "クラウドワークス ↗",
        url: queryStr
          ? `https://crowdworks.jp/public/jobs/search?search%5Bkeywords%5D=${encoded}`
          : "https://crowdworks.jp/public/jobs",
      },
      {
        id: "lancers",
        name: "ランサーズ ↗",
        url: queryStr
          ? `https://www.lancers.jp/work/search?open=1&keyword=${encoded}`
          : "https://www.lancers.jp/work/search?open=1",
      },
      {
        id: "coconala",
        name: "ココナラ公開依頼 ↗",
        url: queryStr
          ? `https://coconala.com/requests?keyword=${encoded}`
          : "https://coconala.com/requests",
      },
      {
        id: "shufti",
        name: "シュフティ ↗",
        url: "https://app.shufti.jp/jobs/search",
      },
      {
        id: "mamaworks",
        name: "ママワークス ↗",
        url: queryStr
          ? `https://mamaworks.jp/list?keyword=${encoded}`
          : "https://mamaworks.jp/list",
      },
    ];

    directSearchLinksEl.innerHTML = "";
    links
      .filter((l) => state.platforms.includes(l.id))
      .forEach((l) => {
        const a = document.createElement("a");
        a.className = "launcher-link";
        a.href = l.url;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        a.textContent = l.name;
        directSearchLinksEl.appendChild(a);
      });
  }

  function isJobClosed(job) {
    if (job.is_closed) return true;
    if (typeof job.days_left === "number" && job.days_left <= 0) return true;
    const text = `${job.title || ""} ${job.description || ""} ${job.deadline_label || ""}`;
    return CLOSED_PATTERNS.some((pat) => text.includes(pat));
  }

  function matchesFilter(job, state) {
    // 0. 応募終了案件の自動除外（常時有効）
    if (isJobClosed(job)) return false;

    const fullText = `${job.title || ""} ${job.description || ""} ${(job.tags || []).join(" ")}`.toLowerCase();

    // 1. 常時除外キーワード（ピックアップ段階＋ブラウザ常時ブロック）
    for (const ex of persistentExcludeKeywords) {
      if (ex && fullText.includes(ex.toLowerCase())) {
        return false;
      }
    }

    // 2. サイト
    if (!state.platforms.includes(job.platform)) return false;

    // 3. カテゴリ
    if (state.category !== "all" && job.category !== state.category) return false;

    // 4. 報酬形態
    if (state.reward_type !== "all" && job.reward_type !== state.reward_type) return false;

    // 5. 予算未定・最低報酬額（手動入力値で比較）
    const effectiveAmount = job.reward_max || job.reward_min || 0;
    if (job.is_unspecified || effectiveAmount === 0) {
      if (!state.include_unspecified) return false;
    } else {
      if (job.reward_type === "hourly") {
        if (effectiveAmount < state.min_hourly_reward) return false;
      } else {
        if (effectiveAmount < state.min_fixed_reward) return false;
      }
    }

    // 6. 応募数上限
    if ((job.proposals || 0) > state.max_proposals) return false;

    // 7. 検索キーワード
    const includeList = splitKeywords(state.include_keywords);
    if (includeList.length > 0) {
      if (state.keyword_mode === "AND") {
        const allHit = includeList.every((kw) => fullText.includes(kw.toLowerCase()));
        if (!allHit) return false;
      } else {
        const anyHit = includeList.some((kw) => fullText.includes(kw.toLowerCase()));
        if (!anyHit) return false;
      }
    }

    return true;
  }

  function sortJobs(jobs, sortBy) {
    const copy = [...jobs];
    copy.sort((a, b) => {
      if (sortBy === "reward_desc") {
        const ra = a.reward_max || a.reward_min || 0;
        const rb = b.reward_max || b.reward_min || 0;
        return rb - ra;
      }
      if (sortBy === "proposals_asc") {
        return (a.proposals || 0) - (b.proposals || 0);
      }
      if (sortBy === "days_asc") {
        return (a.days_left || 99) - (b.days_left || 99);
      }
      if (sortBy === "newest") {
        return String(b.posted_at || "").localeCompare(String(a.posted_at || ""));
      }
      return (b.match_score || 0) - (a.match_score || 0);
    });
    return copy;
  }

  function updateSummaryText(state, matchedCount) {
    const parts = [];
    parts.push(`${state.platforms.length}サイト`);
    if (state.category !== "all") {
      parts.push(CATEGORY_LABELS[state.category] || state.category);
    }
    if (state.min_fixed_reward > 0) {
      parts.push(`固定${state.min_fixed_reward.toLocaleString()}円〜`);
    }
    if (state.min_hourly_reward > 0) {
      parts.push(`時給${state.min_hourly_reward.toLocaleString()}円〜`);
    }
    if (state.max_proposals < 999) {
      parts.push(`応募${state.max_proposals}件以下`);
    }
    parts.push(`該当 ${matchedCount}件`);
    activeFilterSummaryEl.textContent = parts.join(" / ");
  }

  function setJobStatus(jobId, newStatus) {
    if (jobStatusMap[jobId] === newStatus) {
      delete jobStatusMap[jobId];
    } else {
      jobStatusMap[jobId] = newStatus;
    }
    saveJsonStorage(STORAGE_KEYS.JOB_STATUS, jobStatusMap);
    updateAll();
  }

  function renderJobCards(jobs) {
    jobsContainer.innerHTML = "";
    if (jobs.length === 0) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.innerHTML = `
        <p>現在の特定条件に一致する案件がありません。</p>
        <p style="font-size:0.8rem; margin-top:0.4rem;">最低報酬額やキーワードを緩めるか、上の「現在の条件で実サイトを直接開く」から各サイトのリアルタイム検索結果をご確認ください。</p>
      `;
      jobsContainer.appendChild(empty);
      return;
    }

    jobs.forEach((job) => {
      const status = jobStatusMap[job.id] || "";
      const card = document.createElement("article");
      card.className = `job-card ${status === "saved" ? "is-saved" : ""} ${
        status === "applied" ? "is-applied" : ""
      }`;

      const tagsHtml = (job.tags || [])
        .map((t) => `<span class="tag-badge">${escapeHtml(t)}</span>`)
        .join("");

      card.innerHTML = `
        <div class="job-card-top">
          <div class="job-badges">
            <span class="platform-badge badge-${escapeHtml(job.platform)}">${escapeHtml(
              job.platform_name
            )}</span>
            <span class="category-badge">${escapeHtml(
              CATEGORY_LABELS[job.category] || "その他"
            )}</span>
            ${tagsHtml}
          </div>
          <span class="score-pill">適合スコア ${job.match_score || 60}点</span>
        </div>

        <h3 class="job-title">
          <a href="${escapeAttr(job.url)}" target="_blank" rel="noopener noreferrer">
            ${escapeHtml(job.title)}
          </a>
        </h3>

        <p class="job-desc">${escapeHtml(job.description || "")}</p>

        <div class="job-meta-row">
          <div class="job-metrics">
            <span class="metric-reward">💰 ${escapeHtml(job.reward_label || "予算相談")}</span>
            <span class="metric-item">👥 応募 ${Number(job.proposals || 0)}件</span>
            <span class="metric-item">⏳ ${escapeHtml(job.deadline_label || "募集中")}</span>
          </div>

          <div class="job-actions">
            <button type="button" class="action-btn ${
              status === "saved" ? "active-saved" : ""
            }" data-action="saved">
              ${status === "saved" ? "★ お気に入り済" : "☆ お気に入り"}
            </button>
            <button type="button" class="action-btn ${
              status === "applied" ? "active-applied" : ""
            }" data-action="applied">
              ${status === "applied" ? "✓ 応募・検討中" : "✓ 応募済にする"}
            </button>
            <button type="button" class="action-btn" data-action="dismissed" title="一覧から非表示にする">
              ${status === "dismissed" ? "非表示を解除" : "見送り"}
            </button>
            <a class="open-link-btn" href="${escapeAttr(
              job.url
            )}" target="_blank" rel="noopener noreferrer">
              案件を開く ↗
            </a>
          </div>
        </div>
      `;

      card.querySelectorAll("button[data-action]").forEach((btn) => {
        btn.addEventListener("click", () => {
          setJobStatus(job.id, btn.getAttribute("data-action"));
        });
      });

      jobsContainer.appendChild(card);
    });
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function escapeAttr(str) {
    return escapeHtml(str);
  }

  function updateAll() {
    const state = getCurrentFilterState();
    renderDirectSearchLauncher(state);

    const conditionMatched = allJobs.filter((j) => matchesFilter(j, state));

    // タブ別の件数集計
    const listAll = conditionMatched.filter(
      (j) => !state.hide_dismissed || jobStatusMap[j.id] !== "dismissed"
    );
    const listSaved = conditionMatched.filter((j) => jobStatusMap[j.id] === "saved");
    const listApplied = conditionMatched.filter((j) => jobStatusMap[j.id] === "applied");
    const listDismissed = conditionMatched.filter((j) => jobStatusMap[j.id] === "dismissed");

    document.getElementById("count-all").textContent = String(listAll.length);
    document.getElementById("count-saved").textContent = String(listSaved.length);
    document.getElementById("count-applied").textContent = String(listApplied.length);
    document.getElementById("count-dismissed").textContent = String(listDismissed.length);

    let targetList = listAll;
    if (currentStatusTab === "saved") targetList = listSaved;
    if (currentStatusTab === "applied") targetList = listApplied;
    if (currentStatusTab === "dismissed") targetList = listDismissed;

    const sorted = sortJobs(targetList, state.sort_by);
    updateSummaryText(state, listAll.length);
    renderJobCards(sorted);
  }

  function bindEvents() {
    const inputs = [
      ...platformCheckboxes,
      ...categoryRadios,
      includeKeywordsInput,
      keywordModeSelect,
      rewardTypeSelect,
      minFixedInput,
      minHourlyInput,
      maxProposalsInput,
      includeUnspecifiedCheck,
      hideDismissedCheck,
      sortSelect,
    ];

    inputs.forEach((el) => {
      el.addEventListener("input", updateAll);
      el.addEventListener("change", updateAll);
    });

    addExcludeBtn.addEventListener("click", addExcludeKeywordsFromInput);
    addExcludeInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        addExcludeKeywordsFromInput();
      }
    });

    savePresetBtn.addEventListener("click", saveCurrentAsPreset);

    resetFilterBtn.addEventListener("click", () => {
      if (presets.length > 0) {
        activePresetId = presets[0].id;
        applyFilterStateToUI(presets[0]);
        renderPresetBar();
        updateAll();
      }
    });

    toggleFilterBodyBtn.addEventListener("click", () => {
      const isHidden = filterBodyEl.hidden;
      filterBodyEl.hidden = !isHidden;
      toggleFilterBodyBtn.setAttribute("aria-expanded", String(isHidden));
      toggleFilterBodyBtn.textContent = isHidden
        ? "条件パネルを折りたたむ ▲"
        : "条件パネルを展開する ▼";
    });

    statusTabBtns.forEach((btn) => {
      btn.addEventListener("click", () => {
        statusTabBtns.forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        currentStatusTab = btn.getAttribute("data-status") || "all";
        updateAll();
      });
    });

    exportConfigBtn.addEventListener("click", () => {
      const state = getCurrentFilterState();
      const exportObj = {
        default_filters: {
          exclude_keywords: persistentExcludeKeywords,
          exclude_closed_jobs: true,
          min_fixed_reward: state.min_fixed_reward,
          min_hourly_reward: state.min_hourly_reward,
          include_unspecified_budget: state.include_unspecified,
          max_proposals: state.max_proposals,
        },
        saved_presets: presets,
      };
      configTextarea.value = JSON.stringify(exportObj, null, 2);
      configModal.hidden = false;
    });

    closeModalBtn.addEventListener("click", () => {
      configModal.hidden = true;
    });

    copyConfigBtn.addEventListener("click", async () => {
      await navigator.clipboard.writeText(configTextarea.value);
      copyConfigBtn.textContent = "✓ コピーしました！";
      setTimeout(() => {
        copyConfigBtn.textContent = "JSONをクリップボードにコピー";
      }, 2000);
    });
  }

  async function init() {
    initTheme();
    try {
      const resp = await fetch(`./data/jobs.json?t=${Date.now()}`);
      rawData = await resp.json();
      await checkPasswordIfNeeded(rawData);

      allJobs = rawData.jobs || [];
      lastUpdatedEl.textContent = `更新: ${rawData.updated_at || "----"}`;

      const stats = rawData.auto_excluded_stats;
      if (stats && autoExcludeBadge) {
        autoExcludeBadge.textContent = `ピックアップ段階で自動除外済（終了:${stats.closed_count || 0}件 / NG:${stats.ng_keyword_count || 0}件）`;
      }

      const defaultExcludeList = (rawData.default_filters && rawData.default_filters.exclude_keywords) || [];
      initPersistentExcludeKeywords(defaultExcludeList);

      const defaultPresets = rawData.saved_presets || [];
      const customPresets = loadJsonStorage(STORAGE_KEYS.CUSTOM_PRESETS, []);
      presets = [...defaultPresets, ...customPresets];

      const savedPresetId = localStorage.getItem(STORAGE_KEYS.ACTIVE_PRESET);
      const found = presets.find((p) => p.id === savedPresetId) || presets[0];
      if (found) {
        activePresetId = found.id;
        applyFilterStateToUI(found);
      }

      renderPresetBar();
      bindEvents();
      updateAll();
    } catch (err) {
      console.error("Failed to load jobs data:", err);
      jobsContainer.innerHTML = `<div class="empty-state">データの読み込みに失敗しました。</div>`;
    }
  }

  init();
})();
