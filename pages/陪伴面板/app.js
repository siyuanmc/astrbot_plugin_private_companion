const HTTP_API = "/astrbot_plugin_private_companion/page";
const PAGE_ENDPOINT_PREFIX = "page";

const state = {
  overview: null,
  users: [],
  groups: [],
  diagnostics: [],
  availableProviders: [],
  tokenStats: null,
  selectedUserId: "",
  selectedGroupId: "",
  featureDraft: {},
};

const providerLabels = {
  LLM_PROVIDER_ID: "主模型",
  MAI_STYLE_PROVIDER_ID: "陪伴通用模型",
  DAILY_PLAN_PROVIDER_ID: "日程生成",
  DETAIL_ENHANCEMENT_PROVIDER_ID: "日程细化",
  DIARY_PROVIDER_ID: "日记生成",
  DREAM_PROVIDER_ID: "强化梦境",
  CREATIVE_PROVIDER_ID: "私下创作",
  VOICE_PROMPT_PROVIDER_ID: "主动语音文案",
  PHOTO_PROMPT_PROVIDER_ID: "生图提示词",
  NARRATION_PROVIDER_ID: "工具结果转述",
  HISTORY_SUMMARY_PROVIDER_ID: "昨日对话摘要",
  RESPONSE_REVIEW_PROVIDER_ID: "回复自检改写",
  RELATIONSHIP_ANALYSIS_PROVIDER_ID: "关系站位分析",
  COMPANION_MEMORY_PROVIDER_ID: "长期画像整理",
  DIALOGUE_EPISODE_PROVIDER_ID: "私聊片段整理",
  GROUP_INTERJECT_PROVIDER_ID: "群聊主动插话",
  GROUP_EPISODE_PROVIDER_ID: "群聊片段整理",
  GROUP_SLANG_PROVIDER_ID: "群内黑话释义",
};

const providerDescriptions = {
  LLM_PROVIDER_ID: "基础兜底模型。主动消息、未指定模型的任务都会向这里回退。",
  MAI_STYLE_PROVIDER_ID: "陪伴风格通用模型。建议选择稳定、便宜、会写自然口语的模型。",
  DAILY_PLAN_PROVIDER_ID: "每天生成粗日程和纠偏重试。适合结构化稳定、能吃人格和世界观的模型。",
  DETAIL_ENHANCEMENT_PROVIDER_ID: "把当前日程段展开成细节事件、状态变量和主动契机。",
  DIARY_PROVIDER_ID: "生成每日 Bot 日记、生活碎片、梦境碎片和日记主动契机。",
  DREAM_PROVIDER_ID: "生成强化梦境内容和梦后余韵，适合短文本意象能力好的模型。",
  CREATIVE_PROVIDER_ID: "生成小说项目设定和慢速续写正文，适合文风稳定、能守住人设身份的模型。",
  VOICE_PROMPT_PROVIDER_ID: "生成主动语音短句，并修复 TTS 标签、日语或双语格式。",
  PHOTO_PROMPT_PROVIDER_ID: "生成 photo_text 的画面提示词和画面描述，可单独使用视觉描述更强的模型。",
  NARRATION_PROVIDER_ID: "把识屏等工具结果压成自然上下文；留空则直接使用工具摘要。",
  HISTORY_SUMMARY_PROVIDER_ID: "把昨日/最近对话整理成日程和梦境可继承的残留摘要。",
  RESPONSE_REVIEW_PROVIDER_ID: "对生成回复做自检和轻改写，减少生硬、越界、解释提示词等问题。",
  RELATIONSHIP_ANALYSIS_PROVIDER_ID: "分析关系阶段、亲近度和互动边界，调用频率不高但影响语气判断。",
  COMPANION_MEMORY_PROVIDER_ID: "整理长期画像和偏好，适合用便宜但结构化能力好的模型。",
  DIALOGUE_EPISODE_PROVIDER_ID: "把私聊对话压成可复用片段，用于后续自然接话。",
  GROUP_INTERJECT_PROVIDER_ID: "群聊主动插话专用。建议选择短文本质量好、反应稳的模型。",
  GROUP_EPISODE_PROVIDER_ID: "整理群聊片段、群氛围和话题线，主要用于群聊观察。",
  GROUP_SLANG_PROVIDER_ID: "解释群内黑话、梗和成员称呼，适合用小模型。",
};

const featureMeta = {
  enable_mai_style_integration: ["陪伴风格整合", "把关系站位、记忆和自然对话规则注入回复。"],
  enable_companion_memory: ["长期画像", "沉淀用户偏好、边界、关系线索和可复用事实。"],
  enable_expression_learning: ["表达学习", "学习用户常用短句、语气和称呼，提升贴近感。"],
  enable_companion_reply_planner: ["回复规划", "先判断接话策略，再生成回复，减少机械问答。"],
  enable_intent_emotion_analysis: ["意图情绪", "识别用户情绪和真实意图，用于关系与回复策略。"],
  enable_response_self_review: ["回复自检", "发送前检查是否生硬、越界、太像系统提示。"],
  enable_passive_topic_suppression: ["话题抑制", "避免短时间反复主动提同一个话题。"],
  enable_relationship_state_machine: ["关系状态机", "维护陌生、熟悉、亲近等关系阶段。"],
  enable_dialogue_episode_memory: ["私聊片段", "把连续对话整理成共同经历和可续话头。"],
  enable_open_loop_tracking: ["未完话头", "记录用户提到的待办、约定、之后再说的事。"],
  enable_group_companion: ["群聊总开关", "控制是否处理群聊观察、画像、黑话和上下文注入。"],
  enable_group_slang_learning: ["群黑话学习", "记录群内常用梗、简称和特殊表达。"],
  enable_group_member_profiles: ["群成员画像", "记录成员发言习惯和群内角色，帮助判断气氛。"],
  enable_group_context_injection: ["群上下文注入", "在群聊回复时加入群氛围、话题和成员信息。"],
  enable_group_interjection: ["群主动插话", "允许 Bot 在群聊里主动插一句。谨慎开启。"],
  enable_group_topic_threads: ["群话题线", "维护当前群聊正在聊什么，以及话题如何变化。"],
  enable_group_episode_memory: ["群聊片段", "把群聊阶段性内容整理成摘要片段。"],
  enable_group_interjection_feedback: ["插话反馈", "记录群友对主动插话的反应，后续调整频率。"],
  enable_group_slang_meanings: ["黑话释义", "尝试解释黑话含义，方便后续理解群语境。"],
  enable_group_relationship_graph: ["群关系网", "记录成员之间的互动关系和常见组合。"],
  enable_group_privacy_guard: ["群隐私保护", "避免把私聊记忆和私下关系泄露到群聊。建议开启。"],
  enable_worldbook_member_recognition: ["群聊关系网", "以 QQ 号确认成员身份，昵称和别名只作辅助线索。"],
  enable_livingmemory_integration: ["LivingMemory 协同", "引导模型按需调用长期记忆工具，避免重复造轮子。"],
  enable_bilibili_integration: ["B 站联动", "读取 B 站 Bot 观看日志，并在合适节点私聊分享。"],
  enable_bilibili_boredom_watch: ["无聊刷 B 站", "空档或无聊时低频触发 B 站 Bot 自己看视频。"],
  enable_unanswered_screen_peek_followup: ["沉默后窥屏", "主动消息后用户长时间没回、且 Bot 正好无聊时，可免日次数窥屏确认用户在做什么。"],
  enable_creative_writing: ["私下创作", "因生活小事或梦境灵感开小说坑，并按人格速度慢慢写。"],
  creative_hidden_mode: ["低调创作模式", "默认不汇报创作，只在节点或用户询问时自然提起。"],
};

const featureGroups = [
  {
    title: "私聊陪伴",
    note: "关系、记忆、回复策略和自然表达。",
    keys: [
      "enable_mai_style_integration",
      "enable_companion_memory",
      "enable_expression_learning",
      "enable_companion_reply_planner",
      "enable_intent_emotion_analysis",
      "enable_response_self_review",
      "enable_passive_topic_suppression",
      "enable_relationship_state_machine",
      "enable_dialogue_episode_memory",
      "enable_open_loop_tracking",
    ],
  },
  {
    title: "群聊观察",
    note: "群氛围、黑话、话题线、插话和隐私边界。",
    keys: [
      "enable_group_companion",
      "enable_group_context_injection",
      "enable_group_slang_learning",
      "enable_group_slang_meanings",
      "enable_group_member_profiles",
      "enable_group_topic_threads",
      "enable_group_episode_memory",
      "enable_group_relationship_graph",
      "enable_group_interjection",
      "enable_group_interjection_feedback",
      "enable_group_privacy_guard",
    ],
  },
  {
    title: "身份与记忆联动",
    note: "QQ 关系网、外部长期记忆和身份稳定识别。",
    keys: [
      "enable_worldbook_member_recognition",
      "enable_livingmemory_integration",
    ],
  },
  {
    title: "长线主动",
    note: "Bot 自己做事、外部动作和低频分享。",
    keys: [
      "enable_bilibili_integration",
      "enable_bilibili_boredom_watch",
      "enable_unanswered_screen_peek_followup",
      "enable_creative_writing",
      "creative_hidden_mode",
    ],
  },
];

const safeFeatureKeys = [
  "enable_mai_style_integration",
  "enable_companion_memory",
  "enable_expression_learning",
  "enable_response_self_review",
  "enable_group_privacy_guard",
  "enable_relationship_state_machine",
  "enable_dialogue_episode_memory",
  "enable_open_loop_tracking",
  "enable_worldbook_member_recognition",
];

const configLabels = {
  enabled_user_count: "启用私聊对象",
  user_count: "私聊对象总数",
  require_opt_in: "是否需要私聊确认",
  max_daily_messages: "每日主动上限",
  idle_minutes: "空闲门槛分钟",
  min_interval_minutes: "最小主动间隔分钟",
  enabled: "群聊总开关",
  group_count: "群记录总数",
  enabled_group_count: "启用群数量",
  access_mode: "名单模式",
  whitelist: "白名单",
  blacklist: "黑名单",
  interjection_enabled: "群主动插话",
  active_projects: "进行中创作",
  project_count: "创作项目",
  boredom_watch_enabled: "无聊刷视频",
  hidden_mode: "低调模式",
};

const presetCatalog = {
  safe: {
    label: "保守低打扰",
    desc: "降低主动频率，保留学习和自检，适合先稳定观察。",
  },
  standard: {
    label: "标准陪伴",
    desc: "私聊学习、片段记忆和群聊上下文都保持均衡。",
  },
  active: {
    label: "高互动学习",
    desc: "更积极地学习表达和触发主动互动，模型调用量会增加。",
  },
  group_observer: {
    label: "群聊观察优先",
    desc: "强化群画像、黑话、话题线和关系网，默认不主动插话。",
  },
};

const tokenTaskLabels = {
  daily_plan: "日程生成",
  detail: "日程细化",
  dream: "梦境内容",
  diary: "日记整理",
  memory_profile: "长期画像",
  dialogue_episode: "私聊片段",
  response_review: "回复自检",
  relationship: "关系分析",
  group_interject: "群聊插话",
  group_episode: "群聊片段",
  group_slang: "黑话释义",
  worldbook_registration: "关系网自登记",
  creative_project: "创作立项",
  creative_writing: "小说创作",
  photo_prompt: "生图提示",
  screen_narration: "识屏转述",
  voice: "语音文本",
  voice_repair: "语音格式修复",
  yesterday_summary: "昨日摘要",
  full_test_detail: "完整测试细化",
  provider_test: "模型测试",
  other: "其他调用",
};

const $ = (selector) => document.querySelector(selector);

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

async function fetchJson(path, options = {}) {
  const bridge = await waitForBridge();
  const method = (options.method || "GET").toUpperCase();
  let payload;

  if (bridge && typeof bridge.apiGet === "function" && typeof bridge.apiPost === "function") {
    payload = await bridgeRequest(bridge, path, method, options.body);
  } else if (new URLSearchParams(window.location.search).get("debug_http") === "1") {
    const response = await fetch(`${HTTP_API}${path}`, {
      cache: "no-store",
      headers: options.body ? { "Content-Type": "application/json" } : undefined,
      ...options,
    });
    const text = await response.text();
    try {
      payload = text ? JSON.parse(text) : {};
    } catch (error) {
      throw new Error(response.ok ? "返回内容不是 JSON" : `HTTP ${response.status}: ${text.slice(0, 120)}`);
    }
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  } else {
    throw new Error("未检测到 AstrBot 官方插件 Page 桥接，请从 AstrBot 后台的插件拓展页打开");
  }

  payload = normalizeResponse(payload);
  if (!payload.success) throw new Error(payload.error || "请求失败");
  return payload.data;
}

function getBridge() {
  if (window.AstrBotPluginPage) return window.AstrBotPluginPage;
  try {
    if (window.parent && window.parent !== window && window.parent.AstrBotPluginPage) {
      return window.parent.AstrBotPluginPage;
    }
  } catch (error) {
    return null;
  }
  return null;
}

