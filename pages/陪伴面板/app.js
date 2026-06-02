const HTTP_API = "/astrbot_plugin_private_companion/page";
const PAGE_ENDPOINT_PREFIX = "page";
const TRANSPARENT_IMAGE = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==";

const state = {
  overview: null,
  users: [],
  groups: [],
  diagnostics: [],
  availableProviders: [],
  tokenStats: null,
  bookshelfUnlocked: null,
  selectedBook: null,
  bookshelfPage: "shelf",
  selectedBookSpreadIndex: 0,
  selectedUserId: "",
  selectedGroupId: "",
  featureDraft: {},
  selectedFeatureKey: "",
};

const providerLabels = {
  LLM_PROVIDER_ID: "主模型",
  MAI_STYLE_PROVIDER_ID: "陪伴通用模型",
  DAILY_PLAN_PROVIDER_ID: "日程生成",
  DETAIL_ENHANCEMENT_PROVIDER_ID: "日程细化",
  DREAM_DIARY_PROVIDER_ID: "日记与梦境",
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
  GROUP_FOLLOWUP_JUDGE_PROVIDER_ID: "群聊续接判断",
  FORWARD_MESSAGE_PROVIDER_ID: "合并消息转述",
  PRIVATE_READING_VISION_PROVIDER_ID: "总视觉模型",
  NEWS_PROVIDER_ID: "新闻整理",
  WEB_EXPLORATION_PROVIDER_ID: "网页探索",
};

const privateReadingConfigKeys = new Set([
  "enable_private_reading_integration",
  "enable_private_reading_boredom_read",
  "enable_private_reading_ask_recommendation",
  "private_reading_min_interval_hours",
  "private_reading_max_photo_count",
  "private_reading_share_probability",
  "private_reading_ask_probability",
  "private_reading_default_keywords",
]);

function isPrivateReadingAvailable() {
  return Boolean(state.overview?.private_reading?.available);
}

function visibleConfigKey(key) {
  return isPrivateReadingAvailable() || !privateReadingConfigKeys.has(key);
}