async function waitForBridge(timeoutMs = 2500) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const bridge = getBridge();
    if (bridge && typeof bridge.apiGet === "function" && typeof bridge.apiPost === "function") {
      return bridge;
    }
    await new Promise((resolve) => setTimeout(resolve, 80));
  }
  return getBridge();
}

async function bridgeRequest(bridge, path, method, body) {
  const url = new URL(path, "https://astrbot-plugin-page.local/");
  const endpoint = `${PAGE_ENDPOINT_PREFIX}/${url.pathname.replace(/^\/+/, "")}`.replace(/\/+/g, "/");

  if (method === "GET") {
    const params = Object.fromEntries(url.searchParams.entries());
    return bridge.apiGet(endpoint, Object.keys(params).length ? params : undefined);
  }

  let payload = body || {};
  if (typeof payload === "string") {
    try {
      payload = JSON.parse(payload);
    } catch (error) {
      payload = {};
    }
  }
  return bridge.apiPost(endpoint, payload);
}

function normalizeResponse(payload) {
  if (payload && typeof payload === "object" && Object.prototype.hasOwnProperty.call(payload, "success")) {
    return payload;
  }
  return { success: true, data: payload };
}

function postJson(path, body) {
  return fetchJson(path, { method: "POST", body: JSON.stringify(body) });
}

async function loadAll() {
  $("#subtitle").textContent = "读取运行态中...";
  try {
    const [overview, users, groups, diagnostics, availableProviders, tokenStats] = await Promise.all([
      fetchJson("/overview"),
      fetchJson("/users?limit=300"),
      fetchJson("/groups?limit=300"),
      fetchJson("/diagnostics"),
      fetchJson("/providers/available"),
      fetchJson("/token/stats"),
    ]);
    state.overview = overview;
    state.users = users.items || [];
    state.groups = groups.items || [];
    state.diagnostics = diagnostics.items || [];
    state.availableProviders = availableProviders.items || [];
    state.tokenStats = tokenStats || null;
    state.featureDraft = { ...(overview.features || {}) };
    if (!state.selectedUserId && state.users[0]) state.selectedUserId = state.users[0].user_id;
    if (!state.selectedGroupId && state.groups[0]) state.selectedGroupId = state.groups[0].group_id;
    renderAll();
    $("#subtitle").textContent = `${overview.plugin.bot_name || "Private Companion"} · ${new Date().toLocaleString()}`;
  } catch (error) {
    $("#subtitle").textContent = `加载失败：${error.message}`;
  }
}

function renderAll() {
  renderStats();
  renderDashboard();
  renderUsers();
  renderGroups();
  renderWorldbook();
  renderMemory();
  renderProactiveCandidates();
  renderCreative();
  renderTokens();
  renderModuleSettings();
  renderConfig();
  renderProviders();
}

function renderStats() {
  const overview = state.overview || {};
  const privateInfo = overview.private || {};
  const groupInfo = overview.group || {};
  const living = overview.livingmemory || {};
  const creative = overview.creative || {};
  const tokens = state.tokenStats?.totals || {};
  $("#stats").innerHTML = [
    statCard(privateInfo.enabled_user_count || 0, `私聊对象 / 共 ${privateInfo.user_count || 0}`),
    statCard(groupInfo.enabled_group_count || 0, `群聊观测 / 共 ${groupInfo.group_count || 0}`),
    statCard(creative.active_projects || 0, `私下创作 / 共 ${creative.project_count || 0}`),
    statCard(groupInfo.access_mode || "-", "群聊名单模式"),
    statCard(living.available ? "可用" : "未检测", "LivingMemory"),
    statCard(formatCompactNumber(tokens.total_tokens || 0), "累计 Token"),
  ].join("");
}

function statCard(value, label) {
  return `<article class="stat"><b>${escapeHtml(value)}</b><span>${escapeHtml(label)}</span></article>`;
}

function renderDashboard() {
  renderDashboardPulse();
  renderHealthPanel();
  renderDiagnostics();
  renderRelationshipChart();
  renderGroupBubbleChart();
  renderQuotaChart();
  renderFeatureMatrix();
  renderActivityHeatmap();
}

function renderDashboardPulse() {
  const overview = state.overview || {};
  const daily = overview.daily_state || {};
  const life = overview.life_observation || {};
  const current = life.current_plan || {};
  const proactive = overview.proactive_candidates || {};
  const proactiveCounts = proactive.counts || {};
  const worldbook = overview.worldbook || {};
  const tokens = state.tokenStats?.totals || {};
  const nextUser = state.users
    .filter((item) => Number(item.next_proactive_ts || 0) > 0)
    .sort((a, b) => Number(a.next_proactive_ts || 0) - Number(b.next_proactive_ts || 0))[0];
  const cards = [
    {
      tone: "life",
      label: "当前片段",
      value: current.activity || "暂无当前日程",
      note: [current.time, current.mood, current.message_seed].filter(Boolean).join(" · ") || daily.note || "等待日程细化",
      jump: "memory",
    },
    {
      tone: "proactive",
      label: "下一次主动",
      value: nextUser ? (nextUser.nickname || nextUser.user_id) : "暂无计划",
      note: nextUser ? `${nextUser.next_proactive} · ${nextUser.planned_action || "message"}` : `${proactiveCounts.accepted || 0} 个候选已进入计划`,
      jump: "proactive",
    },
    {
      tone: "worldbook",
      label: "关系网",
      value: `${worldbook.enabled_member_count || 0}/${worldbook.member_count || 0}`,
      note: worldbook.enabled ? `注入上限 ${worldbook.inject_limit || 0} · 群资料 ${worldbook.group_count || 0}` : "识别未开启",
      jump: "worldbook",
    },
    {
      tone: "token",
      label: "模型消耗",
      value: formatCompactNumber(tokens.total_tokens || 0),
      note: `${formatCompactNumber(tokens.calls || 0)} 次调用 · 失败 ${formatCompactNumber(tokens.errors || 0)}`,
      jump: "tokens",
    },
  ];
  $("#dashboardPulse").innerHTML = cards.map((card) => `
    <button type="button" class="pulse-card ${escapeHtml(card.tone)}" data-jump-tab="${escapeHtml(card.jump)}">
      <span>${escapeHtml(card.label)}</span>
      <b>${escapeHtml(card.value)}</b>
      <small>${escapeHtml(card.note)}</small>
    </button>
  `).join("");

  const shortcuts = [
    ["modules", "模块配置", moduleShortcutNote(overview.settings || {})],
    ["config", "名单与开关", `${overview.group?.access_mode || "whitelist"} · 白 ${overview.group?.whitelist?.length || 0} / 黑 ${overview.group?.blacklist?.length || 0}`],
    ["models", "模型分流", providerShortcutNote(overview.providers || {})],
    ["creative", "创作状态", overview.creative?.latest_title || "暂无项目"],
  ];
  $("#dashboardShortcuts").innerHTML = shortcuts.map(([tab, label, note]) => `
    <button type="button" class="shortcut-chip" data-jump-tab="${escapeHtml(tab)}">
      <b>${escapeHtml(label)}</b>
      <span>${escapeHtml(note)}</span>
    </button>
  `).join("");
}

function formatCompactNumber(value) {
  const number = Number(value || 0);
  if (number >= 1000000) return `${(number / 1000000).toFixed(number >= 10000000 ? 0 : 1)}M`;
  if (number >= 1000) return `${(number / 1000).toFixed(number >= 10000 ? 0 : 1)}K`;
  return String(Math.round(number));
}

function moduleShortcutNote(settings) {
  const enabled = [
    settings.enable_group_companion,
    settings.enable_worldbook_member_recognition,
    settings.enable_creative_writing,
    settings.enable_bilibili_integration,
  ].filter(Boolean).length;
  return `${enabled}/4 个核心模块开启`;
}

function providerShortcutNote(providers) {
  const configured = Object.values(providers || {}).filter((value) => String(value || "").trim()).length;
  return configured ? `${configured} 个 Provider 已指定` : "使用默认回退链";
}

function renderHealthPanel() {
  const overview = state.overview || {};
  const providers = overview.providers || {};
  const group = overview.group || {};
  const privateInfo = overview.private || {};
  const features = overview.features || {};
  const bili = overview.bilibili || {};
  const creative = overview.creative || {};
  const items = [
    {
      level: providers.LLM_PROVIDER_ID ? "ok" : "warn",
      title: providers.LLM_PROVIDER_ID ? "主模型已配置" : "主模型未单独配置",
      text: providers.LLM_PROVIDER_ID || "会回退到 AstrBot 默认模型",
    },
    {
      level: privateInfo.max_daily_messages > 0 ? "ok" : "warn",
      title: privateInfo.max_daily_messages > 0 ? "私聊主动可用" : "私聊主动已禁用",
      text: `每日主动上限：${privateInfo.max_daily_messages || 0}`,
    },
    {
      level: group.enabled ? "ok" : "warn",
      title: group.enabled ? "群聊观察已开启" : "群聊观察未开启",
      text: `${group.access_mode || "whitelist"} 模式，记录 ${group.group_count || 0} 个群`,
    },
    {
      level: features.enable_livingmemory_integration && overview.livingmemory?.available ? "ok" : "info",
      title: "LivingMemory 协同",
      text: livingMemoryHealthText(overview.livingmemory),
    },
    {
      level: features.enable_bilibili_integration ? (bili.available ? "ok" : "info") : "info",
      title: "B 站主动联动",
      text: features.enable_bilibili_integration
        ? `${bili.available ? "已检测" : "未检测"} · 最新 ${bili.latest_video?.title || "暂无"}`
        : "联动开关未启用",
    },
    {
      level: features.enable_creative_writing ? "ok" : "info",
      title: "私下创作",
      text: features.enable_creative_writing
        ? `${creative.active_projects || 0} 个进行中 · ${creative.hidden_mode ? "节点自然提起" : "普通模式"}`
        : "创作行为未启用",
    },
  ];
  $("#healthPanel").innerHTML = items.map((item) => `
    <div class="health-item ${escapeHtml(item.level)}">
      <b>${escapeHtml(item.title)}</b>
      <span>${escapeHtml(item.text)}</span>
    </div>
  `).join("");
}

function livingMemoryHealthText(livingmemory) {
  if (!livingmemory?.enabled) return "协同开关未启用";
  if (!livingmemory?.available) return `未检测到可用插件：${livingmemory?.plugin_dir || "未知路径"}`;
  return `可用 · ${livingmemory.tool_name || "recall_long_term_memory"}`;
}

function renderDiagnostics() {
  const items = state.diagnostics || [];
  $("#diagnosticPanel").innerHTML = items.length
    ? items.map((item) => `
      <div class="diagnostic-item ${escapeHtml(item.level || "info")}">
        <span class="diag-dot"></span>
        <div>
          <b>${escapeHtml(item.title || "")}</b>
          <p>${escapeHtml(item.text || "")}</p>
          ${item.action ? `<small>${escapeHtml(item.action)}</small>` : ""}
        </div>
      </div>
    `).join("")
    : `<div class="empty small">暂无诊断项</div>`;
}

function renderRelationshipChart() {
  const buckets = { 亲近: 0, 熟悉: 0, 陌生: 0, 未分层: 0 };
  state.users.forEach((user) => {
    const stage = user.relationship_stage || "未分层";
    buckets[Object.prototype.hasOwnProperty.call(buckets, stage) ? stage : "未分层"] += 1;
  });
  $("#relationshipChart").innerHTML = horizontalBars(buckets, Math.max(1, state.users.length));
}

function renderQuotaChart() {
  const maxDaily = Number(state.overview?.private?.max_daily_messages || 0);
  const rows = state.users.slice(0, 12).map((user) => {
    const used = Number(user.sent_today || 0);
    const pct = maxDaily > 0 ? Math.min(100, Math.round((used / maxDaily) * 100)) : 0;
    return `
      <div class="meter-row">
        <span>${escapeHtml(user.nickname || user.user_id)}</span>
        <div class="meter"><i style="width:${pct}%"></i></div>
        <b>${escapeHtml(used)}${maxDaily ? `/${escapeHtml(maxDaily)}` : ""}</b>
      </div>
    `;
  });
  $("#quotaChart").innerHTML = rows.length ? rows.join("") : `<div class="empty small">暂无私聊对象</div>`;
}

function renderGroupBubbleChart() {
  const groups = state.groups.slice(0, 12);
  if (!groups.length) {
    $("#groupBubbleChart").innerHTML = `<div class="empty small">暂无群聊数据</div>`;
    return;
  }
  const maxMessages = Math.max(1, ...groups.map((group) => Number(group.message_count || 0)));
  $("#groupBubbleChart").innerHTML = `
    <div class="bubble-wrap">
      ${groups.map((group) => {
        const size = 42 + Math.round((Number(group.message_count || 0) / maxMessages) * 56);
        return `
          <button class="bubble ${group.enabled ? "" : "off"}" data-bubble-group="${escapeHtml(group.group_id)}" style="width:${size}px;height:${size}px">
            <span>${escapeHtml(group.group_id)}</span>
            <small>${escapeHtml(group.message_count || 0)}</small>
          </button>
        `;
      }).join("")}
    </div>
  `;
  document.querySelectorAll("[data-bubble-group]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedGroupId = button.dataset.bubbleGroup;
      switchTab("group");
      renderGroups();
      renderGroupDetail(true);
    });
  });
}

function renderFeatureMatrix() {
  const groups = [
    ["陪伴", ["enable_mai_style_integration", "enable_expression_learning", "enable_response_self_review", "enable_dialogue_episode_memory"]],
    ["群聊", ["enable_group_companion", "enable_group_context_injection", "enable_group_slang_learning", "enable_group_topic_threads", "enable_group_relationship_graph"]],
    ["记忆", ["enable_companion_memory", "enable_open_loop_tracking", "enable_livingmemory_integration"]],
    ["主动联动", ["enable_unanswered_screen_peek_followup", "enable_bilibili_integration", "enable_bilibili_boredom_watch", "enable_creative_writing", "creative_hidden_mode"]],
  ];
  $("#featureMatrix").innerHTML = groups.map(([label, keys]) => `
    <section>
      <h3>${escapeHtml(label)}</h3>
      ${keys.map((key) => `<span class="feature-dot ${state.overview?.features?.[key] ? "on" : "off"}" title="${escapeHtml(key)}">${escapeHtml(key.replace(/^enable_/, ""))}</span>`).join("")}
    </section>
  `).join("");
}

function renderActivityHeatmap() {
  const now = Math.floor(Date.now() / 1000);
  const buckets = Array.from({ length: 24 }, (_, hour) => ({ hour, count: 0 }));
  [...state.users, ...state.groups].forEach((item) => {
    const ts = Number(item.last_seen_ts || 0);
    if (!ts || now - ts > 86400) return;
    buckets[new Date(ts * 1000).getHours()].count += 1;
  });
  const max = Math.max(1, ...buckets.map((item) => item.count));
  $("#activityHeatmap").innerHTML = buckets.map((item) => {
    const level = Math.min(4, Math.ceil((item.count / max) * 4));
    return `<span class="heat level-${level}" title="${item.hour}:00-${item.hour + 1}:00 · ${item.count}">${item.hour}</span>`;
  }).join("");
}

function horizontalBars(data, total) {
  return Object.entries(data).map(([label, count]) => {
    const pct = Math.round((count / total) * 100);
    return `
      <div class="meter-row">
        <span>${escapeHtml(label)}</span>
        <div class="meter"><i style="width:${pct}%"></i></div>
        <b>${escapeHtml(count)}</b>
      </div>
    `;
  }).join("");
}

function renderTokens() {
  const stats = state.tokenStats || {};
  const totals = stats.totals || {};
  const totalTokens = Number(totals.total_tokens || 0);
  const calls = Number(totals.calls || 0);
  const errors = Number(totals.errors || 0);
  const estimatedRatio = Number(totals.estimated_ratio || 0);
  $("#tokenSummary").innerHTML = [
    miniStat("总 Token", formatNumber(totalTokens)),
    miniStat("调用次数", formatNumber(calls)),
    miniStat("平均 Token", formatNumber(Math.round(Number(totals.avg_tokens || 0)))),
    miniStat("平均延迟", `${formatNumber(Math.round(Number(totals.avg_latency_ms || 0)))} ms`),
    miniStat("估算占比", `${Math.round(estimatedRatio * 100)}%`),
    miniStat("失败次数", formatNumber(errors)),
  ].join("");

  renderTokenChart("#tokenProviderChart", stats.by_provider || [], "暂无 Provider 消耗数据", (item) => item.key || "default");
  renderTokenChart("#tokenTaskChart", stats.by_task || [], "暂无任务消耗数据", (item) => tokenTaskLabel(item.key));
  renderTokenHourlyChart(stats.by_hour || []);
  renderTokenProviderTable(stats.by_provider || []);
  renderTokenTaskTable(stats.by_task || []);
  renderTokenRecentTable(stats.recent || []);
}

function renderTokenChart(selector, rows, emptyText, labeler) {
  const topRows = rows.slice(0, 8);
  const max = Math.max(1, ...topRows.map((item) => Number(item.total_tokens || 0)));
  $(selector).innerHTML = topRows.length
    ? topRows.map((item) => {
      const tokens = Number(item.total_tokens || 0);
      const pct = Math.max(2, Math.round((tokens / max) * 100));
      return `
        <div class="token-rank-row">
          <span title="${escapeHtml(labeler(item))}">${escapeHtml(labeler(item))}</span>
          <div class="meter"><i style="width:${pct}%"></i></div>
          <b>${escapeHtml(formatNumber(tokens))}</b>
        </div>
      `;
    }).join("")
    : `<div class="empty small">${escapeHtml(emptyText)}</div>`;
}

function renderTokenHourlyChart(rows) {
  const normalized = rows.slice(-48);
  const max = Math.max(1, ...normalized.map((item) => Number(item.total_tokens || 0)));
  $("#tokenHourlyChart").innerHTML = normalized.length
    ? normalized.map((item) => {
      const tokens = Number(item.total_tokens || 0);
      const height = Math.max(4, Math.round((tokens / max) * 112));
      const label = formatHourKey(item.key);
      return `
        <div class="token-bar" title="${escapeHtml(label)} · ${escapeHtml(formatNumber(tokens))} token · ${escapeHtml(item.calls || 0)} 次">
          <i style="height:${height}px"></i>
          <span>${escapeHtml(label.slice(-5))}</span>
        </div>
      `;
    }).join("")
    : `<div class="empty small">暂无小时趋势数据</div>`;
}

function renderTokenProviderTable(rows) {
  $("#tokenProviderTable").innerHTML = tokenTable(
    ["Provider", "总 Token", "输入", "输出", "调用", "估算", "平均延迟"],
    rows,
    (item) => [
      item.key || "default",
      formatNumber(item.total_tokens),
      formatNumber(item.prompt_tokens),
      formatNumber(item.completion_tokens),
      formatNumber(item.calls),
      `${Math.round(Number(item.estimated_ratio || 0) * 100)}%`,
      `${formatNumber(Math.round(Number(item.avg_latency_ms || 0)))} ms`,
    ],
    "暂无 Provider 明细"
  );
}

function renderTokenTaskTable(rows) {
  $("#tokenTaskTable").innerHTML = tokenTable(
    ["任务", "总 Token", "输入", "输出", "调用", "失败", "平均 Token"],
    rows,
    (item) => [
      tokenTaskLabel(item.key),
      formatNumber(item.total_tokens),
      formatNumber(item.prompt_tokens),
      formatNumber(item.completion_tokens),
      formatNumber(item.calls),
      formatNumber(item.errors),
      formatNumber(Math.round(Number(item.avg_tokens || 0))),
    ],
    "暂无任务明细"
  );
}

function renderTokenRecentTable(rows) {
  $("#tokenRecentTable").innerHTML = tokenTable(
    ["时间", "任务", "Provider", "Token", "延迟", "状态"],
    rows,
    (item) => [
      formatRecentTime(item.ts, item.time),
      tokenTaskLabel(item.task),
      item.provider || "default",
      `${formatNumber(item.total_tokens)}${item.estimated ? " 估" : ""}`,
      `${formatNumber(Math.round(Number(item.elapsed_ms || item.latency_ms || 0)))} ms`,
      item.success ? "成功" : `失败 ${item.error || ""}`.trim(),
    ],
    "暂无最近调用"
  );
}

function tokenTable(headers, rows, mapper, emptyText) {
  if (!rows.length) return `<div class="empty small">${escapeHtml(emptyText)}</div>`;
  return `
    <table>
      <thead><tr>${headers.map((item) => `<th>${escapeHtml(item)}</th>`).join("")}</tr></thead>
      <tbody>
        ${rows.map((row) => `<tr>${mapper(row).map((value) => `<td>${escapeHtml(value)}</td>`).join("")}</tr>`).join("")}
      </tbody>
    </table>
  `;
}

function tokenTaskLabel(key) {
  return tokenTaskLabels[key] || key || "其他调用";
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString("zh-CN");
}

function formatPercent(value) {
  const num = Number(value || 0);
  return `${Math.round(num * 100)}%`;
}

function formatHourKey(key) {
  const text = String(key || "");
  if (!text.includes("T")) return text || "-";
  return text.replace("T", " ");
}

function formatRecentTime(ts, fallback) {
  const num = Number(ts || 0);
  if (!num) return fallback || "-";
  return new Date(num * 1000).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function renderUsers() {
  const keyword = ($("#userFilter").value || "").trim().toLowerCase();
  const rows = state.users.filter((user) => {
    const text = `${user.user_id} ${user.nickname} ${user.umo}`.toLowerCase();
    return !keyword || text.includes(keyword);
  });
  $("#userRows").innerHTML = rows.length
    ? rows.map((user) => `
      <tr data-user-id="${escapeHtml(user.user_id)}" class="${user.user_id === state.selectedUserId ? "is-selected" : ""}">
        <td><strong>${escapeHtml(user.nickname || user.user_id)}</strong><br><span class="muted">${escapeHtml(user.user_id)}</span></td>
        <td><span class="badge ${user.enabled ? "" : "off"}">${escapeHtml(user.enabled ? "启用" : "停用")}</span> <span class="muted">${escapeHtml(user.relationship_stage || "未分层")}</span><br><span>分数 ${escapeHtml(user.relationship_score)}</span></td>
        <td>入站 ${escapeHtml(user.inbound_count)} · 回复 ${escapeHtml(user.reply_count)}<br><span class="muted">记忆 ${escapeHtml(user.memory_items)} 条</span></td>
        <td>今日 ${escapeHtml(user.sent_today)} · 总计 ${escapeHtml(user.proactive_sent_count)}<br><span class="muted">${escapeHtml(user.next_proactive)}</span></td>
        <td>${escapeHtml(user.last_seen)}<br><span class="muted">上次主动 ${escapeHtml(user.last_sent)}</span></td>
      </tr>
    `).join("")
    : `<tr><td class="empty" colspan="5">暂无私聊对象</td></tr>`;
  document.querySelectorAll("[data-user-id]").forEach((row) => {
    row.addEventListener("click", async () => {
      state.selectedUserId = row.dataset.userId;
      renderUsers();
      await renderUserDetail(true);
    });
  });
  renderUserDetail();
}

async function renderUserDetail(forceFetch = false) {
  const box = $("#userDetail");
  if (!state.selectedUserId) {
    box.innerHTML = "";
    return;
  }
  let detail = state.users.find((user) => user.user_id === state.selectedUserId);
  if (forceFetch || !detail?.formatted) {
    try {
      detail = await fetchJson(`/user?user_id=${encodeURIComponent(state.selectedUserId)}`);
    } catch (error) {
      box.innerHTML = `<p class="muted">详情读取失败：${escapeHtml(error.message)}</p>`;
      return;
    }
  }
  box.innerHTML = `
    <div class="toolbar">
      <button data-user-action="toggle">${escapeHtml(detail.enabled ? "停用私聊陪伴" : "启用私聊陪伴")}</button>
      <button data-user-action="reset_daily">重置今日额度</button>
      <button data-user-action="clear_schedule">清空主动计划</button>
      <button data-user-action="clear_learning" class="danger">清空学习记忆</button>
    </div>
    <form id="userEditForm" class="inline-form">
      <label>称呼 <input name="nickname" value="${escapeHtml(detail.nickname || "")}" placeholder="例如 主人 / 名字" /></label>
      <label>语气 <input name="style" value="${escapeHtml(detail.style || "")}" placeholder="温柔 / 活泼 / 工作" /></label>
      <button type="submit">保存</button>
    </form>
    <div class="visual-strip">
      ${scoreGauge("关系分", detail.relationship_score || 0, -20, 40)}
      ${scoreGauge("今日主动", detail.sent_today || 0, 0, Math.max(1, state.overview?.private?.max_daily_messages || 8))}
      ${miniStat("片段", detail.dialogue_episode_count || (detail.dialogue_episodes || []).length)}
      ${miniStat("未完话头", detail.open_loop_count || (detail.open_loops || []).length)}
    </div>
    <div class="detail-grid">
      ${detailBlock("关系和主动", detail.formatted?.relationship || "", [["下次主动", detail.formatted?.next_proactive || detail.next_proactive], ["动作偏好", detail.formatted?.action_affinity || ""]])}
      ${detailBlock("最近对话", "", [["用户消息", detail.last_user_message || ""], ["陪伴回复", detail.last_companion_message || ""]])}
      ${detailBlock("对话片段", "", (detail.dialogue_episodes || []).map((item, index) => [`#${index + 1}`, item.summary || item.title || JSON.stringify(item)]))}
      ${detailBlock("未完话头", "", (detail.open_loops || []).map((item, index) => [`#${index + 1}`, item.text || item.topic || JSON.stringify(item)]))}
    </div>
  `;
  bindUserActions(detail);
}

function bindUserActions(detail) {
  $("#userEditForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await runAction(() => postJson("/user/update", {
      user_id: detail.user_id,
      nickname: form.get("nickname"),
      style: form.get("style"),
    }));
  });
  document.querySelectorAll("[data-user-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      const action = button.dataset.userAction;
      const body = { user_id: detail.user_id };
      if (action === "toggle") body.enabled = !detail.enabled;
      if (action === "reset_daily") body.reset_daily = true;
      if (action === "clear_schedule") body.clear_schedule = true;
      if (action === "clear_learning" && !confirm("确定清空该用户的学习记忆、片段和未完话头吗？")) return;
      if (action === "clear_learning") body.clear_learning = true;
      await runAction(() => postJson("/user/update", body));
    });
  });
}

function renderGroups() {
  const keyword = ($("#groupFilter").value || "").trim().toLowerCase();
  const rows = state.groups.filter((group) => !keyword || String(group.group_id).toLowerCase().includes(keyword));
  $("#groupRows").innerHTML = rows.length
    ? rows.map((group) => `
      <tr data-group-id="${escapeHtml(group.group_id)}" class="${group.group_id === state.selectedGroupId ? "is-selected" : ""}">
        <td><strong>${escapeHtml(group.group_id)}</strong><br><span class="muted">${escapeHtml(group.enabled ? "观测中" : "已停用")}</span></td>
        <td><span class="badge ${group.allowed_by_mode ? "" : "off"}">${escapeHtml(group.allowed_by_mode ? "允许" : "名单拦截")}</span><br><span class="muted">今日插话 ${escapeHtml(group.interject_today)}</span></td>
        <td>${escapeHtml(group.atmosphere?.mood || "未判断")}<br><span class="muted">${escapeHtml(group.atmosphere?.last_summary || "")}</span></td>
        <td>消息 ${escapeHtml(group.message_count)} · 群友 ${escapeHtml(group.member_count)}<br><span class="muted">黑话 ${escapeHtml(group.slang_count)} · 话题 ${escapeHtml(group.topic_count)}</span></td>
        <td>${escapeHtml(group.last_seen)}<br><span class="muted">上次插话 ${escapeHtml(group.last_interject)}</span></td>
      </tr>
    `).join("")
    : `<tr><td class="empty" colspan="5">暂无群聊观测数据</td></tr>`;
  document.querySelectorAll("[data-group-id]").forEach((row) => {
    row.addEventListener("click", async () => {
      state.selectedGroupId = row.dataset.groupId;
      renderGroups();
      await renderGroupDetail(true);
    });
  });
  renderGroupDetail();
}

async function renderGroupDetail(forceFetch = false) {
  const box = $("#groupDetail");
  if (!state.selectedGroupId) {
    box.innerHTML = "";
    return;
  }
  let detail = state.groups.find((group) => group.group_id === state.selectedGroupId);
  if (forceFetch || !detail?.formatted) {
    try {
      detail = await fetchJson(`/group?group_id=${encodeURIComponent(state.selectedGroupId)}`);
    } catch (error) {
      box.innerHTML = `<p class="muted">详情读取失败：${escapeHtml(error.message)}</p>`;
      return;
    }
  }
  const topics = (detail.topic_threads || []).map((item, index) => [`#${index + 1}`, item.topic || item.summary || JSON.stringify(item)]);
  const episodes = (detail.group_episodes || []).map((item, index) => [`#${index + 1}`, item.summary || item.title || JSON.stringify(item)]);
  box.innerHTML = `
    <div class="toolbar">
      <button data-group-action="toggle">${escapeHtml(detail.enabled ? "停用群聊观测" : "启用群聊观测")}</button>
      <button data-group-action="reset_interjection">重置插话反馈</button>
      <button data-group-action="clear_observation" class="danger">清空群聊观测</button>
    </div>
    <div class="visual-strip">
      ${miniStat("消息", detail.message_count || 0)}
      ${miniStat("群友", detail.member_count || Object.keys(detail.members || {}).length)}
      ${miniStat("已识别", detail.recognized_member_count || 0)}
      ${miniStat("黑话", detail.slang_count || (detail.slang_terms || []).length)}
      ${miniStat("话题", detail.topic_count || (detail.topic_threads || []).length)}
    </div>
    <div class="detail-grid">
      ${detailBlock("群状态", detail.formatted?.status || "", [["常用词", formatSlangTerms(detail.slang_terms || [])]])}
      <section class="detail-block"><h2>关系网</h2>${relationshipGraphSvg(detail.relationship_edges || {})}</section>
      <section class="detail-block"><h2>消息活跃</h2>${messageTimelineSvg(detail.recent_messages || [])}</section>
      ${detailBlock("插话反馈", detail.formatted?.feedback || "", [])}
      ${detailBlock("话题线", "", topics)}
      ${detailBlock("群聊片段", "", episodes)}
      ${detailBlock("关系网摘要", detail.formatted?.relationship_graph || "", [])}
    </div>
  `;
  bindGroupActions(detail);
}

function bindGroupActions(detail) {
  document.querySelectorAll("[data-group-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      const action = button.dataset.groupAction;
      const body = { group_id: detail.group_id };
      if (action === "toggle") body.enabled = !detail.enabled;
      if (action === "reset_interjection") body.reset_interjection = true;
      if (action === "clear_observation" && !confirm("确定清空该群的观测数据、黑话、话题和关系网吗？")) return;
      if (action === "clear_observation") body.clear_observation = true;
      await runAction(() => postJson("/group/update", body));
    });
  });
}