const providerDescriptions = {
  LLM_PROVIDER_ID: "基础兜底模型。主动消息、未指定模型的任务都会向这里回退。",
  MAI_STYLE_PROVIDER_ID: "陪伴风格通用模型。建议选择稳定、便宜、会写自然口语的模型。",
  DAILY_PLAN_PROVIDER_ID: "每天生成粗日程和纠偏重试。适合结构化稳定、能吃人格和世界观的模型。",
  DETAIL_ENHANCEMENT_PROVIDER_ID: "把当前日程段展开成细节事件、状态变量和主动契机。",
  DREAM_DIARY_PROVIDER_ID: "生成每日 Bot 日记、生活碎片、梦境碎片、强化梦境内容和梦后余韵。",
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
  GROUP_FOLLOWUP_JUDGE_PROVIDER_ID: "判断群里用户后续没 @ 的话是否仍在和 Bot 对话。适合便宜、低延迟、YES/NO 分类稳定的小模型；留空只用规则，填写后只在模糊场景调用。",
  FORWARD_MESSAGE_PROVIDER_ID: "合并消息适配方式选择“转述”时使用：先把合并转发读成自然记录，再交给主模型回应。适合长上下文整理稳定、成本较低的模型。",
  PRIVATE_READING_VISION_PROVIDER_ID: "通用视觉理解模型。用于识屏、图片观察、素材封面和抽样页理解等看图任务；适合多模态能力稳定、能准确读图和识别画面文字的模型。",
  NEWS_PROVIDER_ID: "从新闻候选里挑选适合分享的内容，并整理成 Bot 自己的内部印象。适合便宜、稳定、短 JSON 输出可靠的模型。",
  WEB_EXPLORATION_PROVIDER_ID: "让 Bot 自己决定想搜索什么，并把 AstrBot 网页搜索结果整理成探索笔记。适合便宜、稳定、短 JSON 输出可靠的模型。",
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
  enable_semantic_message_debounce: ["语义收口等待", "被唤醒后短暂等待用户补完，把连续几句合成一轮理解。"],
  enable_environment_perception: ["环境感知", "注入当前时间、日期语境、平台、群聊/私聊和消息媒介信息。"],
  enable_holiday_perception: ["节假日感知", "识别工作日、周末、节假日和调休，影响生活节奏判断。"],
  enable_platform_perception: ["平台感知", "识别 QQ/平台、私聊/群聊、群号群名以及图片语音视频消息。"],
  enable_lunar_perception: ["农历感知", "可用时注入农历日期，辅助节日、生活氛围和日记语境。"],
  enable_solar_term_perception: ["节气感知", "注入当天或临近节气，让日程和表达更贴合时令。"],
  enable_almanac_perception: ["轻量黄历", "生成宜/忌氛围标签，默认关闭，避免玄学感太强。"],
  enable_group_companion: ["群聊总开关", "控制是否处理群聊观察、画像、黑话和上下文注入。"],
  enable_group_slang_learning: ["群黑话学习", "记录群内常用梗、简称和特殊表达。"],
  enable_group_member_profiles: ["群成员画像", "记录成员发言习惯和群内角色，帮助判断气氛。"],
  enable_group_context_injection: ["群上下文注入", "在群聊回复时加入群氛围、话题和成员信息。"],
  enable_forward_message_adaptation: ["合并消息阅读", "读取合并转发节点并整理成自然聊天记录，让 Bot 能理解转发里的发言顺序、人物和话题。"],
  enable_group_scene_awareness: ["群聊场景感知", "推断当前消息是在对 Bot、某个群友还是整个群说话，减少误以为别人都在问自己。"],
  enable_group_conversation_followup: ["连续对话保持", "群里叫过 Bot 后，短时间内判断同一用户没继续 @ 的话是否仍在对 Bot 说。"],
  enable_group_interjection: ["群主动插话", "允许 Bot 在群聊里主动插一句。谨慎开启。"],
  enable_group_repeat_follow: ["复读处理", "同一句话连续复读超过三次时，可跟读一次或打断一次。"],
  enable_group_topic_threads: ["群话题线", "维护当前群聊正在聊什么，以及话题如何变化。"],
  enable_group_episode_memory: ["群聊片段", "把群聊阶段性内容整理成摘要片段。"],
  enable_group_interjection_feedback: ["插话反馈", "记录群友对主动插话的反应，后续调整频率。"],
  enable_group_slang_meanings: ["黑话释义", "尝试解释黑话含义，方便后续理解群语境。"],
  enable_group_relationship_graph: ["群关系网", "记录成员之间的互动关系和常见组合。"],
  enable_group_privacy_guard: ["群隐私保护", "避免把私聊记忆和私下关系泄露到群聊。建议开启。"],
  enable_worldbook_member_recognition: ["群聊关系网", "以 QQ 号确认成员身份，昵称和别名只作辅助线索。"],
  enable_atrelay_tools: ["跨群转述与 @ 群友", "整合艾特群友能力，可让模型查询群成员、按关系网解析 @ 对象并发送群聊/私聊消息。"],
  enable_livingmemory_integration: ["LivingMemory 协同", "引导模型按需调用长期记忆工具，避免重复造轮子。"],
  enable_bilibili_integration: ["B 站联动", "读取 B 站 Bot 观看日志，并在合适节点私聊分享。"],
  enable_bilibili_boredom_watch: ["无聊刷 B 站", "空档或无聊时低频触发 B 站 Bot 自己看视频。"],
  enable_news_integration: ["新闻阅读", "低频读取 RSS/Atom 新闻源，形成近期见闻和主动分享素材。"],
  enable_news_boredom_read: ["无聊看新闻", "空档或无聊时扫几条新闻，按人格决定是否私聊提起。"],
  enable_web_exploration: ["主动搜索", "按人格兴趣、最近话题、日程和心情低频使用 AstrBot 网页搜索，形成探索笔记。"],
  enable_web_exploration_boredom_search: ["空档自主搜索", "空闲或无聊时先自行决定搜索主题，再调用网页搜索了解新鲜事物。"],
  enable_qzone_integration: ["QQ 空间动态", "整合查看、点赞、评论和发布说说入口。"],
  enable_qzone_life_publish: ["生活说说", "根据状态、日程和日记余味低频发布公开生活动态。"],
  enable_private_reading_integration: ["夹层阅读素材", "检测到可用素材能力时，允许作为低频私下阅读来源。"],
  enable_private_reading_boredom_read: ["私下阅读", "空档、无聊或夜里低频自己搜索并阅读，形成内部印象。"],
  enable_private_reading_ask_recommendation: ["征求推荐", "空档或无聊时，低频私聊询问用户有没有好看的本子或漫画推荐。"],
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
      "enable_semantic_message_debounce",
    ],
  },
  {
    title: "环境感知",
    note: "时间、节假日、农历节气、平台和消息媒介。",
    keys: [
      "enable_environment_perception",
      "enable_holiday_perception",
      "enable_platform_perception",
      "enable_lunar_perception",
      "enable_solar_term_perception",
      "enable_almanac_perception",
    ],
  },
  {
    title: "群聊观察",
    note: "群氛围、黑话、话题线、插话和隐私边界。",
    keys: [
      "enable_group_companion",
      "enable_group_context_injection",
      "enable_forward_message_adaptation",
      "enable_group_scene_awareness",
      "enable_group_conversation_followup",
      "enable_group_slang_learning",
      "enable_group_slang_meanings",
      "enable_group_member_profiles",
      "enable_group_topic_threads",
      "enable_group_episode_memory",
      "enable_group_relationship_graph",
      "enable_group_interjection",
      "enable_group_repeat_follow",
      "enable_group_interjection_feedback",
      "enable_group_privacy_guard",
    ],
  },
  {
    title: "身份与记忆联动",
    note: "QQ 关系网、外部长期记忆和身份稳定识别。",
    keys: [
      "enable_worldbook_member_recognition",
      "enable_atrelay_tools",
      "enable_livingmemory_integration",
    ],
  },
  {
    title: "长线主动",
    note: "Bot 自己做事、外部动作和低频分享。",
    keys: [
      "enable_bilibili_integration",
      "enable_bilibili_boredom_watch",
      "enable_news_integration",
      "enable_web_exploration",
      "enable_qzone_integration",
      "enable_qzone_life_publish",
      "enable_private_reading_integration",
      "enable_private_reading_boredom_read",
      "enable_private_reading_ask_recommendation",
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
  "enable_semantic_message_debounce",
  "enable_environment_perception",
  "enable_holiday_perception",
  "enable_platform_perception",
  "enable_worldbook_member_recognition",
  "enable_atrelay_tools",
];

const configLabels = {
  enabled_user_count: "启用私聊对象",
  user_count: "私聊对象总数",
  require_opt_in: "是否需要私聊确认",
  max_daily_messages: "每日主动上限",
  inbound_message_debounce_seconds: "用户消息防抖秒数",
  enable_semantic_message_debounce: "语义收口等待",
  semantic_message_debounce_seconds: "收口等待秒数",
  group_conversation_followup_seconds: "群聊续接判断秒数",
  group_conversation_followup_max_turns: "群聊连续续接上限",
  enable_group_conversation_followup: "启用连续对话保持",
  forward_message_mode: "合并消息适配方式",
  forward_message_max_messages: "合并消息最多读取条数",
  forward_message_max_chars: "合并消息注入字数上限",
  forward_message_parse_nested: "展开嵌套合并消息",
  forward_message_image_vision: "合并消息图片视觉",
  forward_message_image_limit: "合并消息视觉图片上限",
  daily_token_limit: "每日 Token 限额",
  worldview_adaptation_mode: "世界观适配模式",
  worldview_adaptation_prompt: "自定义世界观适配",
  environment_perception_timezone: "环境感知时区",
  holiday_country: "节假日地区",
  idle_minutes: "空闲门槛分钟",
  min_interval_minutes: "最小主动间隔分钟",
  check_interval_seconds: "后台检查间隔秒",
  enabled: "群聊总开关",
  group_count: "群记录总数",
  enabled_group_count: "启用群数量",
  access_mode: "名单模式",
  whitelist: "白名单",
  blacklist: "黑名单",
  interjection_enabled: "群主动插话",
  repeat_follow_enabled: "复读跟读",
  group_interject_min_interval_minutes: "群插话最小间隔",
  group_interject_max_daily: "每群每日插话上限",
  group_repeat_follow_probability: "跟读初始概率",
  group_repeat_interrupt_probability: "打断初始概率",
  group_repeat_interrupt_probability_step: "概率共同递增",
  group_repeat_interrupt_text: "打断文本",
  group_repeat_interrupt_image_path: "打断表情包路径",
  group_scene_recent_limit: "场景感知消息数",
  worldbook_auto_import: "启动时刷新关系网",
  worldbook_member_match_aliases: "允许别名辅助匹配",
  worldbook_self_registration: "允许群聊自登记",
  worldbook_auto_pending_observations: "低频待确认观察",
  worldbook_member_inject_limit: "单次注入节点数",
  worldbook_config_paths: "关系网配置路径",
  atrelay_require_worldbook_first: "优先按关系网解析",
  atrelay_member_cache_minutes: "群成员缓存分钟",
  atrelay_sensitive_confirm: "敏感转述确认",
  atrelay_default_relay_style: "默认转述方式",
  atrelay_multi_target_limit: "多目标单次上限",
  memory_refresh_interval_minutes: "长期画像整理间隔",
  max_companion_memory_items: "长期画像条目上限",
  max_learned_expression_items: "表达样本上限",
  episode_memory_refresh_messages: "片段整理消息阈值",
  episode_memory_refresh_minutes: "片段整理时间阈值",
  max_dialogue_episodes: "私聊片段上限",
  bilibili_boredom_min_interval_hours: "B 站触发间隔",
  bilibili_share_probability: "视频分享概率",
  bilibili_share_min_score: "视频分享最低评分",
  news_min_interval_hours: "新闻读取间隔",
  news_share_probability: "新闻分享概率",
  news_max_items_per_source: "单源读取条数",
  news_sources: "新闻源",
  enable_news_daily_hot_read: "每日获取热点",
  news_hot_sources: "热点来源",
  news_hot_max_items: "热点候选数量",
  web_exploration_min_interval_hours: "网页探索间隔",
  web_exploration_share_probability: "探索分享概率",
  web_exploration_max_results: "搜索结果数",
  web_exploration_interests: "探索兴趣倾向",
  qzone_life_publish_min_interval_hours: "说说最小间隔",
  qzone_life_publish_probability: "说说触发概率",
  private_reading_min_interval_hours: "阅读最小间隔",
  private_reading_max_photo_count: "页数上限",
  private_reading_share_probability: "主动提起概率",
  private_reading_default_keywords: "默认搜索关键词",
  private_reading_ask_probability: "征求推荐概率",
  unanswered_screen_peek_after_minutes: "沉默多久后窥屏",
  unanswered_screen_peek_cooldown_minutes: "沉默窥屏冷却",
  creative_inspiration_probability: "创作灵感概率",
  creative_share_probability: "创作透露概率",
  creative_base_chars_per_hour: "基础写作速度",
  creative_max_active_projects: "同时创作项目上限",
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
  web_exploration_query: "探索选题",
  web_exploration_digest: "探索笔记",
  news_digest: "新闻整理",
  creative_project: "创作立项",
  creative_writing: "小说创作",
  photo_prompt: "生图提示",
  screen_narration: "识屏转述",
  private_reading_vision: "夹层视觉",
  voice: "语音文本",
  proactive_framework: "主动主回复",
  voice_framework: "框架语音",
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

function bookshelfImageTag(src, alt) {
  const imageSrc = String(src || "");
  if (!imageSrc) return "";
  return `<img src="${TRANSPARENT_IMAGE}" data-bookshelf-image-src="${escapeHtml(imageSrc)}" alt="${escapeHtml(alt || "书柜图片")}" loading="lazy" />`;
}

function bookshelfImageDataPath(src) {
  const raw = String(src || "");
  if (!raw) return "";
  if (raw.startsWith("data:")) return raw;
  try {
    const url = new URL(raw, window.location.origin);
    if (url.pathname.endsWith("/bookshelf/image")) {
      return `/bookshelf/image_data${url.search}`;
    }
    const marker = "/bookshelf/image?";
    const markerIndex = raw.indexOf(marker);
    if (markerIndex >= 0) {
      return `/bookshelf/image_data?${raw.slice(markerIndex + marker.length)}`;
    }
  } catch (error) {
    const marker = "/bookshelf/image?";
    const markerIndex = raw.indexOf(marker);
    if (markerIndex >= 0) return `/bookshelf/image_data?${raw.slice(markerIndex + marker.length)}`;
  }
  return raw;
}

async function hydrateBookshelfImages(root = document) {
  const images = [...root.querySelectorAll("img[data-bookshelf-image-src]")];
  await Promise.all(images.map(async (img) => {
    if (img.dataset.loaded === "1" || img.dataset.loading === "1") return;
    const source = img.dataset.bookshelfImageSrc || "";
    if (!source) return;
    img.dataset.loading = "1";
    const endpoint = bookshelfImageDataPath(source);
    try {
      if (endpoint.startsWith("data:")) {
        img.src = endpoint;
      } else if (endpoint.startsWith("/bookshelf/image_data")) {
        const result = await fetchJson(endpoint);
        if (result?.data_url) img.src = result.data_url;
      } else {
        img.src = source;
      }
      img.dataset.loaded = "1";
    } catch (error) {
      img.dataset.loaded = "0";
      img.alt = `${img.alt || "书柜图片"}（加载失败）`;
    } finally {
      img.dataset.loading = "0";
    }
  }));
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
  renderBookshelf();
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
    statCard(creative.active_projects || 0, `书柜创作 / 共 ${creative.project_count || 0}`),
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
  renderNewsInsightPanel();
  renderWebExplorationPanel();
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
    ["bookshelf", "书柜", overview.creative?.latest_title || "暂无项目"],
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

function insightStatus(value) {
  const text = String(value || "").trim();
  const labels = {
    read: "已阅读",
    explored: "已搜索",
    no_items: "暂无候选",
    no_results: "无结果",
    digest_failed: "整理失败",
    web_search_disabled_or_unconfigured: "搜索未配置",
  };
  return labels[text] || text || "暂无";
}

function renderNewsInsightPanel() {
  const news = state.overview?.news || {};
  const digest = news.last_digest || {};
  const items = Array.isArray(news.latest_items) ? news.latest_items : [];
  const enabled = Boolean(news.enabled);
  const dailyHot = Boolean(news.daily_hot_enabled);
  const headline = digest.headline || digest.topic || "暂无新闻见闻";
  const impression = digest.impression || (enabled ? "等待下一次日程生成或新闻阅读。" : "新闻阅读未开启。");
  const itemHtml = items.length
    ? items.slice(0, 6).map((item) => `
      <li>
        <span>${escapeHtml(item.source || "来源")}</span>
        <b>${escapeHtml(item.title || "未命名")}</b>
      </li>
    `).join("")
    : `<li class="empty-line">暂无候选记录</li>`;
  $("#newsInsightPanel").innerHTML = `
    <div class="insight-head">
      <div>
        <span class="eyebrow">${enabled ? "新闻阅读" : "未开启"}</span>
        <b>${escapeHtml(headline)}</b>
      </div>
      <small>${escapeHtml(news.last_read_at || "未阅读")}</small>
    </div>
    <p>${escapeHtml(impression)}</p>
    <div class="insight-meta">
      <span>${escapeHtml(insightStatus(news.last_status))}</span>
      <span>${dailyHot ? "每日热点开启" : "每日热点关闭"}</span>
      <span>${news.boredom_read_enabled ? "空档阅读开启" : "空档阅读关闭"}</span>
    </div>
    <ul class="insight-list">${itemHtml}</ul>
  `;
}

function renderWebExplorationPanel() {
  const exploration = state.overview?.web_exploration || {};
  const digest = exploration.last_digest || {};
  const query = exploration.last_query || {};
  const notes = Array.isArray(exploration.recent_notes) ? exploration.recent_notes : [];
  const enabled = Boolean(exploration.enabled);
  const title = digest.topic || query.query || "暂无主动搜索记录";
  const note = digest.note || (enabled ? "等待 Bot 在空档里按兴趣自行搜索。" : "主动搜索未开启。");
  const noteHtml = notes.length
    ? notes.slice().reverse().slice(0, 6).map((item) => `
      <li>
        <span>${escapeHtml(item.created_at || "")}</span>
        <b>${escapeHtml(item.topic || item.query || "探索笔记")}</b>
      </li>
    `).join("")
    : `<li class="empty-line">暂无搜索笔记</li>`;
  $("#webExplorationPanel").innerHTML = `
    <div class="insight-head">
      <div>
        <span class="eyebrow">${enabled ? "主动搜索" : "未开启"}</span>
        <b>${escapeHtml(title)}</b>
      </div>
      <small>${escapeHtml(exploration.last_explore_at || "未搜索")}</small>
    </div>
    <p>${escapeHtml(note)}</p>
    <div class="insight-meta">
      <span>${escapeHtml(insightStatus(exploration.last_status))}</span>
      <span>${exploration.available ? "网页搜索可用" : "网页搜索未配置"}</span>
      <span>${exploration.boredom_search_enabled ? "空档搜索开启" : "空档搜索关闭"}</span>
    </div>
    <ul class="insight-list">${noteHtml}</ul>
  `;
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
  const quotaUsers = state.users.filter((user) => user.is_qq_user);
  const rows = (quotaUsers.length ? quotaUsers : state.users).slice(0, 12).map((user) => {
    const used = Number(user.sent_today || 0);
    const pct = maxDaily > 0 ? Math.min(100, Math.round((used / maxDaily) * 100)) : 0;
    return `
      <div class="meter-row">
        <span title="${escapeHtml(user.user_id || "")}">${escapeHtml(userQuotaLabel(user))}</span>
        <div class="meter"><i style="width:${pct}%"></i></div>
        <b>${escapeHtml(used)}${maxDaily ? `/${escapeHtml(maxDaily)}` : ""}</b>
      </div>
    `;
  });
  $("#quotaChart").innerHTML = rows.length ? rows.join("") : `<div class="empty small">暂无私聊对象</div>`;
}

function userQuotaLabel(user) {
  const id = String(user?.user_id || "");
  if (user?.display_name && !String(user.display_name).startsWith("临时会话")) return user.display_name;
  if (user?.display_name && !user?.is_qq_user) return user.display_name;
  const nickname = String(user?.nickname || "").trim();
  const genericNames = new Set(["用户", "主人", "默认用户"]);
  if (!nickname || genericNames.has(nickname)) return id || "未命名";
  return id ? `${nickname} · ${id.slice(-4)}` : nickname;
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
    ["主动联动", ["enable_unanswered_screen_peek_followup", "enable_bilibili_integration", "enable_bilibili_boredom_watch", "enable_private_reading_integration", "enable_private_reading_boredom_read", "enable_private_reading_ask_recommendation", "enable_creative_writing", "creative_hidden_mode"]],
  ];
  $("#featureMatrix").innerHTML = groups.map(([label, keys]) => `
    <section>
      <h3>${escapeHtml(label)}</h3>
      ${keys.filter(visibleConfigKey).map((key) => `<span class="feature-dot ${state.overview?.features?.[key] ? "on" : "off"}" title="${escapeHtml(key)}">${escapeHtml(key.replace(/^enable_/, ""))}</span>`).join("")}
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
  const budget = stats.budget || {};
  const dailyLimit = Number(budget.limit || 0);
  const dailyUsed = Number(budget.used || 0);
  const exemptUsed = Number(budget.exempt_used || 0);
  const dailyRemaining = budget.remaining == null ? null : Number(budget.remaining || 0);
  $("#tokenSummary").innerHTML = [
    miniStat("总 Token", formatNumber(totalTokens)),
    miniStat("今日用量", dailyLimit > 0 ? `${formatCompactNumber(dailyUsed)} / ${formatCompactNumber(dailyLimit)}` : formatCompactNumber(dailyUsed)),
    miniStat("今日剩余", dailyRemaining == null ? "不限" : formatCompactNumber(dailyRemaining)),
    miniStat("主动消息", formatCompactNumber(exemptUsed)),
    miniStat("调用次数", formatNumber(calls)),
    miniStat("平均 Token", formatNumber(Math.round(Number(totals.avg_tokens || 0)))),
    miniStat("平均延迟", `${formatNumber(Math.round(Number(totals.avg_latency_ms || 0)))} ms`),
    miniStat("估算占比", `${Math.round(estimatedRatio * 100)}%`),
    miniStat("失败次数", formatNumber(errors)),
  ].join("");

  renderTokenChart("#tokenProviderChart", stats.by_provider || [], "暂无 Provider 消耗数据", (item) => item.key || "default");
  renderTokenChart("#tokenTaskChart", stats.by_task || [], "暂无任务消耗数据", (item) => tokenTaskLabel(item.key));
  renderTokenHourlyChart(stats.by_hour || []);
  renderTokenDailyChart(stats.by_day || []);
  renderTokenDailyTable(stats.by_day_detail || stats.by_day || []);
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
    ? tokenHourlySvg(normalized, max)
    : `<div class="empty small">暂无小时趋势数据</div>`;
}

function renderTokenDailyChart(rows) {
  const normalized = rows.slice(-30);
  const max = Math.max(1, ...normalized.map((item) => Number(item.total_tokens || 0)));
  $("#tokenDailyChart").innerHTML = normalized.length
    ? tokenDailySvg(normalized, max)
    : `<div class="empty small">暂无每日统计数据</div>`;
}

function tokenDailySvg(rows, max) {
  const chartHeight = 176;
  const chartTop = 12;
  const chartBottom = 36;
  const axisLeft = 74;
  const rightPad = 18;
  const barStep = 34;
  const width = Math.max(760, axisLeft + rightPad + rows.length * barStep);
  const height = chartHeight + chartTop + chartBottom;
  const plotHeight = chartHeight - chartTop;
  const plotBottom = chartTop + plotHeight;
  const labelStep = Math.max(1, Math.ceil(rows.length / 10));
  const ticks = [1, 0.75, 0.5, 0.25, 0];
  const grid = ticks.map((ratio) => {
    const y = chartTop + (1 - ratio) * plotHeight;
    const value = Math.round(max * ratio);
    return `
      <line class="token-grid-line" x1="${axisLeft}" y1="${y}" x2="${width - rightPad}" y2="${y}"></line>
      <text class="token-axis-label y" x="${axisLeft - 10}" y="${y + 4}">${escapeHtml(formatNumber(value))}</text>
    `;
  }).join("");
  const bars = rows.map((item, index) => {
    const tokens = Number(item.total_tokens || 0);
    const barHeight = Math.max(tokens > 0 ? 4 : 0, Math.round((tokens / max) * (plotHeight - 4)));
    const x = axisLeft + index * barStep + 8;
    const y = plotBottom - barHeight;
    const label = String(item.key || "");
    const labelNode = index % labelStep === 0 || index === rows.length - 1
      ? `<text class="token-axis-label x" x="${x + 8}" y="${height - 8}">${escapeHtml(label.slice(5))}</text>`
      : "";
    return `
      <g class="token-hour-group">
        <title>${escapeHtml(label)} · ${escapeHtml(formatNumber(tokens))} token · ${escapeHtml(item.calls || 0)} 次</title>
        <rect x="${x}" y="${y}" width="18" height="${barHeight}" rx="5"></rect>
        ${labelNode}
      </g>
    `;
  }).join("");
  return `
    <svg class="token-hourly-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="每日 Token 消耗趋势">
      <line class="token-axis-line" x1="${axisLeft}" y1="${chartTop}" x2="${axisLeft}" y2="${plotBottom}"></line>
      <line class="token-axis-line" x1="${axisLeft}" y1="${plotBottom}" x2="${width - rightPad}" y2="${plotBottom}"></line>
      ${grid}
      ${bars}
    </svg>
  `;
}

function tokenHourlySvg(rows, max) {
  const chartHeight = 176;
  const chartTop = 12;
  const chartBottom = 34;
  const axisLeft = 74;
  const rightPad = 18;
  const barStep = 30;
  const width = Math.max(760, axisLeft + rightPad + rows.length * barStep);
  const height = chartHeight + chartTop + chartBottom;
  const plotHeight = chartHeight - chartTop;
  const plotBottom = chartTop + plotHeight;
  const labelStep = Math.max(1, Math.ceil(rows.length / 12));
  const ticks = [1, 0.75, 0.5, 0.25, 0];
  const grid = ticks.map((ratio) => {
    const y = chartTop + (1 - ratio) * plotHeight;
    const value = Math.round(max * ratio);
    return `
      <line class="token-grid-line" x1="${axisLeft}" y1="${y}" x2="${width - rightPad}" y2="${y}"></line>
      <text class="token-axis-label y" x="${axisLeft - 10}" y="${y + 4}">${escapeHtml(formatNumber(value))}</text>
    `;
  }).join("");
  const bars = rows.map((item, index) => {
      const tokens = Number(item.total_tokens || 0);
    const barHeight = Math.max(tokens > 0 ? 4 : 0, Math.round((tokens / max) * (plotHeight - 4)));
      const label = formatHourKey(item.key);
    const x = axisLeft + index * barStep + 7;
    const y = plotBottom - barHeight;
    const labelNode = index % labelStep === 0 || index === rows.length - 1
      ? `<text class="token-axis-label x" x="${x + 8}" y="${height - 8}">${escapeHtml(label.slice(-5))}</text>`
      : "";
      return `
      <g class="token-hour-group">
        <title>${escapeHtml(label)} · ${escapeHtml(formatNumber(tokens))} token · ${escapeHtml(item.calls || 0)} 次</title>
        <rect x="${x}" y="${y}" width="16" height="${barHeight}" rx="5"></rect>
        ${labelNode}
      </g>
      `;
  }).join("");
  return `
    <svg class="token-hourly-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="近 48 小时 Token 消耗趋势">
      <line class="token-axis-line" x1="${axisLeft}" y1="${chartTop}" x2="${axisLeft}" y2="${plotBottom}"></line>
      <line class="token-axis-line" x1="${axisLeft}" y1="${plotBottom}" x2="${width - rightPad}" y2="${plotBottom}"></line>
      ${grid}
      ${bars}
    </svg>
  `;
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

function renderTokenDailyTable(rows) {
  $("#tokenDailyTable").innerHTML = tokenTable(
    ["日期", "总 Token", "调用", "失败", "主要任务", "主要 Provider"],
    rows.slice().reverse(),
    (item) => [
      item.key || "-",
      formatNumber(item.total_tokens),
      formatNumber(item.calls),
      formatNumber(item.errors),
      tokenTopList(item.tasks, tokenTaskLabel),
      tokenTopList(item.providers, (key) => key || "default"),
    ],
    "暂无每日明细"
  );
}

function tokenTopList(rows, labeler) {
  if (!Array.isArray(rows) || !rows.length) return "-";
  return rows.slice(0, 3).map((item) => `${labeler(item.key)} ${formatCompactNumber(item.total_tokens)}`).join(" / ");
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
        <td><strong>${escapeHtml(user.display_name || user.nickname || user.user_id)}</strong>${user.is_qq_user ? "" : ` <span class="badge off">非 QQ</span>`}<br><span class="muted">${escapeHtml(user.user_id)}</span></td>
        <td><span class="badge ${user.enabled ? "" : "off"}">${escapeHtml(user.enabled ? "启用" : "停用")}</span> <span class="muted">${escapeHtml(user.relationship_stage || "未分层")}</span><br><span>分数 ${escapeHtml(user.relationship_score)}</span></td>
        <td>入站 ${escapeHtml(user.inbound_count)} · 回复 ${escapeHtml(user.reply_count)}<br><span class="muted">记忆 ${escapeHtml(user.memory_items)} 条</span></td>
        <td>今日 ${escapeHtml(user.sent_today)} · 总计 ${escapeHtml(user.proactive_sent_count)}<br><span class="muted">${escapeHtml(user.next_proactive)}</span></td>
        <td>${escapeHtml(user.last_seen)}<br><span class="muted">上次主动 ${escapeHtml(user.last_sent)}</span></td>
        <td><button type="button" class="table-action ${user.enabled ? "danger-outline" : ""}" data-user-toggle="${escapeHtml(user.user_id)}">${escapeHtml(user.enabled ? "停用" : "启用")}</button></td>
      </tr>
    `).join("")
    : `<tr><td class="empty" colspan="6">暂无私聊对象</td></tr>`;
  document.querySelectorAll("[data-user-toggle]").forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.stopPropagation();
      const user = state.users.find((item) => item.user_id === button.dataset.userToggle);
      if (!user) return;
      await runAction(() => postJson("/user/update", {
        user_id: user.user_id,
        enabled: !user.enabled,
      }), !user.enabled ? "已启用私聊对象" : "已停用私聊对象", button);
    });
  });
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
    }), "已保存私聊对象", event.submitter);
  });
  document.querySelectorAll("[data-user-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      const action = button.dataset.userAction;
      const body = { user_id: detail.user_id };
      if (action === "toggle") body.enabled = !detail.enabled;
      if (action === "reset_daily") body.reset_daily = true;
      if (action === "clear_schedule") body.clear_schedule = true;
      if (action === "clear_learning") {
        if (!requireSecondClick(button, `user-clear:${detail.user_id}`, "再次点击清空该用户的学习记忆", "再次点击清空")) return;
        body.clear_learning = true;
      }
      await runAction(() => postJson("/user/update", body), "已更新私聊对象", button);
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
      <section class="detail-block wide"><h2>关系网</h2>${relationshipGraphView(detail.relationship_edges || {}, detail.members || {})}</section>
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
      if (action === "clear_observation") {
        if (!requireSecondClick(button, `group-clear:${detail.group_id}`, "再次点击清空该群的观测数据", "再次点击清空")) return;
        body.clear_observation = true;
      }
      await runAction(() => postJson("/group/update", body), "已更新群聊观测", button);
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
  const pending = Array.isArray(item.pending_observations) ? item.pending_observations : [];
  const chips = [...aliases.map((name) => `别名：${name}`), ...observed.map((name) => `群名片：${name}`)].slice(0, 12);
  const sourceEntries = Array.isArray(item.source_entries) ? item.source_entries : [];
  const detailId = `worldbook-editor-${String(item.user_id || "").replace(/[^A-Za-z0-9_-]/g, "_")}`;
  const previewItems = worldbookMemberPreviewItems(item, memories);
  return `
    <section class="worldbook-member-card ${item.enabled ? "" : "off"}" data-worldbook-user-id="${escapeHtml(item.user_id || "")}">
      <div class="worldbook-member-head">
        <div>
          <b>${escapeHtml(item.name || item.user_id || "未命名成员")}</b>
          <span>身份 QQ ${escapeHtml(item.user_id || "-")} · 优先级 ${escapeHtml(item.priority ?? "-")}</span>
        </div>
        <div class="worldbook-card-actions">
          <button type="button" data-worldbook-edit="${escapeHtml(detailId)}">编辑</button>
          <button type="button" data-worldbook-member="${escapeHtml(item.user_id || "")}" data-enabled="${item.enabled ? "0" : "1"}">
            ${escapeHtml(item.enabled ? "停用" : "启用")}
          </button>
          <button type="button" data-worldbook-delete="${escapeHtml(item.user_id || "")}" class="danger-outline">删除</button>
        </div>
      </div>
      <div class="worldbook-compact-meta">
        <span>${escapeHtml(aliases.length)} 个别名</span>
        <span>${escapeHtml(observed.length)} 个曾见群名片</span>
        <span>${escapeHtml((item.important_memories || []).length)} 条记忆</span>
        ${pending.length ? `<span>${escapeHtml(pending.length)} 条待确认观察</span>` : ""}
        ${sourceEntries.length ? `<span>${escapeHtml(sourceEntries.slice(0, 2).join(" / "))}</span>` : ""}
      </div>
      ${previewItems.length ? `
        <div class="worldbook-member-preview-list">
          ${previewItems.map(([label, value]) => `
            <p><b>${escapeHtml(label)}</b><span>${escapeHtml(value)}</span></p>
          `).join("")}
        </div>
      ` : ""}
      <details class="worldbook-editor" id="${escapeHtml(detailId)}">
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
          ${pending.length ? pending.map((obs) => worldbookPendingObservationCard(item.user_id || "", obs)).join("") : ""}
          ${memories.length ? memories.map((memory, index) => worldbookMemoryCard(item.user_id || "", memory, index)).join("") : `<div class="empty small">暂无重要记忆</div>`}
        </div>
        <div class="worldbook-editor-actions">
          <button type="button" data-worldbook-save="${escapeHtml(item.user_id || "")}">保存关系节点</button>
          <button type="button" data-worldbook-delete="${escapeHtml(item.user_id || "")}" class="danger-outline">删除节点</button>
        </div>
      </details>
    </section>
  `;
}

function worldbookPendingObservationCard(userId, obs) {
  return `
    <section class="worldbook-memory-card pending">
      <div>
        <b>${escapeHtml(obs.title || "待确认观察")}</b>
        <p>${escapeHtml(obs.content || obs.evidence || "")}</p>
        <span>${escapeHtml(obs.group_id ? `群 ${obs.group_id}` : "群聊观察")} · ${escapeHtml(obs.created_at || "")}${obs.count > 1 ? ` · ${escapeHtml(obs.count)} 次` : ""}</span>
      </div>
      <div class="actions compact">
        <button type="button" data-worldbook-observation-accept="${escapeHtml(userId)}" data-observation-id="${escapeHtml(obs.id || "")}">确认</button>
        <button type="button" class="danger-outline" data-worldbook-observation-reject="${escapeHtml(userId)}" data-observation-id="${escapeHtml(obs.id || "")}">忽略</button>
      </div>
    </section>
  `;
}

function worldbookMemberPreviewItems(item, memories = []) {
  const rows = [];
  const add = (label, value, limit = 120) => {
    const text = shortName(String(value || "").trim(), limit);
    if (text && !rows.some(([, existing]) => existing === text)) rows.push([label, text]);
  };
  add("资料", item.content || item.note, 130);
  add("身份", item.identity_note, 120);
  add("边界", item.boundary_note, 110);
  const memory = memories.find((entry) => entry && entry.enabled !== false && String(entry.content || "").trim());
  if (memory) add("记忆", `${memory.title ? `${memory.title}：` : ""}${memory.content || ""}`, 120);
  return rows.slice(0, 4);
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

async function handleWorldbookMemberAction(button) {
  const editTarget = button.dataset.worldbookEdit;
  if (editTarget) {
    const details = document.getElementById(editTarget);
    if (details) {
      details.open = true;
      details.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
    return;
  }
  if (button.dataset.worldbookMember !== undefined) {
    const userId = button.dataset.worldbookMember;
    if (!userId) return;
    await runAction(() => postJson("/worldbook/member/update", {
      user_id: userId,
      enabled: button.dataset.enabled === "1",
    }), button.dataset.enabled === "1" ? "已启用关系节点" : "已停用关系节点", button);
    return;
  }
  if (button.dataset.worldbookSave !== undefined) {
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
    }), "已保存关系节点", button);
    return;
  }
  if (button.dataset.worldbookMemoryToggle !== undefined) {
    const userId = button.dataset.worldbookMemoryToggle;
    const index = Number(button.dataset.memoryIndex || -1);
    const member = getWorldbookMember(userId);
    const memories = Array.isArray(member?.important_memories) ? member.important_memories.map((item) => ({ ...item })) : [];
    if (!userId || index < 0 || index >= memories.length) return;
    memories[index].enabled = memories[index].enabled === false;
    await runAction(() => postJson("/worldbook/member/update", { user_id: userId, important_memories: memories }), "已更新重要记忆", button);
    return;
  }
  if (button.dataset.worldbookMemoryDelete !== undefined) {
    const userId = button.dataset.worldbookMemoryDelete;
    const index = Number(button.dataset.memoryIndex || -1);
    const member = getWorldbookMember(userId);
    const memories = Array.isArray(member?.important_memories) ? member.important_memories.map((item) => ({ ...item })) : [];
    if (!userId || index < 0 || index >= memories.length) return;
    memories.splice(index, 1);
    await runAction(() => postJson("/worldbook/member/update", { user_id: userId, important_memories: memories }), "已删除重要记忆", button);
    return;
  }
  if (button.dataset.worldbookObservationAccept !== undefined || button.dataset.worldbookObservationReject !== undefined) {
    const accepting = button.dataset.worldbookObservationAccept !== undefined;
    const userId = accepting ? button.dataset.worldbookObservationAccept : button.dataset.worldbookObservationReject;
    const observationId = button.dataset.observationId || "";
    if (!userId || !observationId) return;
    await runAction(() => postJson("/worldbook/member/update", {
      user_id: userId,
      [accepting ? "accept_pending_observation_id" : "reject_pending_observation_id"]: observationId,
    }), accepting ? "已写入重要记忆" : "已忽略待确认观察", button);
    return;
  }
  if (button.dataset.worldbookDelete !== undefined) {
    const userId = button.dataset.worldbookDelete || button.closest("[data-worldbook-user-id]")?.dataset.worldbookUserId || "";
    if (!userId) {
      showToast("没有找到要删除的关系节点 ID", "error");
      return;
    }
    const now = Date.now();
    const armed = button.dataset.deleteArmed === userId && now - Number(button.dataset.deleteArmedAt || 0) < 6000;
    if (!armed) {
      button.dataset.deleteArmed = userId;
      button.dataset.deleteArmedAt = String(now);
      button.dataset.originalText = button.textContent || "删除";
      button.textContent = "再次点击删除";
      showToast(`再次点击删除关系节点 ${userId}`);
      window.clearTimeout(button._deleteArmedTimer);
      button._deleteArmedTimer = window.setTimeout(() => {
        if (button.dataset.deleteArmed === userId) {
          delete button.dataset.deleteArmed;
          delete button.dataset.deleteArmedAt;
          button.textContent = button.dataset.originalText || "删除";
          delete button.dataset.originalText;
        }
      }, 6000);
      return;
    }
    delete button.dataset.deleteArmed;
    delete button.dataset.deleteArmedAt;
    await runAction(() => postJson("/worldbook/member/update", { user_id: userId, delete: true }), "已删除关系节点", button);
  }
}