function renderWorldbook() {
  const worldbook = state.overview?.worldbook || {};
  const members = Array.isArray(worldbook.members) ? worldbook.members : [];
  const groups = Array.isArray(worldbook.groups) ? worldbook.groups : [];
  const keyword = ($("#worldbookMemberFilter")?.value || "").trim().toLowerCase();
  const filteredMembers = members.filter((item) => {
    const haystack = [
      item.user_id,
      item.name,
      ...(Array.isArray(item.aliases) ? item.aliases : []),
      ...(Array.isArray(item.observed_names) ? item.observed_names : []),
      item.content,
    ].join(" ").toLowerCase();
    return !keyword || haystack.includes(keyword);
  });

  $("#worldbookSummary").innerHTML = [
    worldbookStat("QQ 身份锚点", worldbook.enabled_member_count || 0, `${worldbook.member_count || 0} 个关系节点`),
    worldbookStat("群资料", worldbook.group_count || 0, "可用于群聊上下文"),
    worldbookStat("资料条目", worldbook.entry_count || 0, "保留完整原始资料"),
    worldbookStat("识别方式", worldbook.enabled ? "QQ 精确" : "关闭", worldbook.match_aliases ? "称呼辅助开启" : "仅 QQ 确认"),
  ].join("");
  $("#worldbookSourceFiles").textContent = Array.isArray(worldbook.source_files) && worldbook.source_files.length
    ? `资料路径：${worldbook.source_files.join("；")}`
    : "资料路径：默认路径尚未读取到可用配置";
  $("#worldbookMemberCount").textContent = `${filteredMembers.length}/${members.length} 个成员`;
  renderDl("#worldbookImportState", {
    last_import: worldbook.last_import || "未导入",
    auto_import: worldbook.auto_import ? "开启" : "关闭",
    inject_limit: worldbook.inject_limit || 0,
  });
  $("#worldbookMembers").innerHTML = filteredMembers.length
    ? filteredMembers.map(worldbookMemberCard).join("")
    : `<div class="empty small">暂无匹配关系节点</div>`;
  $("#worldbookGroups").innerHTML = groups.length
    ? groups.map((item) => `
      <section class="worldbook-group-card">
        <div class="worldbook-member-head">
          <div>
            <b>${escapeHtml(item.group_id || "-")}</b>
            <span>${escapeHtml(item.name || "未命名群资料")} · 优先级 ${escapeHtml(item.priority ?? "-")}</span>
          </div>
          <button type="button" data-worldbook-group-delete="${escapeHtml(item.group_id || "")}" class="danger-outline">删除</button>
        </div>
        <div class="worldbook-compact-meta">
          <span>${escapeHtml(item.content ? "有群资料正文" : "无群资料正文")}</span>
        </div>
        <details class="worldbook-editor">
          <summary>编辑群资料</summary>
          <label>名称 <input data-worldbook-group-name="${escapeHtml(item.group_id || "")}" value="${escapeHtml(item.name || "")}" /></label>
          <label>优先级 <input data-worldbook-group-priority="${escapeHtml(item.group_id || "")}" type="number" value="${escapeHtml(item.priority ?? 110)}" /></label>
          <label>资料正文 <textarea data-worldbook-group-content="${escapeHtml(item.group_id || "")}" rows="5">${escapeHtml(item.content || "")}</textarea></label>
          <button type="button" data-worldbook-group-save="${escapeHtml(item.group_id || "")}">保存群资料</button>
        </details>
      </section>
    `).join("")
    : `<div class="empty small">暂无群资料</div>`;
  bindWorldbookMemberActions();
  bindWorldbookGroupActions();
}

function worldbookStat(label, value, note) {
  return `
    <article class="worldbook-stat">
      <span>${escapeHtml(label)}</span>
      <b>${escapeHtml(value)}</b>
      <small>${escapeHtml(note)}</small>
    </article>
  `;
}

function worldbookMemberCard(item) {
  const aliases = Array.isArray(item.aliases) ? item.aliases : [];
  const observed = Array.isArray(item.observed_names) ? item.observed_names : [];
  const memories = Array.isArray(item.important_memories) ? item.important_memories : [];
  const chips = [...aliases.map((name) => `别名：${name}`), ...observed.map((name) => `群名片：${name}`)].slice(0, 12);
  return `
    <section class="worldbook-member-card ${item.enabled ? "" : "off"}">
      <div class="worldbook-member-head">
        <div>
          <b>${escapeHtml(item.name || item.user_id || "未命名成员")}</b>
          <span>身份 QQ ${escapeHtml(item.user_id || "-")} · 优先级 ${escapeHtml(item.priority ?? "-")}</span>
        </div>
        <button type="button" data-worldbook-member="${escapeHtml(item.user_id || "")}" data-enabled="${item.enabled ? "0" : "1"}">
          ${escapeHtml(item.enabled ? "停用" : "启用")}
        </button>
      </div>
      <div class="worldbook-compact-meta">
        <span>${escapeHtml(aliases.length)} 个别名</span>
        <span>${escapeHtml(observed.length)} 个曾见群名片</span>
        <span>${escapeHtml((item.important_memories || []).length)} 条记忆</span>
      </div>
      <details class="worldbook-editor">
        <summary>编辑关系节点</summary>
        <div class="worldbook-chip-row">
          ${chips.length ? chips.map((chip) => `<span>${escapeHtml(chip)}</span>`).join("") : `<span>暂无别名记录</span>`}
        </div>
        <label>别名
          <textarea data-worldbook-aliases="${escapeHtml(item.user_id || "")}" rows="3">${escapeHtml(aliases.join("\n"))}</textarea>
        </label>
        <label>名称
          <input data-worldbook-name="${escapeHtml(item.user_id || "")}" value="${escapeHtml(item.name || "")}" />
        </label>
        <label>注入优先级
          <input data-worldbook-priority="${escapeHtml(item.user_id || "")}" type="number" value="${escapeHtml(item.priority ?? 120)}" />
        </label>
        <label>资料正文
          <textarea data-worldbook-content="${escapeHtml(item.user_id || "")}" rows="5">${escapeHtml(item.content || "")}</textarea>
        </label>
        <label>身份说明
          <textarea data-worldbook-identity-note="${escapeHtml(item.user_id || "")}" rows="3">${escapeHtml(item.identity_note || "")}</textarea>
        </label>
        <label>互动边界（可选）
          <textarea data-worldbook-boundary-note="${escapeHtml(item.user_id || "")}" rows="3">${escapeHtml(item.boundary_note || "")}</textarea>
        </label>
        <div class="worldbook-memory-list">
          ${memories.length ? memories.map((memory, index) => worldbookMemoryCard(item.user_id || "", memory, index)).join("") : `<div class="empty small">暂无重要记忆</div>`}
        </div>
        <button type="button" data-worldbook-save="${escapeHtml(item.user_id || "")}">保存关系节点</button>
        <button type="button" data-worldbook-delete="${escapeHtml(item.user_id || "")}" class="danger-outline">删除节点</button>
      </details>
    </section>
  `;
}

function worldbookMemoryCard(userId, memory, index) {
  return `
    <section class="worldbook-memory-card ${memory.enabled === false ? "off" : ""}">
      <div>
        <b>${escapeHtml(memory.title || "重要记忆")}</b>
        <p>${escapeHtml(memory.content || "")}</p>
        <span>${escapeHtml(memory.privacy || "internal")} · 权重 ${escapeHtml(memory.weight ?? 50)}${memory.source ? ` · ${escapeHtml(memory.source)}` : ""}</span>
      </div>
      <div class="actions compact">
        <button type="button" data-worldbook-memory-toggle="${escapeHtml(userId)}" data-memory-index="${escapeHtml(index)}">
          ${escapeHtml(memory.enabled === false ? "启用" : "停用")}
        </button>
        <button type="button" class="danger-outline" data-worldbook-memory-delete="${escapeHtml(userId)}" data-memory-index="${escapeHtml(index)}">删除</button>
      </div>
    </section>
  `;
}

function getWorldbookMember(userId) {
  const members = state.overview?.worldbook?.members || [];
  return members.find((item) => item.user_id === userId);
}