function findWorldbookField(field, id) {
  return [...document.querySelectorAll(`[data-worldbook-${field}]`)]
    .find((item) => item.getAttribute(`data-worldbook-${field}`) === id);
}

function findWorldbookGroupField(field, id) {
  return [...document.querySelectorAll(`[data-worldbook-group-${field}]`)]
    .find((item) => item.getAttribute(`data-worldbook-group-${field}`) === id);
}

async function handleWorldbookGroupAction(button) {
  if (button.dataset.worldbookGroupSave !== undefined) {
    const groupId = button.dataset.worldbookGroupSave;
    if (!groupId) return;
    await runAction(() => postJson("/worldbook/group/update", {
      group_id: groupId,
      name: findWorldbookGroupField("name", groupId)?.value || "",
      priority: Number(findWorldbookGroupField("priority", groupId)?.value || 110),
      content: findWorldbookGroupField("content", groupId)?.value || "",
    }), "已保存群资料", button);
    return;
  }
  if (button.dataset.worldbookGroupDelete !== undefined) {
    const groupId = button.dataset.worldbookGroupDelete;
    if (!groupId) return;
    const now = Date.now();
    const armed = button.dataset.deleteArmed === groupId && now - Number(button.dataset.deleteArmedAt || 0) < 6000;
    if (!armed) {
      button.dataset.deleteArmed = groupId;
      button.dataset.deleteArmedAt = String(now);
      button.dataset.originalText = button.textContent || "删除";
      button.textContent = "再次点击删除";
      showToast(`再次点击删除群资料 ${groupId}`);
      window.clearTimeout(button._deleteArmedTimer);
      button._deleteArmedTimer = window.setTimeout(() => {
        if (button.dataset.deleteArmed === groupId) {
          delete button.dataset.deleteArmed;
          delete button.dataset.deleteArmedAt;
          button.textContent = button.dataset.originalText || "删除";
          delete button.dataset.originalText;
        }
      }, 6000);
      return;
    }
    delete button.dataset.deleteArmed;
    delete button.dataset.deleteArmedAt;
    await runAction(() => postJson("/worldbook/group/update", { group_id: groupId, delete: true }), "已删除群资料", button);
  }
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
  $("#lifeLocation").textContent = normalizeLocationText(daily.location);
  $("#lifeWeather").textContent = daily.weather || "暂无天气";
  const current = life.current_plan || {};
  $("#lifeCurrentActivity").textContent = current.activity || "暂无当前日程";
  $("#lifeCurrentSeed").textContent = [current.time, current.mood, current.message_seed].filter(Boolean).join(" · ") || "等待日程细化";
}