function bindWorldbookMemberActions() {
  document.querySelectorAll("[data-worldbook-member]").forEach((button) => {
    button.addEventListener("click", async () => {
      const userId = button.dataset.worldbookMember;
      if (!userId) return;
      await runAction(() => postJson("/worldbook/member/update", {
        user_id: userId,
        enabled: button.dataset.enabled === "1",
      }));
    });
  });
  document.querySelectorAll("[data-worldbook-save]").forEach((button) => {
    button.addEventListener("click", async () => {
      const userId = button.dataset.worldbookSave;
      if (!userId) return;
      const aliasBox = findWorldbookField("aliases", userId);
      const identityInput = findWorldbookField("identity-note", userId);
      const boundaryInput = findWorldbookField("boundary-note", userId);
      const nameInput = findWorldbookField("name", userId);
      const priorityInput = findWorldbookField("priority", userId);
      const contentInput = findWorldbookField("content", userId);
      const aliases = String(aliasBox?.value || "")
        .split(/[\n,，;；]+/)
        .map((item) => item.trim())
        .filter(Boolean);
      await runAction(() => postJson("/worldbook/member/update", {
        user_id: userId,
        name: nameInput?.value || "",
        priority: Number(priorityInput?.value || 120),
        content: contentInput?.value || "",
        identity_note: identityInput?.value || "",
        boundary_note: boundaryInput?.value || "",
        aliases,
      }));
    });
  });
  document.querySelectorAll("[data-worldbook-memory-toggle]").forEach((button) => {
    button.addEventListener("click", async () => {
      const userId = button.dataset.worldbookMemoryToggle;
      const index = Number(button.dataset.memoryIndex || -1);
      const member = getWorldbookMember(userId);
      const memories = Array.isArray(member?.important_memories) ? member.important_memories.map((item) => ({ ...item })) : [];
      if (!userId || index < 0 || index >= memories.length) return;
      memories[index].enabled = memories[index].enabled === false;
      await runAction(() => postJson("/worldbook/member/update", { user_id: userId, important_memories: memories }));
    });
  });
  document.querySelectorAll("[data-worldbook-memory-delete]").forEach((button) => {
    button.addEventListener("click", async () => {
      const userId = button.dataset.worldbookMemoryDelete;
      const index = Number(button.dataset.memoryIndex || -1);
      const member = getWorldbookMember(userId);
      const memories = Array.isArray(member?.important_memories) ? member.important_memories.map((item) => ({ ...item })) : [];
      if (!userId || index < 0 || index >= memories.length) return;
      memories.splice(index, 1);
      await runAction(() => postJson("/worldbook/member/update", { user_id: userId, important_memories: memories }));
    });
  });
  document.querySelectorAll("[data-worldbook-delete]").forEach((button) => {
    button.addEventListener("click", async () => {
      const userId = button.dataset.worldbookDelete;
      if (!userId || !confirm(`删除关系节点 ${userId}？`)) return;
      await runAction(() => postJson("/worldbook/member/update", { user_id: userId, delete: true }));
    });
  });
}

function findWorldbookField(field, id) {
  return [...document.querySelectorAll(`[data-worldbook-${field}]`)]
    .find((item) => item.getAttribute(`data-worldbook-${field}`) === id);
}

function findWorldbookGroupField(field, id) {
  return [...document.querySelectorAll(`[data-worldbook-group-${field}]`)]
    .find((item) => item.getAttribute(`data-worldbook-group-${field}`) === id);
}

function bindWorldbookGroupActions() {
  document.querySelectorAll("[data-worldbook-group-save]").forEach((button) => {
    button.addEventListener("click", async () => {
      const groupId = button.dataset.worldbookGroupSave;
      if (!groupId) return;
      await runAction(() => postJson("/worldbook/group/update", {
        group_id: groupId,
        name: findWorldbookGroupField("name", groupId)?.value || "",
        priority: Number(findWorldbookGroupField("priority", groupId)?.value || 110),
        content: findWorldbookGroupField("content", groupId)?.value || "",
      }));
    });
  });
  document.querySelectorAll("[data-worldbook-group-delete]").forEach((button) => {
    button.addEventListener("click", async () => {
      const groupId = button.dataset.worldbookGroupDelete;
      if (!groupId || !confirm(`删除群资料 ${groupId}？`)) return;
      await runAction(() => postJson("/worldbook/group/update", { group_id: groupId, delete: true }));
    });
  });
}

function renderMemory() {
  const overview = state.overview || {};
  const daily = overview.daily_state || {};
  const life = overview.life_observation || {};
  $("#livingMemoryBox").textContent = overview.livingmemory?.status || "未读取到 LivingMemory 状态";
  renderLifeHero(daily, life);
  renderDreamCard(life.dream || {});
  renderStatePillBoard(daily);
  renderDiaryCards(life.diaries || []);
  renderDreamFragments(life.dream_fragments || []);
  renderDl("#dailyState", daily);
  renderDailyTimeline();
  renderInteractionImpact();
  renderMemoryComposition();
  renderSlangCloud();
}

function renderLifeHero(daily, life) {
  const energy = Number(daily.energy || 0);
  const pct = Math.max(0, Math.min(100, energy));
  $("#lifeEnergy").textContent = daily.energy === undefined || daily.energy === "" ? "--" : `${formatNumber(energy)}`;
  $("#lifeEnergyBar").style.width = `${pct}%`;
  $("#lifeMood").textContent = daily.mood_bias || "平稳";
  $("#lifeNote").textContent = daily.note || daily.sleep || "暂无额外备注";
  $("#lifeLocation").textContent = daily.location || "未记录";
  $("#lifeWeather").textContent = daily.weather || "暂无天气";
  const current = life.current_plan || {};
  $("#lifeCurrentActivity").textContent = current.activity || "暂无当前日程";
  $("#lifeCurrentSeed").textContent = [current.time, current.mood, current.message_seed].filter(Boolean).join(" · ") || "等待日程细化";
}

function renderDreamCard(dream) {
  const meta = [
    dream.dream_type || "碎片梦",
    dream.mood ? `情绪 ${dream.mood}` : "",
    dream.duration_hours ? `${dream.duration_hours} 小时` : "",
    dream.generated_at || dream.date || "",
  ].filter(Boolean).join(" · ");
  $("#dreamMeta").textContent = meta || "暂无梦境记录";
  const delta = Number(dream.energy_delta || 0);
  const deltaText = delta > 0 ? `能量 +${delta}` : delta < 0 ? `能量 ${delta}` : "能量平稳";
  $("#dreamAfterglow").textContent = dream.afterglow || dream.label || deltaText;
  $("#dreamContent").textContent = dream.content || dream.label || "暂时没有可展示的梦境内容。开启增强梦境或生成今日状态后，这里会出现更完整的梦境记录。";
  const factors = Array.isArray(dream.factors) ? dream.factors : [];
  $("#dreamFactors").innerHTML = factors.length
    ? factors.map((item) => `<span class="fragment-chip">${escapeHtml(item)}</span>`).join("")
    : `<span class="muted">暂无梦境因子</span>`;
}

function renderStatePillBoard(daily) {
  const items = [
    ["睡眠", daily.sleep],
    ["梦境", daily.dream],
    ["健康", daily.health],
    ["饥饿", daily.hunger],
    ["生理周期", daily.body_cycle],
    ["天气", daily.weather],
  ].filter(([, value]) => value !== undefined && value !== "");
  $("#statePillBoard").innerHTML = items.length
    ? items.map(([label, value]) => `
      <span>
        <b>${escapeHtml(label)}</b>
        ${escapeHtml(value || "-")}
      </span>
    `).join("")
    : `<div class="empty small">暂无今日状态。生成今日状态后会展示生活感指标。</div>`;
}

function renderDiaryCards(diaries) {
  $("#diaryCards").innerHTML = diaries.length
    ? diaries.slice().reverse().map((item) => {
      const tags = Array.isArray(item.tags) && item.tags.length
        ? item.tags.map((tag) => `<span>${escapeHtml(tag)}</span>`).join("")
        : `<span>未标记</span>`;
      return `
        <section class="diary-card">
          <div>
            <b>${escapeHtml(item.date || "未记录日期")}</b>
            <small>${escapeHtml(item.generated_at || "")}</small>
          </div>
          <p>${escapeHtml(item.summary || "暂无日记摘要")}</p>
          ${item.share_seed ? `<blockquote>${escapeHtml(item.share_seed)}</blockquote>` : ""}
          <div class="diary-tags">${tags}</div>
        </section>
      `;
    }).join("")
    : `<div class="empty small">暂无日记。到日记生成时间或手动生成后，这里会记录 Bot 的生活碎片。</div>`;
}

function renderDreamFragments(fragments) {
  if (!fragments.length) {
    $("#dreamFragments").innerHTML = `<div class="empty small">暂无梦境碎片。日记和梦境生成后会积累关键词。</div>`;
    return;
  }
  const max = Math.max(1, ...fragments.map((item) => Number(item.weight || 1)));
  $("#dreamFragments").innerHTML = fragments.map((item) => {
    const weight = Number(item.weight || 1);
    const size = 12 + Math.round((weight / max) * 8);
    const title = [item.source, item.created_at, weight ? `权重 ${weight.toFixed(1)}` : ""].filter(Boolean).join(" · ");
    return `<span class="fragment-chip" style="font-size:${size}px" title="${escapeHtml(title)}">${escapeHtml(item.text || "")}</span>`;
  }).join("");
}

function renderCreative() {
  const creative = state.overview?.creative || {};
  const settings = state.overview?.settings || {};
  $("#creativeActiveCount").textContent = creative.active_projects || 0;
  $("#creativeProjectCount").textContent = creative.project_count || 0;
  $("#creativeRevealMode").textContent = creative.hidden_mode ? "节点自然提起" : "普通模式";
  $("#creativeLatestTitle").textContent = creative.latest_title || "暂无";
  $("#creativeIntro").textContent = creative.enabled
    ? "私下创作会从日程、日记、梦境或生活小事里长出灵感。它不是每天打卡式展示，而是由 Bot 自己按节奏写，写到开头、过半、完稿或想听读后感觉时才可能进入主动候选。"
    : "私下创作当前未开启。开启后，Bot 会把创作当作自己的长线生活行为之一。";
  renderDl("#creativeSettings", {
    "功能状态": creative.enabled ? "开启" : "关闭",
    "低调模式": creative.hidden_mode ? "开启" : "关闭",
    "灵感触发概率": formatPercent(settings.creative_inspiration_probability),
    "节点提起概率": formatPercent(settings.creative_share_probability),
    "基础写作速度": `${settings.creative_base_chars_per_hour || 0} 字/小时`,
    "同时项目上限": settings.creative_max_active_projects || 0,
  });
  const items = creative.items || [];
  $("#creativeProjects").innerHTML = items.length
    ? items.slice().reverse().map(renderCreativeProjectCard).join("")
    : `<div class="empty">暂无创作项目。等某个生活片段或梦境变成灵感时，这里会出现新的小坑。</div>`;
}

function renderProactiveCandidates() {
  const data = state.overview?.proactive_candidates || {};
  const counts = data.counts || {};
  const items = data.items || [];
  $("#proactiveSummary").innerHTML = [
    proactiveSummaryCard("候选总数", data.total || 0, "最近 36 小时内保留"),
    proactiveSummaryCard("已进入计划", counts.accepted || 0, "当前或历史接受候选"),
    proactiveSummaryCard("已发送", counts.sent || 0, "实际发出的主动"),
    proactiveSummaryCard("被拦截", counts.blocked || 0, "去重、配额或已有更早计划"),
  ].join("");
  $("#proactiveSourceChart").innerHTML = donutChart(data.source_counts || {});
  $("#proactiveStatusChart").innerHTML = donutChart(counts || {});
  if (!items.length) {
    $("#proactiveCandidateList").innerHTML = `<div class="empty small">暂无主动候选。运行一段时间后，这里会显示随机日程、群聊分享、B 站、创作等候选。</div>`;
    return;
  }
  $("#proactiveCandidateList").innerHTML = items.map((item) => {
    const status = proactiveStatusLabel(item.status);
    return `
      <section class="proactive-candidate ${escapeHtml(item.status || "unknown")}">
        <div class="proactive-candidate-head">
          <div>
            <b>${escapeHtml(item.topic || item.reason || "未命名候选")}</b>
            <span>${escapeHtml(item.source || "-")} · ${escapeHtml(item.reason || "-")} · ${escapeHtml(item.action || "message")}</span>
          </div>
          <span class="badge">${escapeHtml(status)}</span>
        </div>
        <p>${escapeHtml(item.motive || "暂无动机记录")}</p>
        <div class="proactive-meta">
          <span>用户：${escapeHtml(item.user_id || "-")}</span>
          <span>计划：${escapeHtml(item.scheduled || "-")}</span>
          <span>创建：${escapeHtml(item.created || "-")}</span>
          <span>评分：${escapeHtml(item.score || 0)}</span>
          ${item.note ? `<span>说明：${escapeHtml(item.note)}</span>` : ""}
        </div>
      </section>
    `;
  }).join("");
}

function proactiveSummaryCard(label, value, note) {
  return `
    <section class="proactive-summary-card">
      <span>${escapeHtml(label)}</span>
      <b>${escapeHtml(value)}</b>
      <small>${escapeHtml(note)}</small>
    </section>
  `;
}

function proactiveStatusLabel(status) {
  return {
    accepted: "已计划",
    sent: "已发送",
    blocked: "已拦截",
    expired: "已过期",
  }[status] || status || "未知";
}

function renderCreativeProjectCard(item) {
  const current = Number(item.current_chars || 0);
  const target = Number(item.target_chars || 0);
  const pct = target > 0 ? Math.min(100, Math.round((current / target) * 100)) : 0;
  const statusText = {
    drafting: "慢慢写着",
    finished: "已写完",
    paused: "暂时搁置",
  }[item.status] || item.status || "未知";
  const milestones = Array.isArray(item.milestones) && item.milestones.length
    ? item.milestones.map((name) => `<span>${escapeHtml(creativeMilestoneLabel(name))}</span>`).join("")
    : `<span class="muted">还没提起过</span>`;
  return `
    <article class="creative-card">
      <div class="creative-card-head">
        <div>
          <h3>${escapeHtml(item.title || "未定标题")}</h3>
          <p>${escapeHtml(item.premise || "还没整理出一句设定。")}</p>
        </div>
        <span class="badge">${escapeHtml(statusText)}</span>
      </div>
      <div class="creative-progress">
        <div class="meter"><i style="width:${pct}%"></i></div>
        <b>${escapeHtml(current)} / ${escapeHtml(target || "-")} 字</b>
      </div>
      <div class="creative-meta">
        <span>气质：${escapeHtml(item.tone || "-")}</span>
        <span>片段：${escapeHtml(item.chunk_count || 0)}</span>
        <span>创建：${escapeHtml(item.created_at || "-")}</span>
        <span>上次推进：${escapeHtml(item.last_advanced || "-")}</span>
        <span>下次推进：${escapeHtml(item.next_advance || "-")}</span>
      </div>
      ${item.source ? `<p class="creative-source">灵感来源：${escapeHtml(item.source)}</p>` : ""}
      ${item.latest_snippet ? `<blockquote>${escapeHtml(item.latest_snippet)}</blockquote>` : ""}
      <div class="creative-milestones">
        <b>已自然提起节点</b>
        <div>${milestones}</div>
      </div>
    </article>
  `;
}

function creativeMilestoneLabel(name) {
  return {
    opening: "开头",
    midpoint: "过半",
    finished: "完稿",
    impression_question: "询问观感",
  }[name] || name || "节点";
}

function renderDailyTimeline() {
  const timeline = state.overview?.daily_timeline || {};
  const segments = timeline.segments || [];
  if (!segments.length) {
    $("#dailyTimeline").innerHTML = `<div class="empty small">暂无细化时间段。生成今日细化后会展示状态变化。</div>`;
    return;
  }
  $("#dailyTimeline").innerHTML = segments.map((segment) => {
    const vars = (segment.state_variables || []).slice(0, 4);
    const events = (segment.today_events || []).slice(0, 3);
    const presence = segment.presence_status || {};
    return `
      <section class="timeline-item">
        <div class="timeline-time">${escapeHtml(segment.window || segment.key)}</div>
        <div class="timeline-body">
          <div class="timeline-head">
            <b>${escapeHtml(segment.summary || "这一段还没有摘要")}</b>
            <span>${escapeHtml(presenceLabel(presence))}</span>
          </div>
          <div class="state-pills">
            ${vars.length ? vars.map((item) => `
              <span title="${escapeHtml(item.note || "")}">
                <b>${escapeHtml(item.name || "-")}</b>${escapeHtml(item.value || "-")}
              </span>
            `).join("") : `<span>暂无状态变量</span>`}
          </div>
          <ul>
            ${events.length ? events.map((item) => `<li>${escapeHtml(item.window ? `${item.window} · ${item.text}` : item.text)}</li>`).join("") : `<li>暂无细化事件</li>`}
          </ul>
        </div>
      </section>
    `;
  }).join("");
}

function renderInteractionImpact() {
  const timeline = state.overview?.daily_timeline || {};
  const segmentUpdates = [];
  (timeline.segments || []).forEach((segment) => {
    (segment.interaction_updates || []).forEach((item) => {
      segmentUpdates.push({ ...item, window: segment.window });
    });
  });
  const adjustments = (timeline.adjustments || []).map((item) => ({
    at: item.date || "",
    source: item.source,
    reaction: item.reaction || item.note,
    state_updates: item.state_updates || [],
    window: "全局影响",
  }));
  const items = [...segmentUpdates, ...adjustments].filter((item) => item.reaction || item.state_updates?.length);
  if (!items.length) {
    $("#interactionImpact").innerHTML = `<div class="empty small">暂无用户介入影响。用户的关心、提醒、帮助、回应会在这里留下状态偏移。</div>`;
    return;
  }
  $("#interactionImpact").innerHTML = items.slice(-12).reverse().map((item) => `
    <section class="impact-item">
      <div>
        <b>${escapeHtml(item.source || "用户影响")}</b>
        <span>${escapeHtml([item.window, item.at].filter(Boolean).join(" · "))}</span>
      </div>
      <p>${escapeHtml(item.reaction || "")}</p>
      <div class="state-pills">
        ${(item.state_updates || []).map((update) => `<span>${escapeHtml(update)}</span>`).join("")}
      </div>
    </section>
  `).join("");
}

function presenceLabel(presence) {
  const mode = String(presence?.mode || "unchanged");
  const text = presence?.custom_text || presence?.wording || "";
  if (mode === "custom" && text) return `自定义状态：${text}`;
  if (mode === "sleep") return "状态：休息中";
  if (mode === "online") return "状态：在线";
  return "状态：不变";
}

function renderMemoryComposition() {
  const data = {
    "原始记忆": state.users.reduce((sum, user) => sum + Number(user.memory_items || 0), 0),
    "私聊片段": state.users.reduce((sum, user) => sum + Number(user.dialogue_episode_count || 0), 0),
    "未完话头": state.users.reduce((sum, user) => sum + Number(user.open_loop_count || 0), 0),
    "群聊片段": state.groups.reduce((sum, group) => sum + Number(group.episode_count || 0), 0),
    "群聊话题": state.groups.reduce((sum, group) => sum + Number(group.topic_count || 0), 0),
  };
  $("#memoryComposition").innerHTML = donutChart(data);
}

function renderSlangCloud() {
  const counts = new Map();
  state.groups.forEach((group) => {
    (group.slang_terms || []).forEach((item, index) => {
      const term = slangTermText(item);
      if (!term) return;
      counts.set(term, (counts.get(term) || 0) + Math.max(1, 16 - index));
    });
  });
  const entries = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 36);
  if (!entries.length) {
    $("#slangCloud").innerHTML = `<div class="empty small">暂无群聊黑话</div>`;
    return;
  }
  const max = Math.max(1, ...entries.map(([, count]) => count));
  $("#slangCloud").innerHTML = entries.map(([term, count]) => {
    const size = 12 + Math.round((count / max) * 16);
    return `<span style="font-size:${size}px">${escapeHtml(term)}</span>`;
  }).join("");
}

function slangTermText(item) {
  if (typeof item === "string") return item;
  if (!item || typeof item !== "object") return "";
  return String(
    item.term
      || item.word
      || item.text
      || item.name
      || item.key
      || item.phrase
      || item.slang
      || ""
  ).trim();
}

function formatSlangTerms(items) {
  const terms = (Array.isArray(items) ? items : [])
    .map(slangTermText)
    .filter(Boolean);
  return terms.length ? terms.join("、") : "暂无";
}

function renderConfig() {
  const overview = state.overview || {};
  const group = overview.group || {};
  const creative = overview.creative || {};
  const bili = overview.bilibili || {};
  renderDl("#privateConfig", overview.private || {});
  renderDl("#groupConfig", group);
  renderDl("#longTermConfig", {
    "B 站联动": bili.enabled ? "开启" : "关闭",
    "无聊刷视频": bili.boredom_watch_enabled ? "开启" : "关闭",
    "最新视频": bili.latest_video?.title || "暂无",
    "私下创作": creative.enabled ? "开启" : "关闭",
    "创作项目": `${creative.active_projects || 0}/${creative.project_count || 0}`,
    "最新创作": creative.latest_title || "暂无",
  });
  $("#groupAccessMode").value = group.access_mode || "whitelist";
  $("#groupWhitelist").value = (group.whitelist || []).join("\n");
  $("#groupBlacklist").value = (group.blacklist || []).join("\n");
  renderAccessManager(group);
  renderFeatureSwitches();
}

function renderModuleSettings() {
  const settings = state.overview?.settings || {};
  renderModuleSummary(settings);
  fillForm("#quickModuleForm", settings);
  fillForm("#privateModuleForm", settings);
  fillForm("#groupModuleForm", settings);
  fillForm("#worldbookModuleForm", settings);
  fillForm("#memoryModuleForm", settings);
  fillForm("#longTermModuleForm", settings);
  const targetBox = document.querySelector('#quickModuleForm [name="target_user_ids"]');
  if (targetBox) targetBox.value = Array.isArray(settings.target_user_ids) ? settings.target_user_ids.join("\n") : "";
  document.querySelectorAll(".module-form").forEach((form) => markModuleFormClean(form));
  renderPresetCards();
}

function renderModuleSummary(settings) {
  const features = state.overview?.features || {};
  const groups = state.overview?.group || {};
  const cards = [
    {
      label: "私聊主动",
      value: `${settings.max_daily_messages ?? 0}/天`,
      note: `${settings.idle_minutes ?? 0} 分钟空闲后候选`,
      tone: Number(settings.max_daily_messages || 0) > 0 ? "ok" : "off",
    },
    {
      label: "群聊观察",
      value: features.enable_group_companion ? "开启" : "关闭",
      note: `${groups.enabled_group_count || 0}/${groups.group_count || 0} 个群观测中`,
      tone: features.enable_group_companion ? "ok" : "off",
    },
    {
      label: "关系网",
      value: settings.enable_worldbook_member_recognition ? "开启" : "关闭",
      note: `${state.overview?.worldbook?.enabled_member_count || 0}/${state.overview?.worldbook?.member_count || 0} 个节点启用`,
      tone: settings.enable_worldbook_member_recognition ? "ok" : "off",
    },
    {
      label: "记忆整理",
      value: `${settings.memory_refresh_interval_minutes ?? 0} 分钟`,
      note: `片段阈值 ${settings.episode_memory_refresh_messages ?? 0} 条消息`,
      tone: "cost",
    },
    {
      label: "长线行为",
      value: settings.enable_creative_writing ? "创作开启" : "创作关闭",
      note: settings.enable_bilibili_boredom_watch ? "B 站无聊触发开启" : "B 站无聊触发关闭",
      tone: settings.enable_creative_writing || settings.enable_bilibili_boredom_watch ? "ok" : "off",
    },
  ];
  $("#moduleSummary").innerHTML = cards.map((item) => `
    <section class="module-summary-card ${escapeHtml(item.tone)}">
      <span>${escapeHtml(item.label)}</span>
      <b>${escapeHtml(item.value)}</b>
      <small>${escapeHtml(item.note)}</small>
    </section>
  `).join("");
}

function markModuleFormDirty(form) {
  form?.closest(".module-card")?.classList.add("is-dirty");
}

function markModuleFormClean(form) {
  const card = form?.closest(".module-card");
  if (!card) return;
  card.classList.remove("is-dirty");
}

function renderPresetCards() {
  $("#presetCards").innerHTML = Object.entries(presetCatalog).map(([key, preset]) => `
    <section class="preset-card">
      <div>
        <b>${escapeHtml(preset.label)}</b>
        <p>${escapeHtml(preset.desc)}</p>
      </div>
      <button type="button" data-preset="${escapeHtml(key)}">应用</button>
    </section>
  `).join("");
  document.querySelectorAll("[data-preset]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!confirm(`应用“${presetCatalog[button.dataset.preset]?.label || button.dataset.preset}”预设？`)) return;
      await runAction(() => postJson("/preset/apply", { name: button.dataset.preset }));
    });
  });
}

function fillForm(selector, values) {
  const form = $(selector);
  if (!form) return;
  form.querySelectorAll("[name]").forEach((input) => {
    const value = values[input.name];
    if (input.type === "checkbox") {
      input.checked = Boolean(value);
    } else if (Array.isArray(value)) {
      input.value = value.join("\n");
    } else {
      input.value = value ?? "";
    }
  });
}

function collectFormSettings(selector) {
  const form = $(selector);
  const result = {};
  if (!form) return result;
  form.querySelectorAll("[name]").forEach((input) => {
    if (input.type === "checkbox") {
      result[input.name] = input.checked;
    } else if (input.type === "number") {
      result[input.name] = Number(input.value || 0);
    } else {
      result[input.name] = input.value;
    }
  });
  return result;
}