function normalizeLocationText(value) {
  const text = String(value || "").trim();
  if (!text || text === "地点感平稳") return "地点无明显变化";
  return text;
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
    ["睡眠阶段", daily.sleep_phase || daily.sleep_runtime?.label],
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
          <p>${escapeHtml(item.body || item.summary || "暂无日记正文")}</p>
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

function renderBookshelf() {
  const creative = state.overview?.creative || {};
  const bookshelf = state.bookshelfUnlocked || state.overview?.bookshelf || {};
  const privateReading = state.overview?.private_reading || {};
  const settings = state.overview?.settings || {};
  $("#bookshelfPublicCount").textContent = bookshelf.public_count ?? creative.project_count ?? 0;
  $("#bookshelfSecretCount").textContent = bookshelf.secret_count ?? 0;
  $("#bookshelfDiaryCount").textContent = bookshelf.diary_count ?? 0;
  $("#bookshelfJmCount").textContent = bookshelf.jm_album_count ?? 0;
  $("#bookshelfLockState").textContent = bookshelf.unlocked ? "已解锁" : "未解锁";
  $("#bookshelfIntro").textContent = creative.enabled
    ? "这些书不是一次写完的成品，而是 Bot 按自己的节奏从日程、日记、梦境或生活小事里慢慢写出来的。"
    : "创作当前未开启。开启后，新的项目会像书一样摆到上层书架。";
  const creativeSettings = {
    "创作": creative.enabled ? "开启" : "关闭",
    "提起方式": creative.hidden_mode ? "节点自然提起" : "普通模式",
    "灵感触发概率": formatPercent(settings.creative_inspiration_probability),
    "节点提起概率": formatPercent(settings.creative_share_probability),
    "写作速度": `${settings.creative_base_chars_per_hour || 0} 字/小时`,
  };
  if (privateReading.available) {
    creativeSettings["夹层阅读"] = privateReading.boredom_read_enabled ? "可触发" : "关闭";
    creativeSettings["征求推荐"] = privateReading.ask_recommendation_enabled ? "可触发" : "关闭";
  }
  renderDl("#creativeSettings", creativeSettings);
  const publicBooks = bookshelf.public_books || [];
  $("#bookshelfPublicBooks").innerHTML = publicBooks.length
    ? publicBooks.slice().reverse().map(renderBookshelfBook).join("")
    : `<div class="empty">上层书架还是空的。等某个生活片段或梦境变成灵感时，这里会多出一本书。</div>`;
  const secretBooks = bookshelf.secret_books || [];
  $("#bookshelfSecretBooks").innerHTML = bookshelf.unlocked
    ? renderUnlockedDrawer(secretBooks)
    : renderLockedDrawer(bookshelf.secret_count || 0);
  const home = $("#bookcaseHome");
  if (home) home.hidden = state.bookshelfPage !== "shelf";
  renderBookDetailPanel();
  void hydrateBookshelfImages(document);
}

function renderLockedDrawer(count) {
  return `
    <div class="drawer-locked">
      <div class="drawer-face">
        <span></span>
        <i></i>
      </div>
      <div>
        <b>${escapeHtml(count || 0)} 本锁在夹层里</b>
        <p>日记本和夹层藏书不会直接展示。密码要在聊天里自然向 Bot 询问。</p>
      </div>
    </div>
  `;
}

function renderUnlockedDrawer(items) {
  if (!items.length) {
    return `<div class="empty small">抽屉已经打开，但里面暂时还没有日记本或夹层藏书。</div>`;
  }
  const diaryBooks = items.filter((item) => item.kind === "diary");
  const browsingBooks = items.filter((item) => item.kind === "browsing");
  const privateBooks = items.filter((item) => item.kind !== "diary" && item.kind !== "browsing");
  const groups = [
    ["日记本", diaryBooks, "按日期收进同一本里"],
    ["浏览记录", browsingBooks, "新闻阅读和主动搜索的留痕"],
    ["夹层藏书", privateBooks, "只保留标题和阅读印象"],
  ].filter(([, books]) => books.length);
  return groups.map(([title, books, note]) => `
    <section class="drawer-book-group">
      <header>
        <span>${escapeHtml(title)}</span>
        <small>${escapeHtml(note)}</small>
      </header>
      <div class="drawer-book-row">${books.slice().reverse().map(renderBookshelfBook).join("")}</div>
    </section>
  `).join("");
}

function renderBookshelfBook(item) {
  const kind = item.kind || "creative";
  const kindLabel = {
    creative: "创作",
    diary: "日记本",
    browsing: "浏览记录",
    jm_album: "夹层藏书",
  }[kind] || kind;
  const bookId = bookshelfBookId(item);
  return `
    <button type="button" class="shelf-book ${escapeHtml(kind)}" data-book-id="${escapeHtml(bookId)}">
      <div class="book-spine">
        <span>${escapeHtml(kindLabel)}</span>
        <b>${escapeHtml(item.title || "未命名")}</b>
      </div>
    </button>
  `;
}

function bookshelfBookId(item) {
  return `${item.kind || "book"}:${item.id || item.title || ""}`;
}

function renderBookCoverInner(book, kindLabel, title, progress = "") {
  const coverSrc = book.kind === "jm_album" ? String(book.cover_src || "") : "";
  const image = coverSrc ? bookshelfImageTag(coverSrc, `${title || "夹层藏书"}封面`) : "";
  return `
    ${image}
    <span>${escapeHtml(kindLabel)}</span>
    <b>${escapeHtml(title || "未命名")}</b>
    ${progress ? `<small>${escapeHtml(progress)}</small>` : ""}
  `;
}

function allBookshelfBooks() {
  const bookshelf = state.bookshelfUnlocked || state.overview?.bookshelf || {};
  return [
    ...(bookshelf.public_books || []),
    ...(bookshelf.secret_books || []),
  ];
}

function selectBookshelfBook(bookId) {
  const book = allBookshelfBooks().find((item) => bookshelfBookId(item) === bookId);
  if (!book) return;
  state.selectedBook = book;
  state.bookshelfPage = "detail";
  state.selectedBookSpreadIndex = 0;
  renderBookDetailPanel();
  const panel = $("#bookDetailPanel");
  if (panel) panel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderBookDetailPanel() {
  const panel = $("#bookDetailPanel");
  if (!panel) return;
  const book = state.selectedBook;
  if (!book || state.bookshelfPage === "shelf") {
    panel.hidden = true;
    panel.innerHTML = "";
    return;
  }
  const kindLabel = {
    creative: "创作书",
    diary: "日记本",
    browsing: "浏览记录",
    jm_album: "夹层藏书",
  }[book.kind] || "书";
  const entryBook = ["diary", "browsing"].includes(book.kind || "");
  const diaryEntries = entryBook && Array.isArray(book.entries) ? book.entries : [];
  const selectedDiaryDate = state.selectedDiaryDate || diaryEntries[diaryEntries.length - 1]?.date || "";
  const diaryEntry = diaryEntries.find((entry) => entry.date === selectedDiaryDate) || diaryEntries[diaryEntries.length - 1] || null;
  if (entryBook && diaryEntry && state.selectedDiaryDate !== diaryEntry.date) {
    state.selectedDiaryDate = diaryEntry.date;
  }
  const displayTitle = entryBook && diaryEntry
    ? (book.kind === "diary" ? `${diaryEntry.date} 的日记` : (diaryEntry.title || diaryEntry.date || "浏览记录"))
    : (book.title || "未命名");
  const displayIntro = entryBook && diaryEntry ? (diaryEntry.intro || book.intro) : (book.intro || book.progress || "这本书还没有简介。");
  const displayContent = entryBook && diaryEntry ? (diaryEntry.content || diaryEntry.intro || book.content) : (book.content || book.intro || "这本书暂时没有正文。");
  const diarySelector = diaryEntries.length
    ? `
      <label class="diary-date-picker">
        <span>${book.kind === "diary" ? "日期" : "记录"}</span>
        <select data-diary-date>
          ${diaryEntries.slice().reverse().map((entry) => `<option value="${escapeHtml(entry.date)}"${entry.date === state.selectedDiaryDate ? " selected" : ""}>${escapeHtml(entry.date)}</option>`).join("")}
        </select>
      </label>
    `
    : "";
  const activeTags = entryBook && diaryEntry ? diaryEntry.tags : book.tags;
  const tags = Array.isArray(activeTags) && activeTags.length
    ? `<div class="book-tags">${activeTags.map((tag) => `<span>${escapeHtml(tag)}</span>`).join("")}</div>`
    : "";
  const readingImpressionText = book.kind === "jm_album"
    ? String(book.reading_impression || book.content || displayIntro || "").replace(/^读后感[:：]\s*/, "").trim()
    : "";
  const readingImpression = readingImpressionText
    ? `
      <section class="book-reading-impression">
        <span>Bot 的读后感</span>
        <p>${escapeHtml(readingImpressionText)}</p>
      </section>
    `
    : "";
  const manageActions = book.kind === "browsing" ? "" : `
    <div class="book-manage-actions">
      <button type="button" class="danger-outline" data-book-delete
        data-book-kind="${escapeHtml(book.kind || "")}"
        data-book-id="${escapeHtml(book.id || "")}"
        data-book-album-id="${escapeHtml(book.album_id || "")}"
        data-book-title="${escapeHtml(book.title || "")}"
        data-book-date="${escapeHtml(book.kind === "diary" ? (state.selectedDiaryDate || "") : "")}">
        ${escapeHtml(book.kind === "diary" ? "删除当前日记" : "从书柜移除")}
      </button>
    </div>
  `;
  panel.hidden = false;
  if (state.bookshelfPage === "reader" && book.kind === "jm_album" && Array.isArray(book.pages) && book.pages.length) {
    panel.innerHTML = renderJmAlbumReader(book, kindLabel, displayTitle, displayIntro, readingImpression);
    void hydrateBookshelfImages(panel);
    return;
  }
  panel.innerHTML = state.bookshelfPage === "reader"
    ? `
      <article class="reader-page subpage ${escapeHtml(book.kind || "book")}">
        <nav class="book-breadcrumb">
          <button type="button" data-book-close>书柜</button>
          <span>/</span>
          <button type="button" data-book-back>${escapeHtml(book.title || "未命名")}</button>
          <span>/ 阅读</span>
        </nav>
        <div class="reader-toolbar">
          <button type="button" data-book-back>返回简介</button>
          <span>${escapeHtml(kindLabel)}</span>
          <button type="button" data-book-close>收回书柜</button>
        </div>
        <div class="reader-book-shell">
          <aside class="reader-cover ${book.cover_src ? "has-cover-image" : ""}">
            ${renderBookCoverInner(book, kindLabel, displayTitle, book.progress || "")}
          </aside>
          <section class="reader-paper">
            <header class="reader-page-head">
              <span>${escapeHtml(kindLabel)}</span>
              <h2>${escapeHtml(displayTitle)}</h2>
              ${displayIntro ? `<p>${escapeHtml(displayIntro)}</p>` : ""}
            </header>
            <div class="reader-content">${formatBookContent(displayContent || "这本书暂时没有正文。")}</div>
            <footer class="reader-page-foot">
              <span>${escapeHtml(book.created || "书柜藏本")}</span>
              <span>${escapeHtml(book.tone || book.status || "")}</span>
            </footer>
          </section>
        </div>
      </article>
    `
    : `
      <article class="book-preview subpage ${escapeHtml(book.kind || "book")}">
        <div class="book-preview-cover ${book.cover_src ? "has-cover-image" : ""}">
          ${renderBookCoverInner(book, kindLabel, book.title || "未命名")}
        </div>
        <div class="book-preview-info">
          <nav class="book-breadcrumb">
            <button type="button" data-book-close>书柜</button>
            <span>/ ${escapeHtml(kindLabel)}</span>
          </nav>
          <div class="reader-toolbar">
            <span>${escapeHtml(kindLabel)}</span>
            <button type="button" data-book-close>收回书柜</button>
          </div>
          <h2>${escapeHtml(book.title || "未命名")}</h2>
          <p>${escapeHtml(displayIntro)}</p>
          ${diarySelector}
          <dl>
            ${book.status ? `<div><dt>状态</dt><dd>${escapeHtml(book.status)}</dd></div>` : ""}
            ${book.author ? `<div><dt>作者</dt><dd>${escapeHtml(book.author)}</dd></div>` : ""}
            ${book.tone ? `<div><dt>气质</dt><dd>${escapeHtml(book.tone)}</dd></div>` : ""}
            ${book.point_of_view ? `<div><dt>视角</dt><dd>${escapeHtml(book.point_of_view)}</dd></div>` : ""}
            ${book.progress ? `<div><dt>进度</dt><dd>${escapeHtml(book.progress)}</dd></div>` : ""}
            ${book.created ? `<div><dt>入柜</dt><dd>${escapeHtml(book.created)}</dd></div>` : ""}
          </dl>
          ${readingImpression}
          ${tags}
          ${manageActions}
          <button type="button" class="read-button" data-book-read>开始阅读</button>
        </div>
      </article>
    `;
  void hydrateBookshelfImages(panel);
}

function renderJmAlbumReader(book, kindLabel, displayTitle, displayIntro, readingImpression = "") {
  const pages = Array.isArray(book.pages) ? book.pages : [];
  const maxStart = Math.max(0, pages.length - (pages.length % 2 === 0 ? 2 : 1));
  const start = Math.min(Math.max(0, Number(state.selectedBookSpreadIndex || 0)), maxStart);
  state.selectedBookSpreadIndex = start % 2 === 0 ? start : start - 1;
  const spread = pages.slice(state.selectedBookSpreadIndex, state.selectedBookSpreadIndex + 2);
  const firstPage = spread[0]?.index || state.selectedBookSpreadIndex + 1;
  const lastPage = spread[spread.length - 1]?.index || firstPage;
  return `
    <article class="reader-page subpage jm_album image-reader">
      <nav class="book-breadcrumb">
        <button type="button" data-book-close>书柜</button>
        <span>/</span>
        <button type="button" data-book-back>${escapeHtml(book.title || "未命名")}</button>
        <span>/ 阅读</span>
      </nav>
      <div class="reader-toolbar">
        <button type="button" data-book-back>返回简介</button>
        <span>${escapeHtml(kindLabel)} · ${escapeHtml(firstPage)}-${escapeHtml(lastPage)} / ${escapeHtml(pages.length)}</span>
        <button type="button" data-book-close>收回书柜</button>
      </div>
      <div class="manga-reader-shell">
        <header class="manga-reader-head">
          <div>
            <span>${escapeHtml(kindLabel)}</span>
            <h2>${escapeHtml(displayTitle)}</h2>
            ${displayIntro ? `<p>${escapeHtml(displayIntro)}</p>` : ""}
          </div>
          <div class="manga-reader-actions">
            <button type="button" data-book-prev ${state.selectedBookSpreadIndex <= 0 ? "disabled" : ""}>上一页</button>
            <button type="button" data-book-next ${state.selectedBookSpreadIndex + 2 >= pages.length ? "disabled" : ""}>下一页</button>
            <button type="button" class="danger-outline" data-book-delete
              data-book-kind="${escapeHtml(book.kind || "")}"
              data-book-id="${escapeHtml(book.id || "")}"
              data-book-album-id="${escapeHtml(book.album_id || "")}"
              data-book-title="${escapeHtml(book.title || "")}">从书柜移除</button>
          </div>
        </header>
        ${readingImpression}
        <div class="manga-spread">
          ${spread.map((page) => `
            <figure class="manga-page">
              ${bookshelfImageTag(page.src, `${book.title || "夹层藏书"} 第 ${page.index} 页`)}
              <figcaption>${escapeHtml(page.index)} / ${escapeHtml(pages.length)}</figcaption>
            </figure>
          `).join("")}
          ${spread.length < 2 ? `<figure class="manga-page blank"><span>末页</span></figure>` : ""}
        </div>
      </div>
    </article>
  `;
}

function setBookshelfUnlockMessage(text, tone = "") {
  const message = $("#bookshelfUnlockMessage");
  if (!message) return;
  message.textContent = text || "";
  message.classList.toggle("ok", tone === "ok");
  message.classList.toggle("error", tone === "error");
}

function formatBookContent(value) {
  const parts = String(value || "")
    .split(/\n{2,}/)
    .map((part) => part.trim())
    .filter(Boolean);
  return parts.length
    ? parts.map((part) => `<p>${escapeHtml(part)}</p>`).join("")
    : `<p>这本书暂时没有正文。</p>`;
}

function renderProactiveCandidates() {
  const data = state.overview?.proactive_candidates || {};
  const counts = data.counts || {};
  const items = data.items || [];
  $("#proactiveSummary").innerHTML = [
    proactiveSummaryCard("候选总数", data.total || 0, `${data.visible_total || 0} 条合并记录`),
    proactiveSummaryCard("已进入计划", counts.accepted || 0, "当前或历史接受候选"),
    proactiveSummaryCard("已发送", counts.sent || 0, "实际发出的主动"),
    proactiveSummaryCard("被拦截", counts.blocked || 0, "同类拦截已合并计数"),
  ].join("");
  $("#proactiveSourceChart").innerHTML = donutChart(data.source_counts || {});
  $("#proactiveStatusChart").innerHTML = donutChart(counts || {});
  if (!items.length) {
    $("#proactiveCandidateList").innerHTML = `<div class="empty small">暂无主动候选。运行一段时间后，这里会显示随机日程、群聊分享、B 站、创作等候选。</div>`;
    return;
  }
  $("#proactiveCandidateList").innerHTML = items.map((item) => {
    const status = proactiveStatusLabel(item.status);
    const repeat = Number(item.repeat_count || 1);
    return `
      <section class="proactive-candidate ${escapeHtml(item.status || "unknown")}">
        <div class="proactive-candidate-head">
          <div>
            <b>${escapeHtml(item.topic || item.reason || "未命名候选")}</b>
            <span>${escapeHtml(item.source || "-")} · ${escapeHtml(item.reason || "-")} · ${escapeHtml(item.action || "message")}</span>
          </div>
          <span class="badge">${escapeHtml(repeat > 1 ? `${status} x${repeat}` : status)}</span>
        </div>
        <p>${escapeHtml(item.motive || "暂无动机记录")}</p>
        <div class="proactive-meta">
          <span>用户：${escapeHtml(item.user_id || "-")}</span>
          <span>计划：${escapeHtml(item.scheduled || "-")}</span>
          <span>创建：${escapeHtml(item.created || "-")}</span>
          ${repeat > 1 ? `<span>最近：${escapeHtml(item.last_seen || "-")}</span>` : ""}
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
        <span>视角：${escapeHtml(item.point_of_view || "第三人称有限视角")}</span>
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
  const qzone = overview.qzone || {};
  const privateReading = overview.private_reading || {};
  const longTermRows = {
    "B 站联动": bili.enabled ? "开启" : "关闭",
    "无聊刷视频": bili.boredom_watch_enabled ? "开启" : "关闭",
    "最新视频": bili.latest_video?.title || "暂无",
    "QQ 空间": qzone.enabled ? (qzone.available ? "可用" : "待服务") : "关闭",
    "生活说说": qzone.life_publish_enabled ? "开启" : "关闭",
    "最近说说": qzone.last_text || "暂无",
    "私下创作": creative.enabled ? "开启" : "关闭",
    "创作项目": `${creative.active_projects || 0}/${creative.project_count || 0}`,
    "最新创作": creative.latest_title || "暂无",
  };
  if (privateReading.available) {
    longTermRows["夹层素材"] = privateReading.enabled ? "可用" : "关闭";
    longTermRows["私下阅读"] = privateReading.boredom_read_enabled ? "开启" : "关闭";
    longTermRows["征求推荐"] = privateReading.ask_recommendation_enabled ? "开启" : "关闭";
    longTermRows["最近阅读"] = privateReading.last_album?.title || "暂无";
  }
  renderDl("#privateConfig", overview.private || {});
  renderDl("#groupConfig", group);
  renderDl("#longTermConfig", longTermRows);
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
  fillForm("#environmentModuleForm", settings);
  fillForm("#privateModuleForm", settings);
  fillForm("#groupModuleForm", settings);
  fillForm("#worldbookModuleForm", settings);
  fillForm("#memoryModuleForm", settings);
  fillForm("#longTermModuleForm", settings);
  setPrivateReadingConfigVisible(isPrivateReadingAvailable());
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
      label: "世界观适配",
      value: settings.worldview_adaptation_mode || "auto",
      note: settings.worldview_adaptation_prompt ? "自定义提示已设置" : "使用内置映射",
      tone: settings.worldview_adaptation_mode === "off" ? "off" : "ok",
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
      note: [
        settings.enable_bilibili_boredom_watch ? "B 站" : "",
        settings.enable_qzone_life_publish ? "空间说说" : "",
        isPrivateReadingAvailable() && settings.enable_private_reading_boredom_read ? "夹层阅读" : "",
        isPrivateReadingAvailable() && settings.enable_private_reading_ask_recommendation ? "征求推荐" : "",
      ].filter(Boolean).join(" / ") || "联动关闭",
      tone: settings.enable_creative_writing || settings.enable_bilibili_boredom_watch || settings.enable_qzone_life_publish || (isPrivateReadingAvailable() && (settings.enable_private_reading_boredom_read || settings.enable_private_reading_ask_recommendation)) ? "ok" : "off",
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

function setPrivateReadingConfigVisible(visible) {
  const group = $("#privateReadingModuleGroup");
  if (!group) return;
  group.hidden = !visible;
  group.querySelectorAll("[name]").forEach((input) => {
    input.disabled = !visible;
  });
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
      const label = presetCatalog[button.dataset.preset]?.label || button.dataset.preset;
      if (!requireSecondClick(button, `preset:${button.dataset.preset}`, `再次点击应用“${label}”预设`, "再次点击应用")) return;
      await runAction(() => postJson("/preset/apply", { name: button.dataset.preset }), "已应用配置预设", button);
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
    if (input.disabled) return;
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
  const extraKeys = Object.keys(state.featureDraft || {}).filter((key) => !knownKeys.has(key) && visibleConfigKey(key));
  const groups = extraKeys.length
    ? [...featureGroups, { title: "其他", note: "来自配置但暂未归入固定分组的开关。", keys: extraKeys }]
    : featureGroups;
  const visibleDraftKeys = Object.keys(state.featureDraft || {}).filter(visibleConfigKey);
  const total = visibleDraftKeys.length;
  const enabled = visibleDraftKeys.filter((key) => state.featureDraft[key]).length;
  const riskyEnabled = ["enable_group_interjection", "enable_bilibili_boredom_watch", isPrivateReadingAvailable() ? "enable_private_reading_boredom_read" : "", isPrivateReadingAvailable() ? "enable_private_reading_ask_recommendation" : "", "enable_unanswered_screen_peek_followup"]
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

  if (state.selectedFeatureKey && !visibleConfigKey(state.selectedFeatureKey)) {
    state.selectedFeatureKey = "";
  }
  if (state.selectedFeatureKey && Object.prototype.hasOwnProperty.call(state.featureDraft, state.selectedFeatureKey)) {
    $("#featureFlags").innerHTML = featureDetailPage(state.selectedFeatureKey);
    bindFeatureDetailActions();
    return;
  }

  const board = groups.map((group) => {
    const visibleKeys = group.keys.filter((key) => {
      if (!visibleConfigKey(key)) return false;
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
  document.querySelectorAll("[data-feature-open]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedFeatureKey = button.dataset.featureOpen || "";
      renderFeatureSwitches();
    });
  });
}

function featureSwitchItem(key) {
  const checked = Boolean(state.featureDraft[key]);
  return `
    <section class="feature-switch-item ${checked ? "on" : "off"}" title="${escapeHtml(featureDescription(key))}">
      <label class="feature-toggle-hit" aria-label="${escapeHtml(featureLabel(key))}">
        <input type="checkbox" data-feature-key="${escapeHtml(key)}" ${checked ? "checked" : ""}>
        <span class="feature-toggle-visual"></span>
      </label>
      <button type="button" class="feature-switch-text" data-feature-open="${escapeHtml(key)}">
        <b>${escapeHtml(featureLabel(key))}</b>
        <span class="feature-state-text">${escapeHtml(checked ? "开启" : "关闭")}</span>
        <small>${escapeHtml(key)}</small>
      </button>
    </section>
  `;
}

function featureGroupForKey(key) {
  const group = featureGroups.find((item) => item.keys.includes(key));
  return group ? group.title : "其他";
}

function featureRelatedSettings(key) {
  const settings = state.overview?.settings || {};
  const groups = {
    enable_environment_perception: ["environment_perception_timezone", "holiday_country"],
    enable_holiday_perception: ["holiday_country"],
    enable_group_interjection: ["group_interject_min_interval_minutes", "group_interject_max_daily"],
    enable_group_repeat_follow: ["group_repeat_follow_probability", "group_repeat_interrupt_probability", "group_repeat_interrupt_probability_step", "group_repeat_interrupt_text", "group_repeat_interrupt_image_path"],
    enable_group_scene_awareness: ["group_scene_recent_limit", "group_conversation_followup_seconds", "group_conversation_followup_max_turns"],
    enable_group_conversation_followup: ["group_conversation_followup_seconds", "group_conversation_followup_max_turns"],
    enable_forward_message_adaptation: ["forward_message_mode", "forward_message_max_messages", "forward_message_max_chars", "forward_message_parse_nested", "forward_message_image_vision", "forward_message_image_limit"],
    enable_worldbook_member_recognition: ["worldbook_auto_import", "worldbook_member_match_aliases", "worldbook_self_registration", "worldbook_auto_pending_observations", "worldbook_member_inject_limit", "worldbook_config_paths"],
    enable_atrelay_tools: ["atrelay_require_worldbook_first", "atrelay_member_cache_minutes", "atrelay_sensitive_confirm", "atrelay_default_relay_style", "atrelay_multi_target_limit"],
    enable_bilibili_boredom_watch: ["bilibili_boredom_min_interval_hours", "bilibili_share_probability", "bilibili_share_min_score"],
    enable_news_integration: ["enable_news_daily_hot_read", "news_hot_sources", "news_hot_max_items", "news_sources", "news_min_interval_hours", "news_share_probability", "news_max_items_per_source"],
    enable_news_boredom_read: ["news_min_interval_hours", "news_share_probability", "news_max_items_per_source"],
    enable_web_exploration: ["web_exploration_interests", "web_exploration_min_interval_hours", "web_exploration_share_probability", "web_exploration_max_results"],
    enable_web_exploration_boredom_search: ["web_exploration_interests", "web_exploration_min_interval_hours", "web_exploration_max_results"],
    enable_qzone_life_publish: ["qzone_life_publish_min_interval_hours", "qzone_life_publish_probability"],
    enable_private_reading_boredom_read: ["private_reading_min_interval_hours", "private_reading_max_photo_count", "private_reading_share_probability", "private_reading_default_keywords"],
    enable_private_reading_ask_recommendation: ["private_reading_ask_probability"],
    enable_unanswered_screen_peek_followup: ["unanswered_screen_peek_after_minutes", "unanswered_screen_peek_cooldown_minutes"],
    enable_creative_writing: ["creative_inspiration_probability", "creative_share_probability", "creative_base_chars_per_hour", "creative_max_active_projects"],
    creative_hidden_mode: ["creative_share_probability"],
    enable_companion_memory: ["memory_refresh_interval_minutes", "max_companion_memory_items"],
    enable_expression_learning: ["max_learned_expression_items"],
    enable_dialogue_episode_memory: ["episode_memory_refresh_messages", "episode_memory_refresh_minutes", "max_dialogue_episodes"],
    enable_semantic_message_debounce: ["inbound_message_debounce_seconds", "semantic_message_debounce_seconds"],
  };
  const keys = groups[key] || [];
  return keys
    .filter((item) => Object.prototype.hasOwnProperty.call(settings, item))
    .map((item) => [item, settings[item]]);
}

function featureDependencyLines(key) {
  const dependencies = [];
  if (key !== "enable_group_companion" && key.startsWith("enable_group_")) dependencies.push(["依赖", "群聊总开关开启后才会在群聊中生效"]);
  if (key === "enable_group_conversation_followup") dependencies.push(["依赖", "需要群聊场景感知能判断当前消息是否仍然指向 Bot"]);
  if (["enable_companion_memory", "enable_expression_learning", "enable_companion_reply_planner", "enable_intent_emotion_analysis", "enable_response_self_review", "enable_passive_topic_suppression", "enable_relationship_state_machine", "enable_dialogue_episode_memory", "enable_open_loop_tracking"].includes(key)) {
    dependencies.push(["依赖", "陪伴风格整合开启后注入效果更完整"]);
  }
  if (["enable_bilibili_boredom_watch"].includes(key)) dependencies.push(["依赖", "需要对应整合能力开启且外部服务可用"]);
  if (["enable_web_exploration", "enable_web_exploration_boredom_search"].includes(key)) dependencies.push(["依赖", "需要先在 AstrBot 全局 provider_settings 中开启网页搜索，并配置可用的 Tavily、Bocha、Brave、Firecrawl 或百度 AI 搜索"]);
  if (["enable_qzone_life_publish"].includes(key)) dependencies.push(["依赖", "需要 QQ 空间动态层可用"]);
  if (key.startsWith("enable_private_reading_")) dependencies.push(["依赖", "检测到可用素材能力后才显示并生效"]);
  if (["enable_group_interjection", "enable_bilibili_boredom_watch", "enable_news_boredom_read", "enable_web_exploration_boredom_search", "enable_private_reading_boredom_read", "enable_private_reading_ask_recommendation", "enable_unanswered_screen_peek_followup"].includes(key)) {
    dependencies.push(["注意", "属于高主动项，建议结合频率、冷却和每日额度观察"]);
  }
  return dependencies;
}

function featureDetailExplanation(key) {
  const specific = {
    enable_mai_style_integration: "把本插件整理出的关系状态、用户画像、表达习惯、未完话头和当前生活状态注入到 Bot 回复上下文里。关闭后，这些陪伴侧信息仍可能被记录，但不会系统性地参与回复生成。",
    enable_companion_memory: "从私聊中提取稳定事实和长期偏好，例如称呼、雷点、常聊主题、关系边界。它不是逐字保存聊天，而是整理成后续回复可引用的画像条目。",
    enable_expression_learning: "记录用户常用的称呼、短句、语气和互动方式，让 Bot 在长期相处后更懂用户平时怎么说话。关闭后不会继续学习新的表达样本。",
    enable_companion_reply_planner: "在生成回复前先判断本轮应该安慰、接梗、解释、转移话题还是简短回应，用来减少机械问答和不合时宜的长篇回复。",
    enable_intent_emotion_analysis: "分析用户消息里的情绪、真实意图和关系信号，例如撒娇、吐槽、求助、试探或普通闲聊。结果会影响关系分、语气和是否继续追问。",
    enable_response_self_review: "回复生成后再检查一遍是否生硬、越界、重复、像系统提示或不符合人设。开启后会多一次模型调用，但能降低奇怪回复的概率。",
    enable_passive_topic_suppression: "记录近期已经主动提过的话题，避免 Bot 在短时间内反复提同一个日程、梦境、创作或问候内容。",
    enable_relationship_state_machine: "根据互动频率、回应情况、情绪反馈和长期记忆维护关系阶段，例如陌生、熟悉、亲近、冷却。阶段会影响主动频率和说话距离感。",
    enable_dialogue_episode_memory: "把一段连续私聊整理成“发生过的一段事”，保存摘要、情绪和可继续接的话头。适合承接上次聊天，而不是只记住零散关键词。",
    enable_open_loop_tracking: "识别用户说的待办、约定、之后再说、还没解决的问题。Bot 后续可以在合适时候自然接上，而不是把未完成话题丢掉。",
    enable_semantic_message_debounce: "Bot 被唤醒后先短暂收口，不急着立刻回复。用户连续补充的几句话会被合成同一轮理解，适合“先发图再说明”“一句话拆成几条发”的场景，也能减少重复模型调用。",
    enable_environment_perception: "注入当前时间、日期、平台、群聊/私聊和消息媒介，让 Bot 的判断更贴近日常场景。它会影响日程、状态、回复和主动消息。",
    enable_holiday_perception: "识别节假日、周末、调休和工作日，影响日程、问候、日记和主动消息的生活节奏。",
    enable_platform_perception: "识别当前消息来自哪个平台、私聊还是群聊、是否带图片/语音/视频等媒介信息。用于调整回复方式和上下文描述。",
    enable_lunar_perception: "在可用时注入农历日期，帮助日程、梦境、日记和节日氛围更贴近中文生活语境。",
    enable_solar_term_perception: "注入当天或临近节气，例如立春、芒种、冬至。主要影响日程细节、生活观察和表达氛围。",
    enable_almanac_perception: "生成轻量宜/忌氛围标签，用作生活化调味。默认建议谨慎使用，避免 Bot 表现得过于玄学。",
    enable_group_companion: "控制插件是否接收并维护群聊侧的观察数据。关闭后，群聊黑话、群成员画像、话题线、关系网、群插话等群聊能力都会失去基础输入。",
    enable_group_context_injection: "当 Bot 在群里回复时，把近期话题、群氛围、相关成员和关系网信息注入上下文，让回复知道当前群里正在发生什么。",
    enable_forward_message_adaptation: "当用户发送或引用合并转发时，插件会读取合并消息节点。可选择“注入”把整理后的原始记录直接交给主模型，也可选择“转述”先用专门模型压成自然记录再交给主模型。Bot 会把它当作被转来的聊天记录来读，而不是把里面每句话都当成当前用户本人说的内容。",
    enable_group_scene_awareness: "让 Bot 判断当前消息是在对 Bot、某个群友还是整个群说话。它会参考 @、回复对象、最近发言和文本语气，减少误接别人话的情况。",
    enable_group_conversation_followup: "用户在群里明确叫过 Bot 后，后续短时间内即使没有继续 @，插件也会结合场景、插话者、指代词和最近上下文判断是否仍在和 Bot 对话。它有连续续接上限，避免对话链无限延长。",
    enable_group_slang_learning: "从群聊消息中记录高频梗、简称、黑话和特殊表达，保存出现次数和最近出现时间。它只负责收集词，不负责解释含义。",
    enable_group_slang_meanings: "在收集到群黑话后，尝试用模型解释它在当前群里的含义。解释结果会用于群聊理解，不等于对外公开发言。",
    enable_group_member_profiles: "为群成员维护轻量画像，例如常用名字、发言频率、最近活跃、常见语气和是否经常与 Bot 互动。用于判断群氛围和说话对象。",
    enable_group_topic_threads: "把群聊中连续讨论的内容整理成话题线，记录参与者、最近例句和话题变化。后续群聊总结和私聊分享会用到它。",
    enable_group_episode_memory: "把一段时间内的群聊整理成摘要片段，保留有趣事件、重要讨论和群氛围。它比最近消息窗口保存得更久。",
    enable_group_relationship_graph: "记录群友之间的互动边，用于观察常一起说话的人、常见组合和群内关系氛围。",
    enable_group_interjection: "允许 Bot 在群聊里主动插一句。它会参考群氛围、最近话题、冷却和每日上限，不是每次有消息都发言。",
    enable_group_repeat_follow: "检测群聊中同一句话连续复读。达到阈值后，Bot 可能只跟读一次，也可能用文本或表情包打断复读。",
    enable_group_interjection_feedback: "记录 Bot 主动插话后群友是接话、无视、笑还是反感，用来调整之后插话的保守程度。",
    enable_group_privacy_guard: "防止 Bot 把私聊记忆、私下关系、书柜夹层和用户私人信息泄露到群聊。建议长期保持开启。",
    enable_worldbook_member_recognition: "以 QQ 号作为身份锚点维护关系网，让 Bot 在群聊和转述中知道“谁是谁”。昵称、群名片和别名只作为辅助线索，避免用户改名后认错人。",
    enable_atrelay_tools: "为模型提供跨群转述、查询群成员、解析 @ 对象等工具。开启后，Bot 可以结合关系网把用户口中的名字或别名解析成稳定 QQ 身份；转述时默认按人格和双方关系改写，用户要求原话时也可保留原话。",
    enable_livingmemory_integration: "允许 Bot 在需要长期事实时调用 LivingMemory，而不是只依赖本插件自己的画像。适合复用已有长期记忆，避免多套记忆互相打架。",
    enable_bilibili_integration: "读取已整合的 B 站相关能力状态和观看记录，让 Bot 知道自己看过什么视频，并能在合适时机提起。",
    enable_bilibili_boredom_watch: "当 Bot 空闲或无聊时，低频触发 B 站观看行为，并可能在合适节点向用户分享看过的内容。",
    enable_news_integration: "新闻阅读负责让 Bot 每天知道外界发生了什么。默认会在日程生成那一轮一起获取公开热点，并合并 RSS/Atom 新闻源，只抓取标题、摘要、链接和发布时间。整理后的见闻会进入内部留痕，可影响日记、状态余味和后续主动搜索。",
    enable_news_boredom_read: "当 Bot 的日程和状态显示比较空、无聊、休息或有好奇心时，低频读取新闻源。读取后不一定主动发给用户，也可能只是作为近期见闻留存。",
    enable_web_exploration: "主动搜索负责 Bot 自己的好奇心。它会使用 AstrBot 全局网页搜索，根据人设兴趣、最近聊天、当前日程、心情和今日新闻见闻自行选一个搜索主题，再整理成内部探索笔记，留下搜索词、摘要、来源和时间。",
    enable_web_exploration_boredom_search: "当 Bot 处在空档、无聊、休息或有好奇心的状态时触发主动搜索。它不是固定搜索新闻，而是可以按人格去查作品、技术、生活知识、流行梗、时讯或最近聊天里引出的内容。",
    enable_qzone_integration: "启用 QQ 空间动态层，让 Bot 可以查看、点赞、评论或发布动态。具体是否执行取决于可用服务和工具调用。",
    enable_qzone_life_publish: "让 Bot 根据日程、状态和日记余味低频发布生活动态。它属于公开表达，不等同于私聊主动消息。",
    enable_private_reading_integration: "检测并接入书柜夹层的私下阅读素材能力。开启后，相关素材可以作为 Bot 的私下长期行为来源。",
    enable_private_reading_boredom_read: "当 Bot 空闲、无聊或夜里状态合适时，低频自己找内容阅读，并把阅读记录放入书柜夹层。",
    enable_private_reading_ask_recommendation: "当 Bot 想补充私下阅读素材时，低频私聊询问用户有没有推荐。是否害羞、坦率或绕开话题由人设决定。",
    enable_unanswered_screen_peek_followup: "当 Bot 主动找用户后长时间没有回应，且状态上有无聊/在意倾向时，允许额外识屏看看用户在做什么。",
    enable_creative_writing: "让 Bot 因生活小事、梦境或状态灵感开小说/文本坑，并按人设对应的速度慢慢写入书柜。",
    creative_hidden_mode: "让创作默认作为 Bot 自己私下进行的长期行为，只在节点、被问到近况或合适时机自然提起。",
  };
  if (specific[key]) return specific[key];
  if (key.startsWith("enable_group_")) return "群聊观察模块的一项子能力，会读取群聊近期消息和成员信息，并影响群聊回复、转述、插话或关系网注入。";
  if (key.startsWith("enable_private_reading_")) return "书柜夹层相关的长期行为。只有检测到对应素材能力可用时才会显示并触发，记录会进入书柜夹层。";
  if (key.startsWith("enable_bilibili_")) return "外部内容消费相关能力，用于让 Bot 在空闲时形成自己的经历，并在合适时机转化为分享素材。";
  if (key.startsWith("enable_qzone_")) return "QQ 空间动态相关能力，用于查看、互动或发布生活动态。";
  return featureDescription(key);
}

function featureImpactLines(key) {
  const lines = [];
  const group = featureGroupForKey(key);
  lines.push(["影响范围", group]);
  if (key.startsWith("enable_group_") || key === "enable_atrelay_tools" || key === "enable_worldbook_member_recognition") {
    lines.push(["主要场景", "群聊、转述、关系网注入"]);
  } else if (key.startsWith("enable_bilibili_") || key.startsWith("enable_news_") || key.startsWith("enable_web_exploration") || key.startsWith("enable_qzone_") || key.startsWith("enable_private_reading_") || key === "enable_creative_writing" || key === "creative_hidden_mode") {
    lines.push(["主要场景", "长线主动行为、书柜、私聊分享"]);
  } else if (key.startsWith("enable_environment_") || key.includes("perception")) {
    lines.push(["主要场景", "日程、状态、回复上下文"]);
  } else {
    lines.push(["主要场景", "私聊陪伴、记忆和回复生成"]);
  }
  lines.push(["保存方式", "切换后需要点击“保存功能开关”写入配置"]);
  return lines;
}

function configLabel(name) {
  return configLabels[name] || name.replace(/^enable_/, "").replaceAll("_", " ");
}

function featureDetailPage(key) {
  const enabled = Boolean(state.featureDraft[key]);
  const related = featureRelatedSettings(key);
  const dependencies = featureDependencyLines(key);
  const impacts = featureImpactLines(key);
  const settingsRows = related.length
    ? related.map(([name, value]) => `
      <section class="feature-param-row">
        <div>
          <b>${escapeHtml(configLabel(name))}</b>
          <code>${escapeHtml(name)}</code>
        </div>
        <span>${escapeHtml(formatValue(value))}</span>
      </section>
    `).join("")
    : `<div class="feature-param-empty">暂无关联参数</div>`;
  const dependencyRows = dependencies.length
    ? dependencies.map(([name, value]) => `<div><dt>${escapeHtml(name)}</dt><dd>${escapeHtml(value)}</dd></div>`).join("")
    : `<div><dt>-</dt><dd>无额外依赖</dd></div>`;
  const impactRows = impacts.map(([name, value]) => `<div><dt>${escapeHtml(name)}</dt><dd>${escapeHtml(value)}</dd></div>`).join("");
  return `
    <section class="feature-detail-page ${enabled ? "on" : "off"}">
      <nav class="feature-detail-breadcrumb">
        <button type="button" data-feature-back>功能开关</button>
        <span>/ ${escapeHtml(featureGroupForKey(key))}</span>
      </nav>
      <div class="feature-state-strip ${enabled ? "on" : "off"}">
        <b>${escapeHtml(enabled ? "当前已开启" : "当前已关闭")}</b>
        <span>${escapeHtml(enabled ? "保存后该能力会继续生效" : "保存后该能力不会触发")}</span>
      </div>
      <header class="feature-detail-head">
        <div>
          <span class="module-badge">${escapeHtml(featureGroupForKey(key))}</span>
          <h2>${escapeHtml(featureLabel(key))}</h2>
          <p>${escapeHtml(featureDetailExplanation(key))}</p>
        </div>
        <label class="feature-detail-toggle">
          <input type="checkbox" data-feature-detail-toggle="${escapeHtml(key)}" ${enabled ? "checked" : ""}>
          <span class="feature-toggle-visual"></span>
          <b>${escapeHtml(enabled ? "开启" : "关闭")}</b>
        </label>
      </header>
      <div class="feature-detail-grid">
        <article class="feature-detail-card">
          <h3>基础信息</h3>
          <dl>
            <div><dt>配置键</dt><dd>${escapeHtml(key)}</dd></div>
            <div><dt>所属模块</dt><dd>${escapeHtml(featureGroupForKey(key))}</dd></div>
            <div><dt>当前状态</dt><dd>${escapeHtml(enabled ? "开启" : "关闭")}</dd></div>
          </dl>
        </article>
        <article class="feature-detail-card">
          <h3>影响范围</h3>
          <dl>${impactRows}</dl>
        </article>
        <article class="feature-detail-card">
          <h3>关联参数</h3>
          <div class="feature-param-list">${settingsRows}</div>
        </article>
        <article class="feature-detail-card">
          <h3>依赖与注意</h3>
          <dl>${dependencyRows}</dl>
        </article>
      </div>
    </section>
  `;
}

function bindFeatureDetailActions() {
  document.querySelectorAll("[data-feature-back]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedFeatureKey = "";
      renderFeatureSwitches();
    });
  });
  document.querySelectorAll("[data-feature-detail-toggle]").forEach((input) => {
    input.addEventListener("change", () => {
      state.featureDraft[input.dataset.featureDetailToggle] = input.checked;
      renderFeatureSwitches();
    });
  });
}

function renderProviders() {
  const providers = state.overview?.providers || {};
  renderProviderFlow(providers);
  $("#providerForm").innerHTML = Object.entries(providerLabels)
    .filter(([key]) => visibleConfigKey(key))
    .map(([key, label]) => `
    <label class="provider-card">
      <span>${escapeHtml(label)}</span>
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
  const tasks = Object.entries(providerLabels).filter(([key]) => (
    key !== "LLM_PROVIDER_ID"
    && key !== "MAI_STYLE_PROVIDER_ID"
    && visibleConfigKey(key)
  ));
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

function relationshipGraphView(edges, groupMembers = {}) {
  const pairs = Object.entries(edges || {})
    .map(([key, value]) => {
      const parts = key.split(/[-|:>]+/).map((item) => item.trim()).filter(Boolean);
      const weight = Number(value?.count || value?.weight || value || 1);
      return parts.length >= 2 ? {
        a: parts[0],
        b: parts[1],
        weight,
        kind: value?.kind || value?.type || value?.relation || "",
        summary: value?.summary || value?.last_summary || value?.reason || "",
      } : null;
    })
    .filter(Boolean)
    .sort((a, b) => b.weight - a.weight)
    .slice(0, 24);
  if (!pairs.length) return `<div class="empty small">暂无关系边</div>`;

  const memberMap = relationshipMemberMap(groupMembers);
  const scores = new Map();
  pairs.forEach((edge) => {
    [edge.a, edge.b].forEach((id) => {
      const item = scores.get(id) || { id, degree: 0, weight: 0 };
      item.degree += 1;
      item.weight += edge.weight;
      scores.set(id, item);
    });
  });
  const topNodes = [...scores.values()]
    .sort((a, b) => b.weight - a.weight || b.degree - a.degree)
    .slice(0, 8);
  const maxWeight = Math.max(1, ...pairs.map((edge) => edge.weight));
  const strongest = pairs[0];
  const hiddenCount = Math.max(0, Object.keys(edges || {}).length - pairs.length);
  return `
    <div class="relation-map">
      <div class="relation-map-summary">
        <article><span>涉及成员</span><b>${escapeHtml(scores.size)}</b></article>
        <article><span>互动关系</span><b>${escapeHtml(Object.keys(edges || {}).length)}</b></article>
        <article><span>最强连接</span><b>${escapeHtml(relationNodeName(strongest.a, memberMap))} ↔ ${escapeHtml(relationNodeName(strongest.b, memberMap))}</b></article>
      </div>
      <div class="relation-node-grid">
        ${topNodes.map((node) => relationNodeCard(node, memberMap)).join("")}
      </div>
      <div class="relation-edge-list">
        ${pairs.map((edge) => relationEdgeRow(edge, memberMap, maxWeight)).join("")}
      </div>
      ${hiddenCount ? `<p class="muted relation-map-note">还有 ${escapeHtml(hiddenCount)} 条较弱关系未展开，可在群聊观测继续积累后查看。</p>` : ""}
    </div>
  `;
}

function relationshipMemberMap(groupMembers = {}) {
  const map = new Map();
  const worldbookMembers = state.overview?.worldbook?.members || [];
  worldbookMembers.forEach((item) => {
    const id = String(item.user_id || "").trim();
    if (!id) return;
    map.set(id, {
      name: item.name || id,
      aliases: Array.isArray(item.aliases) ? item.aliases : [],
      observed: Array.isArray(item.observed_names) ? item.observed_names : [],
      source: "关系网",
    });
  });
  Object.entries(groupMembers || {}).forEach(([id, raw]) => {
    if (!id) return;
    const item = raw && typeof raw === "object" ? raw : {};
    const existing = map.get(String(id)) || {};
    map.set(String(id), {
      name: existing.name || item.name || item.nickname || item.card || id,
      aliases: existing.aliases || [],
      observed: existing.observed || [],
      source: existing.source || "群聊",
    });
  });
  return map;
}

function relationNodeName(id, memberMap) {
  const item = memberMap.get(String(id));
  return item?.name || String(id);
}

function relationNodeCard(node, memberMap) {
  const member = memberMap.get(String(node.id)) || {};
  const name = member.name || node.id;
  const subNames = [...(member.aliases || []), ...(member.observed || [])].filter(Boolean).slice(0, 3);
  return `
    <article class="relation-node-card">
      <div class="relation-avatar">${escapeHtml(shortName(name, 2))}</div>
      <div>
        <b>${escapeHtml(name)}</b>
        <code>${escapeHtml(node.id)}</code>
        ${subNames.length ? `<small>${subNames.map((item) => escapeHtml(item)).join(" / ")}</small>` : `<small>${escapeHtml(member.source || "群聊成员")}</small>`}
      </div>
      <span>${escapeHtml(node.degree)} 边</span>
    </article>
  `;
}

function relationEdgeRow(edge, memberMap, maxWeight) {
  const pct = Math.max(4, Math.round((edge.weight / maxWeight) * 100));
  const leftName = relationNodeName(edge.a, memberMap);
  const rightName = relationNodeName(edge.b, memberMap);
  return `
    <article class="relation-edge-row">
      <div class="relation-edge-main">
        <b title="${escapeHtml(edge.a)}">${escapeHtml(leftName)}</b>
        <span>↔</span>
        <b title="${escapeHtml(edge.b)}">${escapeHtml(rightName)}</b>
      </div>
      <div class="relation-edge-meter"><i style="width:${pct}%"></i></div>
      <div class="relation-edge-meta">
        <code>${escapeHtml(edge.a)}</code>
        <code>${escapeHtml(edge.b)}</code>
        <span>${escapeHtml(edge.kind || "互动")} · ${escapeHtml(edge.weight)}</span>
      </div>
      ${edge.summary ? `<p>${escapeHtml(edge.summary)}</p>` : ""}
    </article>
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
  if (value === "inject") return "注入";
  if (value === "transcribe") return "转述";
  if (Array.isArray(value)) return value.join(", ");
  if (value && typeof value === "object") return JSON.stringify(value, null, 2);
  return value ?? "";
}

function showToast(message, tone = "ok") {
  const text = String(message || "").trim();
  if (!text) return;
  let toast = document.getElementById("pageToast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "pageToast";
    toast.className = "page-toast";
    toast.setAttribute("role", "status");
    toast.setAttribute("aria-live", "polite");
    document.body.appendChild(toast);
  }
  toast.textContent = text;
  toast.classList.toggle("error", tone === "error");
  toast.classList.add("show");
  window.clearTimeout(showToast._timer);
  showToast._timer = window.setTimeout(() => toast.classList.remove("show"), 1800);
}

function setActionBusy(control, busy) {
  if (!(control instanceof HTMLButtonElement)) return;
  if (busy) {
    control.dataset.originalText = control.textContent || "";
    control.disabled = true;
    control.classList.add("is-busy");
    control.textContent = "处理中...";
  } else {
    control.disabled = false;
    control.classList.remove("is-busy");
    if (control.dataset.originalText) {
      control.textContent = control.dataset.originalText;
      delete control.dataset.originalText;
    }
  }
}

function requireSecondClick(control, key, message, nextText = "再次点击确认", timeoutMs = 6000) {
  if (!(control instanceof HTMLButtonElement)) return true;
  const now = Date.now();
  const armed = control.dataset.confirmKey === key && now - Number(control.dataset.confirmAt || 0) < timeoutMs;
  if (armed) {
    delete control.dataset.confirmKey;
    delete control.dataset.confirmAt;
    return true;
  }
  control.dataset.confirmKey = key;
  control.dataset.confirmAt = String(now);
  control.dataset.originalText = control.dataset.originalText || control.textContent || "";
  control.textContent = nextText;
  showToast(message);
  window.clearTimeout(control._confirmTimer);
  control._confirmTimer = window.setTimeout(() => {
    if (control.dataset.confirmKey === key) {
      delete control.dataset.confirmKey;
      delete control.dataset.confirmAt;
      control.textContent = control.dataset.originalText || "";
      delete control.dataset.originalText;
    }
  }, timeoutMs);
  return false;
}

async function runAction(action, successMessage = "", control = null) {
  setActionBusy(control, true);
  showToast("正在处理...");
  try {
    const result = await action();
    await loadAll();
    showToast(successMessage || result?.message || "操作已完成");
    return result;
  } catch (error) {
    showToast(`操作失败：${error.message}`, "error");
  } finally {
    setActionBusy(control, false);
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

document.addEventListener("click", (event) => {
  const element = event.target instanceof Element ? event.target : null;
  const bookButton = element?.closest("[data-book-id]");
  if (bookButton) {
    selectBookshelfBook(bookButton.dataset.bookId);
    return;
  }
  if (element?.closest("[data-book-read]")) {
    state.bookshelfPage = "reader";
    state.selectedBookSpreadIndex = 0;
    renderBookDetailPanel();
    return;
  }
  if (element?.closest("[data-book-prev]")) {
    state.selectedBookSpreadIndex = Math.max(0, Number(state.selectedBookSpreadIndex || 0) - 2);
    renderBookDetailPanel();
    return;
  }
  if (element?.closest("[data-book-next]")) {
    const pages = Array.isArray(state.selectedBook?.pages) ? state.selectedBook.pages : [];
    state.selectedBookSpreadIndex = Math.min(Math.max(0, pages.length - 1), Number(state.selectedBookSpreadIndex || 0) + 2);
    renderBookDetailPanel();
    return;
  }
  const deleteButton = element?.closest("[data-book-delete]");
  if (deleteButton) {
    deleteSelectedBookshelfItem(deleteButton);
    return;
  }
  if (element?.closest("[data-book-back]")) {
    state.bookshelfPage = "detail";
    renderBookDetailPanel();
    return;
  }
  if (element?.closest("[data-book-close]")) {
    state.selectedBook = null;
    state.bookshelfPage = "shelf";
    renderBookshelf();
  }
});

async function deleteSelectedBookshelfItem(button = null) {
  const book = state.selectedBook || {};
  const dataset = button?.dataset || {};
  const kind = dataset.bookKind || book.kind || "";
  const itemId = dataset.bookId || book.id || "";
  const albumId = dataset.bookAlbumId || book.album_id || "";
  const title = dataset.bookTitle || book.title || "";
  const diaryDate = kind === "diary" ? (dataset.bookDate || state.selectedDiaryDate || "") : "";
  if (!kind) {
    alert("没有找到当前书籍，请刷新拓展页后再试。");
    return;
  }
  const label = kind === "diary" && diaryDate ? `${diaryDate} 的日记` : (title || "这本书");
  if (kind !== "jm_album" && !requireSecondClick(button, `book:${kind}:${itemId}:${diaryDate}`, `再次点击删除「${label}」`, "再次点击删除")) return;
  if (button) {
    button.disabled = true;
    button.textContent = "移除中...";
  }
  try {
    const result = await postJson("/bookshelf/delete", {
      kind,
      id: itemId,
      album_id: albumId,
      title,
      date: diaryDate,
    });
    if (!result.changed) {
      alert("没有找到要移除的书柜条目，请刷新拓展页后再试。");
      if (button) {
        button.disabled = false;
        button.textContent = kind === "diary" ? "删除当前日记" : "从书柜移除";
      }
      return;
    }
    state.bookshelfUnlocked = result.bookshelf || null;
    state.selectedBook = null;
    state.bookshelfPage = "shelf";
    state.selectedBookSpreadIndex = 0;
    renderBookshelf();
  } catch (error) {
    alert(error.message);
    if (button) {
      button.disabled = false;
      button.textContent = kind === "diary" ? "删除当前日记" : "从书柜移除";
    }
  }
}

document.addEventListener("change", (event) => {
  const target = event.target instanceof HTMLSelectElement ? event.target : null;
  if (!target || !target.matches("[data-diary-date]")) return;
  state.selectedDiaryDate = target.value;
  renderBookDetailPanel();
});

$("#refreshBtn").addEventListener("click", loadAll);
$("#bookshelfUnlockForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const password = $("#bookshelfPassword").value.trim();
  if (!password) {
    setBookshelfUnlockMessage("请输入密码", "error");
    return;
  }
  const button = event.currentTarget.querySelector("button[type='submit']");
  if (button) {
    button.disabled = true;
    button.textContent = "验证中...";
  }
  setBookshelfUnlockMessage("正在验证...", "");
  try {
    const result = await postJson("/bookshelf/unlock", { password });
    state.bookshelfUnlocked = result.bookshelf || null;
    state.selectedBook = null;
    state.bookshelfPage = "shelf";
    renderBookshelf();
    $("#bookshelfPassword").value = "";
    setBookshelfUnlockMessage("密码正确，已打开", "ok");
  } catch (error) {
    setBookshelfUnlockMessage(error.message || "密码不对", "error");
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = "打开抽屉";
    }
  }
});
$("#userFilter").addEventListener("input", renderUsers);
$("#groupFilter").addEventListener("input", renderGroups);
$("#worldbookMemberFilter").addEventListener("input", renderWorldbook);
$("#featureFilter").addEventListener("input", renderFeatureSwitches);
$("#worldbookMembers").addEventListener("click", async (event) => {
  const button = event.target instanceof Element ? event.target.closest("[data-worldbook-edit], [data-worldbook-member], [data-worldbook-save], [data-worldbook-memory-toggle], [data-worldbook-memory-delete], [data-worldbook-delete]") : null;
  if (!button) return;
  event.preventDefault();
  await handleWorldbookMemberAction(button);
});
$("#worldbookGroups").addEventListener("click", async (event) => {
  const button = event.target instanceof Element ? event.target.closest("[data-worldbook-group-save], [data-worldbook-group-delete]") : null;
  if (!button) return;
  event.preventDefault();
  await handleWorldbookGroupAction(button);
});
$("#worldbookImportBtn").addEventListener("click", async () => {
  await runAction(() => postJson("/worldbook/import", {}), "已刷新关系网", $("#worldbookImportBtn"));
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
  }), "已添加关系节点", event.submitter);
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
  }), "已添加群资料", event.submitter);
  event.currentTarget.reset();
});
$("#resetTokenStatsBtn").addEventListener("click", async () => {
  const button = $("#resetTokenStatsBtn");
  if (!requireSecondClick(button, "token-reset", "再次点击清空 Token 统计", "再次点击清空")) return;
  await runAction(() => postJson("/token/reset", {}), "已清空 Token 统计", button);
});

["quickModuleForm", "environmentModuleForm", "privateModuleForm", "groupModuleForm", "worldbookModuleForm", "memoryModuleForm", "longTermModuleForm"].forEach((formId) => {
  const form = document.getElementById(formId);
  if (!form) return;
  form.addEventListener("input", () => markModuleFormDirty(form));
  form.addEventListener("change", () => markModuleFormDirty(form));
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    await runAction(() => postJson("/settings/update", {
      settings: collectFormSettings(`#${formId}`),
    }), "已保存模块配置", event.submitter);
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
  }), "已添加私聊对象", event.submitter);
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
  }, "已添加群聊观测", event.submitter);
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
  }), "已保存群聊名单", event.submitter);
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
  }), "已更新群聊名单", button);
});

$("#saveFeaturesBtn").addEventListener("click", async () => {
  const features = Object.fromEntries(Object.entries(state.featureDraft).filter(([key]) => visibleConfigKey(key)));
  await runAction(() => postJson("/settings/update", { features }), "已保存功能开关", $("#saveFeaturesBtn"));
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
  await runAction(() => postJson("/settings/update", { providers }), "已保存模型配置", $("#saveProvidersBtn"));
});

$("#testAllProvidersBtn").addEventListener("click", async () => {
  for (const key of Object.keys(providerLabels).filter(visibleConfigKey)) {
    await testProvider(key);
  }
});

loadAll();