function normalizeGroupIdList(value) {
  const source = Array.isArray(value) ? value.join("\n") : String(value || "");
  const seen = new Set();
  return source
    .split(/[\s,，;；、]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .filter((item) => {
      if (seen.has(item)) return false;
      seen.add(item);
      return true;
    });
}

function accessDraftFromForm(group = {}) {
  const whitelistInput = $("#groupWhitelist");
  const blacklistInput = $("#groupBlacklist");
  return {
    mode: $("#groupAccessMode")?.value || group.access_mode || "whitelist",
    whitelist: new Set(normalizeGroupIdList(whitelistInput ? whitelistInput.value : group.whitelist || [])),
    blacklist: new Set(normalizeGroupIdList(blacklistInput ? blacklistInput.value : group.blacklist || [])),
  };
}

function writeAccessDraft(draft) {
  $("#groupAccessMode").value = draft.mode || "whitelist";
  $("#groupWhitelist").value = [...draft.whitelist].join("\n");
  $("#groupBlacklist").value = [...draft.blacklist].join("\n");
}

function groupAllowedByDraft(groupId, draft) {
  const id = String(groupId || "");
  return draft.mode === "blacklist" ? !draft.blacklist.has(id) : draft.whitelist.has(id);
}

function groupListMark(groupId, draft) {
  const id = String(groupId || "");
  if (draft.whitelist.has(id) && draft.blacklist.has(id)) return "白名单 + 黑名单";
  if (draft.whitelist.has(id)) return "白名单";
  if (draft.blacklist.has(id)) return "黑名单";
  return "未列入";
}

function renderAccessManager(group) {
  const draft = accessDraftFromForm(group);
  const mode = draft.mode === "blacklist" ? "blacklist" : "whitelist";
  $("#groupAccessMode").value = mode;
  document.querySelectorAll("[name='groupAccessModeChoice']").forEach((input) => {
    input.checked = input.value === mode;
  });

  const knownGroups = state.groups || [];
  const allowedCount = knownGroups.filter((item) => groupAllowedByDraft(item.group_id, draft)).length;
  const blockedCount = Math.max(0, knownGroups.length - allowedCount);
  const warning = mode === "whitelist" && draft.whitelist.size === 0
    ? "白名单为空"
    : mode === "blacklist" && draft.blacklist.size === 0
      ? "未拦截群"
      : "已配置";
  $("#accessSummary").innerHTML = `
    <section class="access-summary-card ${mode}">
      <span>当前模式</span>
      <b>${escapeHtml(mode === "blacklist" ? "黑名单" : "白名单")}</b>
      <small>${escapeHtml(warning)}</small>
    </section>
    <section class="access-summary-card ok">
      <span>允许群</span>
      <b>${escapeHtml(allowedCount)}</b>
      <small>已记录群</small>
    </section>
    <section class="access-summary-card blocked">
      <span>拦截群</span>
      <b>${escapeHtml(blockedCount)}</b>
      <small>已记录群</small>
    </section>
    <section class="access-summary-card">
      <span>名单规模</span>
      <b>${escapeHtml(draft.whitelist.size)} / ${escapeHtml(draft.blacklist.size)}</b>
      <small>白名单 / 黑名单</small>
    </section>
  `;

  $("#accessQuickGroups").innerHTML = knownGroups.length
    ? knownGroups.map((item) => {
      const groupId = String(item.group_id || "");
      const inWhite = draft.whitelist.has(groupId);
      const inBlack = draft.blacklist.has(groupId);
      const allowed = groupAllowedByDraft(groupId, draft);
      return `
        <section class="access-group-card ${allowed ? "ok" : "blocked"}">
          <div>
            <b>${escapeHtml(groupId)}</b>
            <span>${escapeHtml(allowed ? "允许" : "拦截")} · ${escapeHtml(groupListMark(groupId, draft))}</span>
            <small>消息 ${escapeHtml(item.message_count || 0)} · 最近 ${escapeHtml(item.last_seen || "未知")}</small>
          </div>
          <div class="access-group-actions">
            <button type="button" data-access-action="white" data-access-group="${escapeHtml(groupId)}">${escapeHtml(inWhite ? "移出白名单" : "加入白名单")}</button>
            <button type="button" data-access-action="black" data-access-group="${escapeHtml(groupId)}">${escapeHtml(inBlack ? "移出黑名单" : "加入黑名单")}</button>
          </div>
        </section>
      `;
    }).join("")
    : `<div class="empty small">暂无群聊记录</div>`;

  renderListCoverage(group, draft);
}

function renderListCoverage(group, draft = null) {
  const access = draft || {
    mode: group.access_mode || "whitelist",
    whitelist: new Set(normalizeGroupIdList(group.whitelist || [])),
    blacklist: new Set(normalizeGroupIdList(group.blacklist || [])),
  };
  const rows = state.groups.map((item) => {
    const groupId = String(item.group_id || "");
    const allowed = groupAllowedByDraft(groupId, access);
    return `
      <div class="coverage-item ${allowed ? "ok" : "blocked"}">
        <b>${escapeHtml(groupId)}</b>
        <span>${escapeHtml(allowed ? "允许" : "拦截")} · ${escapeHtml(groupListMark(groupId, access))}</span>
      </div>
    `;
  });
  $("#listCoverage").innerHTML = rows.length ? rows.join("") : `<div class="empty small">暂无群聊记录</div>`;
}

function renderFeatureSwitches() {
  const filter = ($("#featureFilter")?.value || "").trim().toLowerCase();
  const knownKeys = new Set(featureGroups.flatMap((group) => group.keys));
  const extraKeys = Object.keys(state.featureDraft || {}).filter((key) => !knownKeys.has(key));
  const groups = extraKeys.length
    ? [...featureGroups, { title: "其他", note: "来自配置但暂未归入固定分组的开关。", keys: extraKeys }]
    : featureGroups;
  const total = Object.keys(state.featureDraft || {}).length;
  const enabled = Object.values(state.featureDraft || {}).filter(Boolean).length;
  const riskyEnabled = ["enable_group_interjection", "enable_bilibili_boredom_watch", "enable_unanswered_screen_peek_followup"]
    .filter((key) => state.featureDraft[key]).length;
  $("#featureSwitchSummary").innerHTML = `
    <section class="feature-summary-card ok">
      <span>已开启</span>
      <b>${escapeHtml(enabled)} / ${escapeHtml(total)}</b>
      <small>当前功能开关</small>
    </section>
    <section class="feature-summary-card">
      <span>基础安全项</span>
      <b>${escapeHtml(safeFeatureKeys.filter((key) => state.featureDraft[key]).length)} / ${escapeHtml(safeFeatureKeys.length)}</b>
      <small>隐私、记忆、回复稳定性</small>
    </section>
    <section class="feature-summary-card ${riskyEnabled ? "warn" : ""}">
      <span>高主动项</span>
      <b>${escapeHtml(riskyEnabled)}</b>
      <small>群插话 / 无聊刷视频 / 沉默窥屏</small>
    </section>
  `;

  const board = groups.map((group) => {
    const visibleKeys = group.keys.filter((key) => {
      if (!filter) return true;
      const haystack = `${key} ${featureLabel(key)} ${featureDescription(key)}`.toLowerCase();
      return haystack.includes(filter);
    });
    if (!visibleKeys.length) return "";
    const groupEnabled = visibleKeys.filter((key) => state.featureDraft[key]).length;
    return `
      <section class="feature-switch-group">
        <header>
          <div>
            <b>${escapeHtml(group.title)}</b>
            <span>${escapeHtml(group.note)}</span>
          </div>
          <small>${escapeHtml(groupEnabled)} / ${escapeHtml(visibleKeys.length)}</small>
        </header>
        <div class="feature-switch-list">
          ${visibleKeys.map((key) => featureSwitchItem(key)).join("")}
        </div>
      </section>
    `;
  }).filter(Boolean).join("");
  $("#featureFlags").innerHTML = board || `<div class="empty small">没有匹配的功能开关</div>`;
  document.querySelectorAll("[data-feature-key]").forEach((input) => {
    input.addEventListener("change", () => {
      state.featureDraft[input.dataset.featureKey] = input.checked;
      renderFeatureSwitches();
    });
  });
}

function featureSwitchItem(key) {
  const checked = Boolean(state.featureDraft[key]);
  return `
    <label class="feature-switch-item ${checked ? "on" : "off"}" title="${escapeHtml(featureDescription(key))}">
      <input type="checkbox" data-feature-key="${escapeHtml(key)}" ${checked ? "checked" : ""}>
      <span class="feature-toggle-visual"></span>
      <span class="feature-switch-text">
        <b>${escapeHtml(featureLabel(key))}</b>
        <small>${escapeHtml(key)}</small>
        <em>${escapeHtml(featureDescription(key))}</em>
      </span>
    </label>
  `;
}

function renderProviders() {
  const providers = state.overview?.providers || {};
  renderProviderFlow(providers);
  $("#providerForm").innerHTML = Object.entries(providerLabels).map(([key, label]) => `
    <label class="provider-card">
      <span>${escapeHtml(label)}</span>
      <small>${escapeHtml(providerDescriptions[key] || "选择一个 AstrBot 已配置 Provider，或手动输入 Provider ID。")}</small>
      ${providerSelect(key, providers[key] || "")}
      <span class="provider-row">
        <span class="hint">${escapeHtml(key)}</span>
        <button type="button" data-provider-test="${escapeHtml(key)}">测试</button>
      </span>
      <span class="provider-status" data-provider-status="${escapeHtml(key)}"></span>
    </label>
  `).join("");
  bindProviderTests();
}

function providerSelect(key, value) {
  const known = state.availableProviders.some((item) => item.id === value);
  const customValue = value && !known ? value : "";
  const options = [
    `<option value="">留空自动回退</option>`,
    ...state.availableProviders.map((item) => {
      const label = `${item.name || item.id}${item.model ? ` · ${item.model}` : ""}${item.is_default ? " · 默认" : ""}`;
      return `<option value="${escapeHtml(item.id)}" ${item.id === value ? "selected" : ""}>${escapeHtml(label)}</option>`;
    }),
    `<option value="__custom__" ${customValue ? "selected" : ""}>手动输入 Provider ID</option>`,
  ].join("");
  return `
    <select data-provider-select="${escapeHtml(key)}">${options}</select>
    <input data-provider-key="${escapeHtml(key)}" value="${escapeHtml(value || "")}" placeholder="自定义 Provider ID" ${customValue ? "" : "hidden"} />
  `;
}

function currentProviderValues() {
  const values = {};
  document.querySelectorAll("[data-provider-key]").forEach((input) => {
    values[input.dataset.providerKey] = input.value.trim();
  });
  return values;
}

function resolveProviderId(key, values = currentProviderValues()) {
  if (values[key]) return values[key];
  if (key !== "LLM_PROVIDER_ID" && values.MAI_STYLE_PROVIDER_ID) return values.MAI_STYLE_PROVIDER_ID;
  return values.LLM_PROVIDER_ID || "";
}

function setProviderStatus(key, message, level = "info") {
  const status = document.querySelector(`[data-provider-status="${key}"]`);
  if (!status) return;
  status.className = `provider-status ${level}`;
  status.textContent = message;
}

function bindProviderTests() {
  document.querySelectorAll("[data-provider-select]").forEach((select) => {
    syncProviderInput(select);
    select.addEventListener("change", () => syncProviderInput(select));
  });
  document.querySelectorAll("[data-provider-test]").forEach((button) => {
    button.addEventListener("click", async () => {
      await testProvider(button.dataset.providerTest);
    });
  });
}

function syncProviderInput(select) {
  const key = select.dataset.providerSelect;
  const input = document.querySelector(`[data-provider-key="${key}"]`);
  if (!input) return;
  if (select.value === "__custom__") {
    input.hidden = false;
    input.focus();
  } else {
    input.hidden = true;
    input.value = select.value;
  }
}

async function testProvider(key) {
  const providerId = resolveProviderId(key);
  setProviderStatus(key, "测试中...", "info");
  try {
    const result = await postJson("/provider/test", { key, provider_id: providerId });
    if (result.ok) {
      const suffix = result.sample ? ` · ${result.sample}` : "";
      setProviderStatus(key, `正常 ${result.elapsed_ms}ms${suffix}`, "ok");
    } else {
      setProviderStatus(key, result.error || "未返回内容", "warn");
    }
  } catch (error) {
    setProviderStatus(key, error.message, "warn");
  }
}

function renderProviderFlow(providers) {
  const main = providers.LLM_PROVIDER_ID || "AstrBot 默认模型";
  const mai = providers.MAI_STYLE_PROVIDER_ID || main;
  const tasks = Object.entries(providerLabels).filter(([key]) => key !== "LLM_PROVIDER_ID" && key !== "MAI_STYLE_PROVIDER_ID");
  $("#providerFlow").innerHTML = `
    <div class="flow-lane">
      <span class="flow-node primary">主模型<br><b>${escapeHtml(main)}</b></span>
      <span class="flow-arrow">→</span>
      <span class="flow-node">陪伴通用<br><b>${escapeHtml(mai)}</b></span>
    </div>
    <div class="flow-tasks">
      ${tasks.map(([key, label]) => {
        const value = providers[key] || mai;
        const inherited = !providers[key];
        return `<span class="flow-node ${inherited ? "inherited" : "primary"}">${escapeHtml(label)}<br><b>${escapeHtml(value)}</b></span>`;
      }).join("")}
    </div>
  `;
}

function miniStat(label, value) {
  return `<div class="mini-stat"><b>${escapeHtml(value)}</b><span>${escapeHtml(label)}</span></div>`;
}

function scoreGauge(label, value, min, max) {
  const num = Number(value || 0);
  const pct = Math.max(0, Math.min(100, Math.round(((num - min) / Math.max(1, max - min)) * 100)));
  return `
    <div class="gauge">
      <svg viewBox="0 0 120 64" role="img" aria-label="${escapeHtml(label)}">
        <path d="M16 58 A44 44 0 0 1 104 58" class="gauge-bg"></path>
        <path d="M16 58 A44 44 0 0 1 104 58" class="gauge-fg" pathLength="100" style="stroke-dasharray:${pct} 100"></path>
        <text x="60" y="48" text-anchor="middle">${escapeHtml(num)}</text>
      </svg>
      <span>${escapeHtml(label)}</span>
    </div>
  `;
}

function relationshipGraphSvg(edges) {
  const pairs = Object.entries(edges || {})
    .map(([key, value]) => {
      const parts = key.split(/[-|:>]+/).map((item) => item.trim()).filter(Boolean);
      const weight = Number(value?.count || value?.weight || value || 1);
      return parts.length >= 2 ? { a: parts[0], b: parts[1], weight } : null;
    })
    .filter(Boolean)
    .sort((a, b) => b.weight - a.weight)
    .slice(0, 16);
  if (!pairs.length) return `<div class="empty small">暂无关系边</div>`;

  const names = [...new Set(pairs.flatMap((edge) => [edge.a, edge.b]))].slice(0, 12);
  const center = 120;
  const radius = 76;
  const pos = Object.fromEntries(names.map((name, index) => {
    const angle = (Math.PI * 2 * index) / Math.max(1, names.length) - Math.PI / 2;
    return [name, { x: center + Math.cos(angle) * radius, y: center + Math.sin(angle) * radius }];
  }));
  return `
    <svg class="relation-svg" viewBox="0 0 240 240">
      ${pairs.map((edge) => {
        if (!pos[edge.a] || !pos[edge.b]) return "";
        const width = Math.min(6, 1 + edge.weight / 3);
        return `<line x1="${pos[edge.a].x}" y1="${pos[edge.a].y}" x2="${pos[edge.b].x}" y2="${pos[edge.b].y}" stroke-width="${width}"></line>`;
      }).join("")}
      ${names.map((name) => `
        <g>
          <circle cx="${pos[name].x}" cy="${pos[name].y}" r="18"></circle>
          <text x="${pos[name].x}" y="${pos[name].y + 4}" text-anchor="middle">${escapeHtml(shortName(name, 4))}</text>
        </g>
      `).join("")}
    </svg>
  `;
}

function messageTimelineSvg(messages) {
  const recent = Array.isArray(messages) ? messages.slice(-30) : [];
  if (!recent.length) return `<div class="empty small">暂无最近消息</div>`;
  const buckets = Array.from({ length: 12 }, () => 0);
  const now = Math.floor(Date.now() / 1000);
  recent.forEach((item) => {
    const ts = Number(item.ts || item.time || 0);
    const diffHours = ts ? Math.max(0, Math.min(11, Math.floor((now - ts) / 3600))) : 0;
    buckets[11 - diffHours] += 1;
  });
  const max = Math.max(1, ...buckets);
  return `
    <svg class="timeline-svg" viewBox="0 0 360 120">
      ${buckets.map((value, index) => {
        const height = Math.max(4, Math.round((value / max) * 86));
        const x = 16 + index * 28;
        const y = 100 - height;
        return `<rect x="${x}" y="${y}" width="18" height="${height}" rx="4"></rect>`;
      }).join("")}
      <line x1="12" y1="102" x2="348" y2="102"></line>
      <text x="18" y="116">-12h</text>
      <text x="318" y="116">now</text>
    </svg>
  `;
}

function shortName(value, limit) {
  const text = String(value || "");
  return text.length > limit ? `${text.slice(0, limit)}…` : text;
}

function donutChart(data) {
  const entries = Object.entries(data).filter(([, value]) => Number(value) > 0);
  if (!entries.length) return `<div class="empty small">暂无记忆数据</div>`;
  const total = entries.reduce((sum, [, value]) => sum + Number(value), 0);
  let offset = 0;
  const colors = ["#2f7566", "#8a6f3e", "#4d7ea8", "#a15f26", "#6e7f3f"];
  const circles = entries.map(([label, value], index) => {
    const pct = (Number(value) / total) * 100;
    const circle = `<circle r="42" cx="60" cy="60" pathLength="100" stroke="${colors[index % colors.length]}" stroke-dasharray="${pct} ${100 - pct}" stroke-dashoffset="${-offset}"></circle>`;
    offset += pct;
    return circle;
  }).join("");
  return `
    <div class="donut-wrap">
      <svg class="donut" viewBox="0 0 120 120">
        <circle r="42" cx="60" cy="60" class="donut-bg"></circle>
        ${circles}
        <text x="60" y="64" text-anchor="middle">${escapeHtml(total)}</text>
      </svg>
      <div class="donut-legend">
        ${entries.map(([label, value], index) => `<span><i style="background:${colors[index % colors.length]}"></i>${escapeHtml(label)} ${escapeHtml(value)}</span>`).join("")}
      </div>
    </div>
  `;
}

function detailBlock(title, preText, pairs) {
  const dl = pairs?.length
    ? `<dl>${pairs.map(([key, value]) => `<dt>${escapeHtml(key)}</dt><dd>${escapeHtml(value || "-")}</dd>`).join("")}</dl>`
    : "";
  const pre = preText ? `<pre>${escapeHtml(preText)}</pre>` : "";
  return `<section class="detail-block"><h2>${escapeHtml(title)}</h2>${pre}${dl}</section>`;
}

function renderDl(selector, data) {
  const entries = Object.entries(data || {});
  $(selector).innerHTML = entries.length
    ? entries.map(([key, value]) => `<dt>${escapeHtml(configLabels[key] || key)}</dt><dd>${escapeHtml(formatValue(value))}</dd>`).join("")
    : `<dt>-</dt><dd>暂无数据</dd>`;
}

function featureLabel(key) {
  return featureMeta[key]?.[0] || key.replace(/^enable_/, "");
}

function featureDescription(key) {
  return featureMeta[key]?.[1] || "该功能来自插件配置，可在这里热切换。";
}

function formatValue(value) {
  if (Array.isArray(value)) return value.join(", ");
  if (value && typeof value === "object") return JSON.stringify(value, null, 2);
  return value ?? "";
}

async function runAction(action) {
  try {
    await action();
    await loadAll();
  } catch (error) {
    alert(`操作失败：${error.message}`);
  }
}

function switchTab(tabName) {
  document.querySelectorAll(".tab").forEach((item) => item.classList.toggle("is-active", item.dataset.tab === tabName));
  document.querySelectorAll(".panel").forEach((item) => item.classList.toggle("is-active", item.id === `panel-${tabName}`));
}

document.querySelectorAll(".tab").forEach((button) => {
  button.addEventListener("click", () => {
    switchTab(button.dataset.tab);
  });
});

document.addEventListener("click", (event) => {
  const target = event.target instanceof Element ? event.target.closest("[data-jump-tab]") : null;
  if (!target) return;
  switchTab(target.dataset.jumpTab);
});

$("#refreshBtn").addEventListener("click", loadAll);
$("#userFilter").addEventListener("input", renderUsers);
$("#groupFilter").addEventListener("input", renderGroups);
$("#worldbookMemberFilter").addEventListener("input", renderWorldbook);
$("#featureFilter").addEventListener("input", renderFeatureSwitches);
$("#worldbookImportBtn").addEventListener("click", async () => {
  await runAction(() => postJson("/worldbook/import", {}));
});
$("#worldbookAddMemberForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const userId = String(form.get("user_id") || "").trim();
  if (!userId) return;
  if (!/^\d{5,}$/.test(userId)) {
    alert("关系节点必须使用有效 QQ 号作为身份键");
    return;
  }
  await runAction(() => postJson("/worldbook/member/update", {
    user_id: userId,
    name: form.get("name") || userId,
    priority: Number(form.get("priority") || 120),
    enabled: true,
  }));
  event.currentTarget.reset();
});
$("#worldbookAddGroupForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const groupId = String(form.get("group_id") || "").trim();
  if (!groupId) return;
  await runAction(() => postJson("/worldbook/group/update", {
    group_id: groupId,
    name: form.get("name") || groupId,
    enabled: true,
  }));
  event.currentTarget.reset();
});
$("#resetTokenStatsBtn").addEventListener("click", async () => {
  if (!confirm("确定清空 Token 消耗统计吗？这不会影响聊天记忆和配置。")) return;
  await runAction(() => postJson("/token/reset", {}));
});

["quickModuleForm", "privateModuleForm", "groupModuleForm", "worldbookModuleForm", "memoryModuleForm", "longTermModuleForm"].forEach((formId) => {
  const form = document.getElementById(formId);
  if (!form) return;
  form.addEventListener("input", () => markModuleFormDirty(form));
  form.addEventListener("change", () => markModuleFormDirty(form));
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    await runAction(() => postJson("/settings/update", {
      settings: collectFormSettings(`#${formId}`),
    }));
    markModuleFormClean(form);
  });
});

$("#addUserForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const userId = String(form.get("user_id") || "").trim();
  if (!userId) return;
  state.selectedUserId = userId;
  await runAction(() => postJson("/user/update", {
    user_id: userId,
    enabled: true,
    nickname: form.get("nickname") || "",
  }));
  event.currentTarget.reset();
});

$("#addGroupForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const groupId = String(form.get("group_id") || "").trim();
  const listMode = String(form.get("list_mode") || "none");
  if (!groupId) return;
  state.selectedGroupId = groupId;
  await runAction(async () => {
    await postJson("/group/update", { group_id: groupId, enabled: true });
    if (listMode !== "none") {
      const group = state.overview?.group || {};
      const whitelist = new Set(group.whitelist || []);
      const blacklist = new Set(group.blacklist || []);
      if (listMode === "whitelist") whitelist.add(groupId);
      if (listMode === "blacklist") blacklist.add(groupId);
      await postJson("/settings/update", {
        group_whitelist_ids: [...whitelist],
        group_blacklist_ids: [...blacklist],
      });
    }
  });
  event.currentTarget.reset();
});

$("#exportSnapshotBtn").addEventListener("click", () => {
  const snapshot = {
    exported_at: new Date().toISOString(),
    overview: state.overview,
    users: state.users,
    groups: state.groups,
  };
  const blob = new Blob([JSON.stringify(snapshot, null, 2)], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `private-companion-snapshot-${new Date().toISOString().slice(0, 10)}.json`;
  link.click();
  URL.revokeObjectURL(url);
});

$("#accessForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const draft = accessDraftFromForm(state.overview?.group || {});
  writeAccessDraft(draft);
  await runAction(() => postJson("/settings/update", {
    group_access_mode: draft.mode,
    group_whitelist_ids: [...draft.whitelist],
    group_blacklist_ids: [...draft.blacklist],
  }));
});

$("#groupAccessMode").addEventListener("change", () => {
  renderAccessManager(state.overview?.group || {});
});

document.querySelectorAll("[name='groupAccessModeChoice']").forEach((input) => {
  input.addEventListener("change", () => {
    $("#groupAccessMode").value = input.value;
    renderAccessManager(state.overview?.group || {});
  });
});

$("#accessQuickGroups").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-access-action]");
  if (!button) return;
  const groupId = String(button.dataset.accessGroup || "").trim();
  if (!groupId) return;
  const draft = accessDraftFromForm(state.overview?.group || {});
  const targetSet = button.dataset.accessAction === "black" ? draft.blacklist : draft.whitelist;
  if (targetSet.has(groupId)) {
    targetSet.delete(groupId);
  } else {
    targetSet.add(groupId);
    if (button.dataset.accessAction === "black") {
      draft.whitelist.delete(groupId);
    } else {
      draft.blacklist.delete(groupId);
    }
  }
  writeAccessDraft(draft);
  renderAccessManager(state.overview?.group || {});
  await runAction(() => postJson("/settings/update", {
    group_access_mode: draft.mode,
    group_whitelist_ids: [...draft.whitelist],
    group_blacklist_ids: [...draft.blacklist],
  }));
});

$("#saveFeaturesBtn").addEventListener("click", async () => {
  await runAction(() => postJson("/settings/update", { features: state.featureDraft }));
});

$("#enableSafeFeaturesBtn").addEventListener("click", () => {
  safeFeatureKeys.forEach((key) => {
    if (Object.prototype.hasOwnProperty.call(state.featureDraft, key)) {
      state.featureDraft[key] = true;
    }
  });
  renderFeatureSwitches();
});

$("#saveProvidersBtn").addEventListener("click", async () => {
  const providers = {};
  document.querySelectorAll("[data-provider-key]").forEach((input) => {
    providers[input.dataset.providerKey] = input.value.trim();
  });
  await runAction(() => postJson("/settings/update", { providers }));
});

$("#testAllProvidersBtn").addEventListener("click", async () => {
  for (const key of Object.keys(providerLabels)) {
    await testProvider(key);
  }
});

loadAll();
