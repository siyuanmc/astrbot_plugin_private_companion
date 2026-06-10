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
  bookshelfAccessToken: "",
  selectedBook: null,
  bookshelfPage: "shelf",
  selectedBookSpreadIndex: 0,
  selectedDiaryDate: "",
  selectedBrowsingIndex: 0,
  selectedUserId: "",
  selectedGroupId: "",
  featureDraft: {},
  selectedFeatureKey: "",
  providerFilter: "",
  providerMode: "all",
  providerDraft: {},
  tokenView: "today",
  tokenDate: "",
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
  PLUGIN_VISION_PROVIDER_ID: "插件识图模型",
  NEWS_PROVIDER_ID: "新闻整理",
  WEB_EXPLORATION_PROVIDER_ID: "搜索决策/整理",
};

const privateReadingConfigKeys = new Set([
  "enable_private_reading_integration",
  "enable_private_reading_boredom_read",
  "enable_private_reading_ask_recommendation",
  "enable_private_reading_preference_influence",
  "private_reading_min_interval_hours",
  "private_reading_max_photo_count",
  "private_reading_share_probability",
  "private_reading_ask_probability",
  "private_reading_preference_min_ratings",
  "private_reading_preference_max_terms",
  "private_reading_default_keywords",
  "private_reading_blocked_tags",
]);

function isPrivateReadingAvailable() {
  return Boolean(state.overview?.private_reading?.available);
}

function visibleConfigKey(key) {
  return isPrivateReadingAvailable() || !privateReadingConfigKeys.has(key);
}

const providerGuides = {
  LLM_PROVIDER_ID: {
    purpose: "插件的基础兜底文本模型，主动消息和未单独指定的内部任务都会回退到这里。",
    fit: "适合选综合能力稳定、上下文理解好、指令遵循可靠的主聊天模型。",
    fallback: "留空时使用 AstrBot 默认会话模型。",
  },
  MAI_STYLE_PROVIDER_ID: {
    purpose: "陪伴风格通用模型，也是多数分项能力留空后的第一层兜底。",
    fit: "适合稳定、成本可控、中文口语自然、能守住人格边界的模型。",
    fallback: "留空时跟随主模型。",
  },
  DAILY_PLAN_PROVIDER_ID: {
    purpose: "每天生成粗日程，并在格式异常时做日程重试纠偏。",
    fit: "适合结构化 JSON 稳定、能理解人格/世界观、长一点提示词也不容易跑偏的模型。",
    fallback: "留空时跟随陪伴通用模型。",
  },
  DETAIL_ENHANCEMENT_PROVIDER_ID: {
    purpose: "把当前日程段展开成细节事件、状态变化和可能主动开口的契机。",
    fit: "适合便宜、低延迟、JSON 输出稳定的小到中型模型。",
    fallback: "留空时跟随主模型。",
  },
  DREAM_DIARY_PROVIDER_ID: {
    purpose: "生成每日 Bot 日记、生活碎片、梦境碎片、强化梦境和梦后余韵。",
    fit: "适合短文本意象好、口语自然、能按要求输出 JSON 的模型。",
    fallback: "留空时跟随陪伴通用模型。",
  },
  CREATIVE_PROVIDER_ID: {
    purpose: "生成私下创作项目设定，以及闲暇时的小说、诗、随笔、剧本等正文片段。",
    fit: "适合文风稳定、有创作能力、能遵守角色身份边界的模型。",
    fallback: "留空时跟随陪伴通用模型。",
  },
  VOICE_PROMPT_PROVIDER_ID: {
    purpose: "生成主动语音短句，并修复 TTS 标签、日语或双语格式。",
    fit: "适合短句口语感强、格式遵循稳、不会写得太长的模型。",
    fallback: "留空时跟随陪伴通用模型。",
  },
  PHOTO_PROMPT_PROVIDER_ID: {
    purpose: "只负责生成 photo_text 的画面提示词和画面描述，不影响普通聊天或日程。",
    fit: "适合视觉描述、审美词汇和画面构图更稳定的模型。",
    fallback: "留空时跟随主模型。",
  },
  NARRATION_PROVIDER_ID: {
    purpose: "把识屏等工具结果转成可供最终主动消息使用的自然语言上下文。",
    fit: "适合摘要稳、保留关键事实、不会添油加醋的便宜模型。",
    fallback: "留空时不单独转述，直接使用工具摘要。",
  },
  HISTORY_SUMMARY_PROVIDER_ID: {
    purpose: "把昨日或最近完整对话压成能延续到日程、梦境和主动理解里的摘要。",
    fit: "适合长上下文整理稳定、成本较低、能保留人物和时间线的模型。",
    fallback: "留空时跟随日程生成模型。",
  },
  RESPONSE_REVIEW_PROVIDER_ID: {
    purpose: "只在少数回复不自然时做二次自检和轻改写，减少助手腔、越界和提示词泄露。",
    fit: "适合便宜、短文本改写自然、边界判断稳的模型。",
    fallback: "留空时回退到陪伴通用模型，再回退到主模型。",
  },
  RELATIONSHIP_ANALYSIS_PROVIDER_ID: {
    purpose: "分析关系阶段、亲近度、打扰边界和互动站位，影响后续语气判断。",
    fit: "适合情绪和关系判断细腻、分类稳定、不会过度脑补的模型。",
    fallback: "留空时跟随陪伴通用模型。",
  },
  COMPANION_MEMORY_PROVIDER_ID: {
    purpose: "把原始私聊记忆整理成用户画像、兴趣、边界、关系备注和说话习惯。",
    fit: "适合结构化抽取能力好、便宜、能区分事实和推测的模型。",
    fallback: "留空时跟随陪伴通用模型。",
  },
  DIALOGUE_EPISODE_PROVIDER_ID: {
    purpose: "把私聊片段整理成共同经历、情绪余味、可续话头和未完成约定。",
    fit: "适合对话摘要稳、能保留细节和情绪温度的模型。",
    fallback: "留空时跟随陪伴通用模型。",
  },
  GROUP_INTERJECT_PROVIDER_ID: {
    purpose: "群聊主动插话专用，用来生成很短、自然、不突兀的群聊发言。",
    fit: "适合低延迟、短文本质量好、中文群聊语感稳的模型。",
    fallback: "留空时跟随陪伴通用模型。",
  },
  GROUP_EPISODE_PROVIDER_ID: {
    purpose: "整理群聊最近片段、群氛围、话题线、活跃群友和短期避免重复内容。",
    fit: "适合群聊摘要、多人关系和话题归纳稳定的便宜模型。",
    fallback: "留空时跟随陪伴通用模型。",
  },
  GROUP_SLANG_PROVIDER_ID: {
    purpose: "根据群聊样例解释群内黑话、梗、简称和成员称呼。",
    fit: "适合小模型；重点是分类/释义稳定、别把玩笑当事实。",
    fallback: "留空时跟随陪伴通用模型。",
  },
  GROUP_FOLLOWUP_JUDGE_PROVIDER_ID: {
    purpose: "判断群里用户后续没 @ 的话是否仍在和 Bot 对话，只在规则不确定时调用。",
    fit: "适合便宜、低延迟、YES/NO 分类准确、指令遵循稳定的小模型。",
    fallback: "留空时只使用规则判断。",
  },
  FORWARD_MESSAGE_PROVIDER_ID: {
    purpose: "合并消息选择“转述”模式时，先把合并转发读成自然记录，再交给主模型回应。",
    fit: "适合长上下文整理稳定、成本较低、能保留人物和时间线的模型。",
    fallback: "留空时跟随陪伴通用模型。",
  },
  PLUGIN_VISION_PROVIDER_ID: {
    purpose: "插件自己的视觉理解模型，用于私聊图片/表情包、引用图片、合并消息图片、识屏和素材页理解。",
    fit: "适合确认支持图片输入、视觉描述可靠、能简短转述关键信息的多模态模型。",
    fallback: "留空时先尝试 AstrBot 本体图片转述模型，再回退到工具结果转述或主模型。",
  },
  NEWS_PROVIDER_ID: {
    purpose: "从新闻标题和摘要候选里挑选适合分享的内容，并整理成 Bot 的内部印象。",
    fit: "适合便宜、稳定、短 JSON 输出可靠、能做轻量筛选的小模型。",
    fallback: "留空时跟随主动转述/主模型。",
  },
  WEB_EXPLORATION_PROVIDER_ID: {
    purpose: "不负责联网检索，只决定 Bot 想搜索什么，并把搜索结果整理成探索笔记。",
    fit: "适合便宜、稳定、短 JSON 输出可靠、能归纳搜索结果的模型。",
    fallback: "留空时跟随新闻整理/主模型。",
  },
};

const providerGroups = [
  {
    id: "core",
    title: "基础与兜底",
    desc: "主模型、陪伴通用和最终回复前后的基础能力。",
    keys: ["LLM_PROVIDER_ID", "MAI_STYLE_PROVIDER_ID", "RESPONSE_REVIEW_PROVIDER_ID", "NARRATION_PROVIDER_ID"],
  },
  {
    id: "daily",
    title: "日程与表达",
    desc: "决定 Bot 每天做什么、怎么把生活片段和主动表达写出来。",
    keys: ["DAILY_PLAN_PROVIDER_ID", "DETAIL_ENHANCEMENT_PROVIDER_ID", "DREAM_DIARY_PROVIDER_ID", "CREATIVE_PROVIDER_ID", "VOICE_PROMPT_PROVIDER_ID", "PHOTO_PROMPT_PROVIDER_ID"],
  },
  {
    id: "memory",
    title: "记忆与关系",
    desc: "整理长期画像、对话片段和关系站位。",
    keys: ["HISTORY_SUMMARY_PROVIDER_ID", "RELATIONSHIP_ANALYSIS_PROVIDER_ID", "COMPANION_MEMORY_PROVIDER_ID", "DIALOGUE_EPISODE_PROVIDER_ID"],
  },
  {
    id: "group",
    title: "群聊能力",
    desc: "处理群聊插话、片段整理、黑话释义和续接判断。",
    keys: ["GROUP_INTERJECT_PROVIDER_ID", "GROUP_EPISODE_PROVIDER_ID", "GROUP_SLANG_PROVIDER_ID", "GROUP_FOLLOWUP_JUDGE_PROVIDER_ID", "FORWARD_MESSAGE_PROVIDER_ID"],
  },
  {
    id: "media",
    title: "视觉与外界信息",
    desc: "识图、新闻和主动搜索相关模型。",
    keys: ["PLUGIN_VISION_PROVIDER_ID", "NEWS_PROVIDER_ID", "WEB_EXPLORATION_PROVIDER_ID"],
  },
];

const providerGroupByKey = providerGroups.reduce((acc, group) => {
  group.keys.forEach((key) => { acc[key] = group; });
  return acc;
}, {});

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
  enable_user_habit_learning: ["用户习惯画像", "学习用户常在什么时段做什么、问什么，用于日程细化和主动理解。"],
  enable_humanized_states: ["拟人身体状态", "生成睡眠、梦境、健康、饥饿和周期等连续状态，影响日程、主动消息和被动回复。"],
  enable_segmented_proactive_reply: ["主动分段发送", "把主动消息拆成更像聊天的短句，同时合并过短片段，避免“哈哈”“我也觉得”单独刷成一条。"],
  inject_passive_states: ["被动状态注入", "普通聊天前把当前拟人状态注入提示词，让被动回复也受状态影响。"],
  enable_cycle_state: ["生理周期模拟", "允许符合人格的人类角色出现周期前、周期中和恢复期状态。"],
  enable_skill_growth_simulation: ["技能成长", "技能等级与能力边界。"],
  enable_private_image_self_recognition: ["图片转述增强", "私聊单图防抖、视觉转述等待和角色自我识别。"],
  enable_environment_perception: ["环境感知", "注入当前时间、日期语境、平台、群聊/私聊和消息媒介信息。"],
  enable_holiday_perception: ["节假日感知", "识别工作日、周末、节假日和调休，影响生活节奏判断。"],
  enable_platform_perception: ["平台感知", "识别 QQ/平台、私聊/群聊、群号群名以及图片语音视频消息。"],
  enable_model_perception: ["模型感知", "识别当前会话 LLM、插件任务模型覆盖和视觉转述模型配置。"],
  enable_lunar_perception: ["农历感知", "可用时注入农历日期，辅助节日、生活氛围和日记语境。"],
  enable_solar_term_perception: ["节气感知", "注入当天或临近节气，让日程和表达更贴合时令。"],
  enable_almanac_perception: ["轻量黄历", "生成宜/忌氛围标签，默认关闭，避免玄学感太强。"],
  enable_group_companion: ["群聊总开关", "控制是否处理群聊观察、画像、黑话和上下文注入。"],
  enable_group_slang_learning: ["群黑话学习", "记录群内常用梗、简称和特殊表达。"],
  enable_group_member_profiles: ["群成员画像", "记录成员发言习惯和群内角色，帮助判断气氛。"],
  enable_group_context_injection: ["群上下文注入", "在群聊回复时加入群氛围、话题和成员信息。"],
  enable_forward_message_adaptation: ["合并消息阅读", "读取合并转发节点并整理成自然聊天记录，让 Bot 能理解转发里的发言顺序、人物和话题。"],
  enable_group_scene_awareness: ["群聊场景感知", "推断当前消息是在对 Bot、某个群友还是整个群说话，减少误以为别人都在问自己。"],
  enable_group_reality_promise_guard: ["阻止群聊现实承诺", "群聊里避免承诺自己能拉人、修网、开房间或操作现实设备；私聊扮演不受影响。"],
  enable_group_wakeup_enhancement: ["群聊唤醒强化", "通过强唤醒词、弱相关唤醒词和兴趣关键词，让 Bot 在群里被自然叫到或碰到感兴趣话题时进入回复链。"],
  enable_group_high_intensity_mode: ["群聊高强度收口", "短时间连续被 @、引用或增强唤醒后，自动合并同群后续唤醒消息，并暂停非必要群聊后台任务，减少 LLM 过载。"],
  enable_group_conversation_followup: ["连续对话保持", "群里叫过 Bot 后，短时间内判断同一用户没继续 @ 的话是否仍在对 Bot 说。"],
  enable_group_interjection: ["群主动插话", "允许 Bot 在群聊里主动插一句。谨慎开启。"],
  enable_group_repeat_follow: ["复读处理", "同一句话连续复读超过三次时，可跟读一次或打断一次。"],
  enable_group_topic_threads: ["群话题线", "维护当前群聊正在聊什么，以及话题如何变化。"],
  enable_group_episode_memory: ["群聊片段", "把群聊阶段性内容整理成摘要片段。"],
  enable_group_interjection_feedback: ["插话反馈", "记录群友对主动插话的反应，后续调整频率。"],
  enable_group_slang_meanings: ["黑话释义", "解释群内黑话。"],
  enable_group_relationship_graph: ["群关系网", "记录成员之间的互动关系和常见组合。"],
  enable_group_privacy_guard: ["群隐私保护", "保护私聊信息。"],
  enable_worldbook_member_recognition: ["群聊关系网", "以 QQ 号确认成员身份，昵称和别名只作辅助线索。"],
  enable_atrelay_tools: ["跨群转述与 @ 群友", "整合艾特群友能力，可让模型查询群成员、按关系网解析 @ 对象并发送群聊/私聊消息。"],
  enable_livingmemory_integration: ["LivingMemory 协同", "引导模型按需调用长期记忆工具，避免重复造轮子。"],
  enable_bilibili_integration: ["B 站联动", "读取 B 站 Bot 观看日志，并在合适节点私聊分享。"],
  enable_bilibili_boredom_watch: ["无聊刷 B 站", "空档看视频。"],
  enable_news_integration: ["新闻阅读", "低频读取 RSS/Atom 新闻源，形成近期见闻和主动分享素材。"],
  enable_news_daily_hot_read: ["每日热点", "随日程或后台检查读取热点候选，形成当天的时讯见闻。"],
  enable_news_boredom_read: ["无聊看新闻", "空档或无聊时扫几条新闻，按人格决定是否私聊提起。"],
  enable_ai_daily_watch: ["AI 日报/早报追踪", "按配置时间读取黑鸦早报和橘鸦日报，到点后当天只尝试一次。"],
  enable_external_event_self_link: ["外界信息自我关联", "让新闻和搜索结果先变成“这和我有什么关系”的内部意愿，再进入主动候选。"],
  enable_web_exploration: ["主动搜索", "按人格兴趣、最近话题、日程和心情低频使用 AstrBot 网页搜索，形成探索笔记。"],
  enable_web_exploration_boredom_search: ["空档自主搜索", "空闲或无聊时先自行决定搜索主题，再调用网页搜索了解新鲜事物。"],
  enable_qzone_integration: ["QQ 空间动态", "整合查看、点赞、评论和发布说说入口。"],
  enable_qzone_life_publish: ["生活说说", "根据状态、日程和日记余味低频发布公开生活动态。"],
  enable_photo_text_action: ["主动拍照/生图", "允许 Bot 在合适的主动动机下生成真实图片；本地 ComfyUI 可在电脑忙时自动延后。"],
  enable_private_reading_integration: ["夹层阅读素材", "检测到可用素材能力时，允许作为低频私下阅读来源。"],
  enable_private_reading_boredom_read: ["私下阅读", "空档、无聊或夜里低频自己搜索并阅读，形成内部印象。"],
  enable_private_reading_ask_recommendation: ["征求推荐", "空档或无聊时，低频私聊询问用户有没有好看的本子或漫画推荐。"],
  enable_private_reading_preference_influence: ["私密偏好影响", "评分样本足够后，把稳定偏好作为私聊私密互动的弱背景。"],
  enable_unanswered_screen_peek_followup: ["沉默后窥屏", "主动消息后用户长时间没回、且 Bot 正好无聊时，可免日次数窥屏确认用户在做什么。"],
  enable_proactive_quote_trigger_message: ["群回复/主动引用触发消息", "群聊被 @、引用、唤醒或连续对话保持时，回复引用当前触发消息；群主动插话也可引用，复读跟读/打断不引用。"],
  enable_creative_writing: ["私下创作", "闲暇时可选地因生活小事、日记碎片或梦境灵感写一点文本作品。"],
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
      "enable_user_habit_learning",
      "enable_humanized_states",
      "enable_segmented_proactive_reply",
      "inject_passive_states",
      "enable_cycle_state",
      "enable_skill_growth_simulation",
      "enable_private_image_self_recognition",
    ],
  },
  {
    title: "环境感知",
    note: "时间、节假日、农历节气、平台和消息媒介。",
    keys: [
      "enable_environment_perception",
      "enable_holiday_perception",
      "enable_platform_perception",
      "enable_model_perception",
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
      "enable_group_reality_promise_guard",
      "enable_group_wakeup_enhancement",
      "enable_group_high_intensity_mode",
      "enable_group_conversation_followup",
      "enable_group_slang_learning",
      "enable_group_slang_meanings",
      "enable_group_member_profiles",
      "enable_group_topic_threads",
      "enable_group_episode_memory",
      "enable_group_relationship_graph",
      "enable_proactive_quote_trigger_message",
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
    note: "外部动作和低频分享。",
    keys: [
      "enable_bilibili_integration",
      "enable_bilibili_boredom_watch",
      "enable_news_integration",
      "enable_news_daily_hot_read",
      "enable_ai_daily_watch",
      "enable_news_boredom_read",
      "enable_external_event_self_link",
      "enable_web_exploration",
      "enable_web_exploration_boredom_search",
      "enable_qzone_integration",
      "enable_qzone_life_publish",
      "enable_photo_text_action",
      "enable_private_reading_integration",
      "enable_private_reading_boredom_read",
      "enable_private_reading_ask_recommendation",
      "enable_private_reading_preference_influence",
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
  "enable_user_habit_learning",
  "enable_private_image_self_recognition",
  "enable_environment_perception",
  "enable_holiday_perception",
  "enable_platform_perception",
  "enable_model_perception",
  "enable_worldbook_member_recognition",
  "enable_atrelay_tools",
];

const configLabels = {
  enabled_user_count: "启用私聊对象",
  user_count: "私聊对象总数",
  require_opt_in: "是否需要私聊确认",
  default_style: "默认语气",
  plugin_specific_persona_id: "插件指定人格 ID",
  private_user_aliases: "私聊身份别名归并",
  schedule_persona_prompt: "角色设定补充",
  schedule_worldview_prompt: "世界观/生活背景",
  roleplay_user_profile_prompt: "用户与关系补充",
  max_daily_messages: "每日主动上限",
  inbound_message_debounce_seconds: "重复消息防抖秒数",
  enable_semantic_message_debounce: "语义收口等待",
  semantic_message_debounce_seconds: "语义收口等待秒数",
  enable_proactive_quote_trigger_message: "群回复/主动引用触发消息",
  private_image_vision_wait_seconds: "单图等待识图秒数",
  enable_private_image_self_recognition: "图片转述增强",
  private_image_self_recognition_hint: "角色自我识别线索",
  enable_private_image_vision_cache: "重复图片转述缓存",
  private_image_vision_cache_max_items: "图片转述缓存上限",
  enable_segmented_proactive_reply: "主动分段发送",
  segmented_proactive_scope: "分段作用范围",
  segmented_proactive_threshold: "不分段字数阈值",
  segmented_proactive_min_segment_chars: "短片段合并阈值",
  segmented_proactive_max_segments: "最多分段数",
  segmented_proactive_split_mode: "分段模式",
  segmented_proactive_regex: "分段正则",
  segmented_proactive_split_words: "分段词列表",
  enable_segmented_proactive_content_cleanup: "分段内容清理",
  segmented_proactive_content_cleanup_rule: "清理正则",
  segmented_proactive_content_cleanup_words: "清理词列表",
  segmented_proactive_interval_method: "分段间隔方式",
  segmented_proactive_interval_min: "最小间隔秒数",
  segmented_proactive_interval_max: "最大间隔秒数",
  segmented_proactive_log_base: "对数间隔底数",
  group_conversation_followup_seconds: "群聊续接判断秒数",
  group_conversation_followup_max_turns: "群聊连续续接上限",
  enable_group_conversation_followup: "启用连续对话保持",
  forward_message_mode: "合并消息适配方式",
  forward_message_max_messages: "合并消息最多读取条数",
  forward_message_max_chars: "合并消息注入字数上限",
  forward_message_parse_nested: "展开嵌套合并消息",
  forward_message_image_vision: "合并消息图片视觉",
  forward_message_image_limit: "合并消息视觉图片上限",
  max_group_recent_messages: "群聊最近消息上限",
  max_group_slang_terms: "群黑话上限",
  daily_token_limit: "每日 Token 限额",
  enable_daily_token_soft_limit: "启用每日 Token 软限额",
  daily_token_soft_limit: "每日 Token 软限额",
  humanized_state_intensity: "拟人状态强度",
  enable_humanized_states: "拟人身体状态",
  inject_passive_states: "被动状态注入",
  enable_cycle_state: "生理周期模拟",
  worldview_adaptation_mode: "世界观适配模式",
  worldview_adaptation_prompt: "自定义世界观适配",
  environment_perception_timezone: "环境感知时区",
  holiday_country: "节假日地区",
  enable_holiday_perception: "节假日/工作日",
  enable_platform_perception: "平台与消息类型",
  enable_model_perception: "当前模型配置",
  enable_lunar_perception: "农历",
  enable_solar_term_perception: "节气",
  enable_almanac_perception: "轻量黄历",
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
  group_wakeup_direct_words: "强唤醒词",
  group_wakeup_context_words: "弱相关唤醒词",
  group_wakeup_interest_keywords: "手动兴趣关键词",
  group_wakeup_interest_probability: "兴趣唤醒概率",
  group_wakeup_cooldown_seconds: "唤醒冷却秒数",
  group_wakeup_generated_keyword_limit: "自动兴趣词上限",
  group_wakeup_topic_interest_max_boost: "话题兴趣权重上限",
  group_wakeup_debounce_pending_penalty: "收口等待兴趣降权",
  group_wakeup_fatigue_limit: "唤醒疲劳阈值",
  group_wakeup_fatigue_decay_minutes: "疲劳恢复分钟",
  group_wakeup_log_limit: "唤醒记录上限",
  enable_group_high_intensity_mode: "群聊高强度收口",
  group_high_intensity_wakeup_window_seconds: "高强度窗口秒数",
  group_high_intensity_wakeup_threshold: "高强度唤醒阈值",
  group_high_intensity_cooldown_seconds: "收口持续秒数",
  group_high_intensity_merge_seconds: "合并等待秒数",
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
  user_habit_min_count: "习惯成型次数",
  user_habit_max_items: "习惯条目上限",
  skill_growth_rate: "技能成长倍率",
  skill_growth_custom_skills: "自定义技能",
  enable_skill_growth_schedule_influence: "技能影响日程",
  skill_growth_schedule_influence_strength: "日程影响强度",
  bilibili_boredom_min_interval_hours: "B 站触发间隔",
  bilibili_share_probability: "视频分享概率",
  bilibili_share_min_score: "视频分享最低评分",
  news_min_interval_hours: "新闻读取间隔",
  news_share_probability: "新闻分享概率",
  enable_external_event_self_link: "外界信息自我关联",
  external_event_self_link_probability: "自我关联分享欲倍率",
  external_event_self_link_cooldown_hours: "自我关联冷却",
  news_max_items_per_source: "单源读取条数",
  news_sources: "新闻源",
  enable_ai_daily_watch: "AI 日报/早报追踪",
  ai_daily_sources: "AI 日报/早报来源",
  ai_daily_source_uid: "兼容旧版 UP 主 UID",
  ai_daily_check_window: "旧版检查窗口",
  ai_daily_check_interval_minutes: "旧版检查间隔",
  ai_daily_prefer_text_version: "优先文字版",
  enable_news_daily_hot_read: "每日获取热点",
  enable_news_boredom_read: "无聊看新闻",
  news_hot_sources: "热点来源",
  news_hot_max_items: "热点候选数量",
  web_exploration_min_interval_hours: "网页探索间隔",
  web_exploration_share_probability: "探索分享概率",
  web_exploration_max_results: "搜索结果数",
  web_exploration_interests: "探索兴趣倾向",
  enable_web_exploration_boredom_search: "空档自主搜索",
  qzone_life_publish_min_interval_hours: "说说最小间隔",
  qzone_life_publish_probability: "说说触发概率",
  enable_photo_text_action: "主动拍照/生图",
  photo_action_max_daily: "每日主动生图上限",
  photo_generation_backend: "主动生图后端",
  COMFYUI_TEXT2IMG_WORKFLOW_NAME: "文生图工作流",
  COMFYUI_SELFIE_WORKFLOW_NAME: "自拍工作流",
  comfyui_photo_wait_seconds: "本地生图等待秒数",
  enable_local_photo_load_guard: "电脑高负荷保护",
  local_photo_cpu_busy_percent: "CPU 忙碌阈值",
  local_photo_memory_busy_percent: "内存忙碌阈值",
  local_photo_defer_minutes: "忙时延后分钟数",
  EXTERNAL_IMAGE_API_BASE_URL: "在线图片 API 地址",
  EXTERNAL_IMAGE_API_MODEL: "在线图片模型",
  external_image_api_size: "在线生图尺寸",
  external_image_api_timeout_seconds: "在线生图超时秒数",
  photo_generation_style: "主动生图风格",
  photo_generation_style_custom_prompt: "自定义风格说明",
  private_reading_min_interval_hours: "阅读最小间隔",
  private_reading_max_photo_count: "页数上限",
  private_reading_share_probability: "主动提起概率",
  private_reading_default_keywords: "默认搜索关键词",
  private_reading_blocked_tags: "过滤标签",
  private_reading_ask_probability: "征求推荐概率",
  private_reading_preference_min_ratings: "偏好生效最少评分数",
  private_reading_preference_max_terms: "偏好注入最多词条",
  unanswered_screen_peek_after_minutes: "沉默多久后窥屏",
  unanswered_screen_peek_cooldown_minutes: "沉默窥屏冷却",
  creative_inspiration_probability: "创作灵感概率",
  creative_share_probability: "创作透露概率",
  creative_chars_per_session: "每次创作字数",
  creative_max_active_projects: "同时创作项目上限",
  active_projects: "进行中创作",
  project_count: "创作项目",
  boredom_watch_enabled: "无聊刷视频",
  hidden_mode: "低调模式",
};

const configDescriptions = {
  default_style: "没有单独学习到用户偏好时，插件用于生成日程、状态和主动行为的基础语气参考。",
  plugin_specific_persona_id: "填写 AstrBot 人格 ID 后，插件会优先使用该人格作为主回复人格；留空则继承 AstrBot 当前默认人格。不同于角色设定补充，它会影响私聊被动回复和关系判断。",
  private_user_aliases: "把临时会话 ID、异常 sender_id 或机器人侧误报 ID 归并到主 QQ。每行一个映射，例如：688C2CE7...=100012345。",
  schedule_persona_prompt: "给陪伴插件的日程、状态、主动行为、识图和创作提供角色补充；不会覆盖 AstrBot 主人格。",
  schedule_worldview_prompt: "给陪伴插件判断生活背景和世界规则，适合写所在世界、日常规则、居住/学校/城市环境和与用户的生活关系。",
  roleplay_user_profile_prompt: "描述角色如何称呼用户、用户身份、彼此关系和相处方式；不会作为图片自我识别的外观线索。",
  humanized_state_intensity: "控制失眠、生病、饥饿、周期等状态出现概率和能量影响强度，范围 0-100。",
  enable_humanized_states: "总开关。关闭后不再生成拟人身体/梦境状态，只保留基础平稳状态。",
  inject_passive_states: "开启后普通聊天也会吃到当前拟人状态；关闭后状态主要影响日程和主动行为。",
  enable_cycle_state: "开启后，且人格适合人类身体设定时，才允许出现周期相关状态；非人类人格会自动判定不适用。",
  environment_perception_timezone: "用于判断当前时段、日期语境、节假日和日程跨日。默认 Asia/Shanghai。",
  holiday_country: "节假日识别地区。目前主要用于 CN，未安装依赖时会自动退化为周末/工作日。",
  enable_holiday_perception: "开启后会把节假日、调休和工作日判断注入环境感知。",
  enable_platform_perception: "开启后会识别平台、私聊/群聊和消息媒介类型。",
  enable_model_perception: "开启后会把当前会话 LLM、插件分项模型和视觉转述模型作为环境信息注入；只供 Bot 判断能力边界，不要求主动报告模型名。",
  enable_lunar_perception: "开启后在依赖可用时注入农历日期。",
  enable_solar_term_perception: "开启后注入当天或近三天节气提示。",
  enable_almanac_perception: "开启后生成轻量宜忌氛围标签，只作表达参考。",
  idle_minutes: "用户多久没有活跃后，才被视为适合主动触达或分享的空闲状态。",
  min_interval_minutes: "同一私聊对象两次主动消息之间的最小间隔，避免频繁打扰。",
  max_daily_messages: "每个私聊对象每天最多收到多少条插件主动消息。",
  daily_token_limit: "插件内部 LLM 任务的每日硬限额，达到后跳过非豁免后台调用。0 表示不限。",
  enable_daily_token_soft_limit: "作为达到限额就停止插件/停止后台链路的替代方案。开启后，达到软限额时暂缓新闻、网页探索、创作、群整理、自检和主动生图等低优先级后台任务，优先保留用户当下触发的回复。",
  daily_token_soft_limit: "今日插件内部 LLM 消耗达到该值后进入软降载。0 表示关闭软限额，只保留每日硬限额。",
  inbound_message_debounce_seconds: "拦截平台或适配器短时间重复上报的同一条用户消息；不是等待用户补话的收口窗口。",
  enable_semantic_message_debounce: "开启后，Bot 会短暂等待用户补完，把连续文字或先图后文当作同一轮发言理解。",
  semantic_message_debounce_seconds: "真正的语义收口窗口。用户继续补充时，会把窗口内文本和图片当成一轮完整发言。",
  enable_proactive_quote_trigger_message: "开启后，群聊被 @、引用、唤醒或连续对话保持时，Bot 的普通回复会引用当前触发消息；群聊主动插话会引用触发消息；模型预约的私聊主动若能追溯到同一私聊消息，也会引用。复读跟读/打断不会引用。",
  private_image_vision_wait_seconds: "私聊单图确认没有继续补充后，最多等待视觉转述多久。不是图片防抖时间；视觉提前完成会立刻进入主链。",
  private_image_self_recognition_hint: "只补充当前角色自己的外观、头像、名字、表情包特征或聊天截图昵称，让视觉转述更容易判断图里是不是当前角色。不要写用户资料。",
  enable_private_image_vision_cache: "开启后，同一张图片或表情包会按内容哈希复用上次视觉摘要，避免重复调用识图模型；不会缓存最终聊天回复。",
  private_image_vision_cache_max_items: "最多保留多少条图片视觉摘要缓存。达到上限后会清理最久未命中的旧缓存，0 表示不限制。",
  segmented_proactive_threshold: "主动文本短于或等于该字数时才考虑分段；太长的内容保持一整条，避免读起来散。",
  segmented_proactive_scope: "插件主动只影响插件主动消息；全部 LLM 回复会额外拆普通模型纯文本回复，图片、语音、AT 或工具转述等复杂消息不会拆。",
  segmented_proactive_min_segment_chars: "分段后短于或等于该字数的片段会并入相邻消息，避免“哈哈”“我也觉得”这类附和语单独发出。",
  segmented_proactive_max_segments: "一次主动消息最多拆成几条。默认 3，过高会显得刷屏。",
  segmented_proactive_split_mode: "regex 使用正则切句；words 使用分段词列表，更适合清理句号、空格等固定分隔符。网址会自动保护，不会被按点号或斜杠拆开。",
  segmented_proactive_regex: "分段模式为 regex 时使用的切分正则。",
  segmented_proactive_split_words: "分段模式为 words 时使用的分段词。推荐一行一个；中文逗号要单独写一行，或写“逗号”。英文点号会把连续 ... 当成一个省略号边界；网址内部字符会自动保护，完整网址结束处可作为自然断点；括号或引号内部字符会跳过。",
  enable_segmented_proactive_content_cleanup: "开启后会在分段时清理分隔符或无意义字符。",
  segmented_proactive_content_cleanup_rule: "regex 模式下的后清理正则。",
  segmented_proactive_content_cleanup_words: "words 模式下的后清理词。可用于清理句号、空格等词模式分隔符。",
  segmented_proactive_interval_method: "log 会按分段长度计算自然间隔；random 会在最小/最大间隔之间随机。",
  segmented_proactive_interval_min: "两段主动消息之间的最小等待秒数。",
  segmented_proactive_interval_max: "两段主动消息之间的最大等待秒数。",
  segmented_proactive_log_base: "对数间隔的底数。数值越小，长句间隔增长越明显。",
  group_conversation_followup_seconds: "群里用户叫过 Bot 后，后续未 @ 的消息在多久内可能被判断为仍在对 Bot 说。",
  group_conversation_followup_max_turns: "一次群聊连续对话最多自动续接几轮，防止 Bot 一直卷进对话。",
  group_interject_min_interval_minutes: "同一群两次主动插话之间的最小间隔。",
  group_interject_max_daily: "每个群每天最多允许几次主动插话。",
  group_repeat_follow_probability: "群里同一句话复读超过阈值后，Bot 跟读一次的基础概率。这里以百分比填写。",
  group_repeat_interrupt_probability: "复读链持续时，Bot 打断复读的基础概率。这里以百分比填写。",
  group_repeat_interrupt_probability_step: "复读越久，跟读/打断概率共同增加的步进。这里以百分比填写。",
  group_repeat_interrupt_text: "选择文本打断时发送的句子，例如“禁止复读”。",
  group_repeat_interrupt_image_path: "表情包路径。填写后可用图片代替打断文本。",
  group_scene_recent_limit: "判断群聊场景时参考最近多少条群消息。",
  enable_group_reality_promise_guard: "仅群聊生效。开启后 Bot 不会承诺自己能拉人、修网、开房间、登录或操作现实设备；私聊扮演不受影响。",
  group_wakeup_direct_words: "消息中出现即唤醒 Bot。适合填写 Bot 名字、昵称、固定称呼。多个词可用换行、逗号或顿号分隔。",
  group_wakeup_context_words: "与 Bot 身份、称呼或设定弱相关的关键词。命中后不会直接回复，而是先结合群聊上下文、关系网和句式判断是否适合自然接话。适合填写“机器人”“bot”、外号、作品名、设定称呼或常被拿来指代 Bot 的梗；不适合填“你怎么看”“问问你”这类泛请求句。",
  group_wakeup_interest_keywords: "手动补充 Bot 感兴趣的话题关键词。命中后按概率唤醒，不会每次都抢话。",
  group_wakeup_interest_probability: "群聊出现兴趣关键词时进入回复链的基础概率，填写 0-100。",
  group_wakeup_cooldown_seconds: "判断唤醒和兴趣唤醒的冷却时间，防止群聊里连续关键词刷屏。",
  group_wakeup_generated_keyword_limit: "自动从人格兴趣、技能、群话题和黑话中抽取多少个兴趣关键词参与判断。",
  group_wakeup_topic_interest_max_boost: "兴趣词如果同时出现在当前句、近几句或活跃话题线里，最多额外提高多少百分比的兴趣唤醒概率。",
  group_wakeup_debounce_pending_penalty: "同一群友正在语义收口等待时，兴趣唤醒概率降低多少百分比，避免等补充时又抢话。",
  group_wakeup_fatigue_limit: "短时间多次唤醒累计到多少点后，Bot 会更保守、更省力。强唤醒词仍然能叫到它。",
  group_wakeup_fatigue_decay_minutes: "每隔多少分钟自然恢复 1 点唤醒疲劳。数值越大，越会保留“刚被频繁叫到”的感觉。",
  group_wakeup_log_limit: "每个群最多保留多少条唤醒命中、冷却拦截和兴趣未触发记录。",
  enable_group_high_intensity_mode: "短时间连续被明确叫到后自动进入收口降载，合并同群后续唤醒消息，并暂停弱相关/兴趣唤醒、群片段整理、黑话释义刷新和主动插话。",
  group_high_intensity_wakeup_window_seconds: "统计连续唤醒的时间窗口。默认 60 秒，即一分钟内连续被叫到才进入高强度收口。",
  group_high_intensity_wakeup_threshold: "窗口内达到多少次唤醒后进入收口。默认 3 次，用于减少连续 @、连续引用造成的多次 LLM 调用。",
  group_high_intensity_cooldown_seconds: "进入收口降载后维持多久。期间明确 @ 或引用会被合并处理，非必要后台动作会让路。",
  group_high_intensity_merge_seconds: "高强度期间第一条明确叫到 Bot 的消息会等待多久，用来把同一群后续叫 Bot 的消息合并进同一轮回复。",
  forward_message_mode: "注入：把合并消息摘要塞进主模型上下文；转述：先用专门模型读一遍再交给主模型。",
  forward_message_max_messages: "合并消息最多读取多少条节点，过多会截断。",
  forward_message_max_chars: "注入模式下放进主模型上下文的最大字符数。",
  forward_message_parse_nested: "是否继续展开合并消息里的嵌套合并消息。",
  forward_message_image_vision: "合并消息里出现图片时，按出现顺序交给视觉模型生成简短说明，再作为消息集上下文交给 Bot。",
  forward_message_image_limit: "单次合并消息最多转述多少张图片，超过上限的图片仍会保留占位。",
  max_group_recent_messages: "每个群保存的最近消息数量，用于场景、话题和插话判断。",
  max_group_slang_terms: "每个群最多保留多少条黑话/简称候选。",
  memory_refresh_interval_minutes: "长期画像整理的最小间隔，越短越容易产生模型调用。",
  max_companion_memory_items: "每个私聊对象最多保留多少条长期画像条目。",
  max_learned_expression_items: "每个私聊对象最多保留多少条表达习惯样本。",
  episode_memory_refresh_messages: "累计多少条私聊消息后尝试整理一次对话片段。",
  episode_memory_refresh_minutes: "距离上次整理多久后允许再次整理私聊片段。",
  max_dialogue_episodes: "每个私聊对象最多保留多少条对话片段。",
  user_habit_min_count: "同一时段同类行为至少出现多少次，才被视为可用于提示词的用户习惯。",
  user_habit_max_items: "每个私聊对象最多保留多少条行为习惯模式。",
  skill_growth_rate: "技能经验增长倍率。1 为默认速度，越高升级越快。",
  skill_growth_custom_skills: "手动补充技能名，可用逗号、换行或 JSON 列表表达。",
  enable_skill_growth_schedule_influence: "开启后技能等级会约束日程表现，例如高等级物理不再被常规物理题难住。",
  skill_growth_schedule_influence_strength: "技能等级影响日程生成的强度，0 表示只记录不约束。",
  bilibili_boredom_min_interval_hours: "Bot 无聊刷 B 站的最小间隔。",
  bilibili_share_probability: "看完视频后主动分享给用户的概率，0-1。",
  bilibili_share_min_score: "视频评分达到多少才考虑分享。",
  enable_news_daily_hot_read: "每日随日程生成或后台检查读取一次热点，形成新闻见闻。",
  enable_news_boredom_read: "开启后 Bot 空闲或无聊时会低频读取新闻。",
  news_min_interval_hours: "无聊看新闻的最小间隔。",
  news_share_probability: "新闻阅读后主动私聊分享的概率，0-1。",
  enable_external_event_self_link: "开启后，Bot 会把新闻和搜索结果先与自己的模型、能力、兴趣、创作、日程或关系做关联判断，再决定是否产生主动分享欲。不是关键词硬触发。",
  external_event_self_link_probability: "自我关联判断通过后进入主动候选的概率倍率，0-1。越高越容易因为与自己有关的新鲜事来找用户。",
  external_event_self_link_cooldown_hours: "同一用户两次因外界信息自我关联而主动找人的最小间隔。",
  news_max_items_per_source: "每个新闻源最多读取多少条候选。",
  news_sources: "新闻源地址。可填 RSS/Atom、B 站空间链接、bilibili:UID、bvid:BV... 或单条 B 站视频链接。AI 日报/早报建议使用定时来源，避免普通新闻阅读反复访问 UP 空间。",
  enable_ai_daily_watch: "开启后按来源配置的固定时间读取 AI 日报/早报；默认 12:00 黑鸦Heya早报，23:00 橘鸦Juya日报。",
  ai_daily_sources: "每行一个来源：名称|UP主名|UID|关键词|HH:MM。到点后当天只尝试一次，会优先文字版，再尝试字幕和视频公开信息。",
  ai_daily_source_uid: "旧版单 UP 配置兼容项。新版本请优先使用 AI 日报/早报来源。",
  ai_daily_check_window: "旧版窗口轮询兼容项。定时来源按每行 HH:MM 执行。",
  ai_daily_check_interval_minutes: "旧版窗口轮询兼容项。定时来源到点后当天只尝试一次。",
  ai_daily_prefer_text_version: "开启后优先读取视频简介里的文字版链接，失败时尝试公开视频字幕，再退回视频公开信息。",
  news_hot_sources: "热点来源配置。用于每日热点候选。",
  news_hot_max_items: "热点候选最多抓取多少条。",
  web_exploration_interests: "主动搜索时的兴趣倾向。不是硬名单，Bot 会结合人格、日程和最近聊天自行决定。",
  enable_web_exploration_boredom_search: "开启后 Bot 空闲或无聊时会自己决定搜索主题并调用网页搜索。",
  web_exploration_min_interval_hours: "两次自主搜索之间的最小间隔。",
  web_exploration_share_probability: "完成探索后，主动私聊分享的概率，0-1。",
  web_exploration_max_results: "每次调用 AstrBot 网页搜索时最多读取多少条结果。",
  qzone_life_publish_min_interval_hours: "两次低频生活说说之间的最小间隔。",
  qzone_life_publish_probability: "满足条件时发布生活说说的概率，0-1。",
  photo_action_max_daily: "每个私聊对象每天最多生成几张主动图片。真实生成成功就消耗额度，避免失败重试时反复生图。",
  photo_generation_backend: "auto 优先本地 ComfyUI；电脑高负荷且在线图片 API 可用时会绕开本地。comfyui 只用本地，external 只用在线。",
  COMFYUI_TEXT2IMG_WORKFLOW_NAME: "用于普通随手拍、风景、桌面小物等 photo_text 的 ComfyUI 工作流名。",
  COMFYUI_SELFIE_WORKFLOW_NAME: "用于自拍或人像类 photo_text 的 ComfyUI 工作流名。",
  comfyui_photo_wait_seconds: "本地 ComfyUI 工作流最多等待多久。超时后不会假装已经拍照。",
  enable_local_photo_load_guard: "开启后，本地 ComfyUI 生图前读取 CPU/内存负载；负载偏高时延后本次主动计划，或在 auto 模式下改走在线图片 API。",
  local_photo_cpu_busy_percent: "CPU 使用率达到该百分比时，暂缓本地 ComfyUI 生图。需要 psutil 可用；不可用时会放行。",
  local_photo_memory_busy_percent: "内存使用率达到该百分比时，暂缓本地 ComfyUI 生图。",
  local_photo_defer_minutes: "只有本地 ComfyUI 可用且电脑忙时，保留原主动计划并延后这么久再重试。",
  EXTERNAL_IMAGE_API_BASE_URL: "OpenAI 兼容在线生图接口地址。API Key 仍在 AstrBot 原配置页维护，不在拓展页回显。",
  EXTERNAL_IMAGE_API_MODEL: "在线图片模型名。填写后配合 API 地址和 Key 可作为 external 或 auto 的备选后端。",
  external_image_api_size: "在线生图尺寸，例如 1024x1024、768x1344。",
  external_image_api_timeout_seconds: "等待在线图片 API 返回结果的最长时间。",
  photo_generation_style: "影响主动生图提示词的整体风格倾向，可填 真实、二次元 或 其他。",
  photo_generation_style_custom_prompt: "当风格为“其他”时，把这里作为额外风格要求注入生图提示词。",
  private_reading_min_interval_hours: "两次私下阅读之间的最小间隔。",
  private_reading_max_photo_count: "只阅读页数不超过该值的素材，避免视觉理解成本过高。",
  private_reading_share_probability: "读完后主动提起阅读体验的概率，0-1。",
  private_reading_default_keywords: "私下阅读时默认搜索关键词。多个词可用逗号或换行分隔。",
  private_reading_blocked_tags: "过滤标签。匹配到这些标签时跳过对应素材。",
  private_reading_ask_probability: "无聊时向用户征求推荐的概率，0-1。",
  private_reading_preference_min_ratings: "累计评分达到这个数量后，偏好画像才会影响私聊私密互动。",
  private_reading_preference_max_terms: "每次注入最多参考多少个稳定偏好词，避免上下文太长或风格偏移。",
  unanswered_screen_peek_after_minutes: "主动消息发出后，用户沉默多久才允许尝试识屏观察。",
  unanswered_screen_peek_cooldown_minutes: "沉默识屏触发后的冷却时间。",
  creative_inspiration_probability: "从生活小事、梦境或日记里长出创作灵感的概率，0-1。",
  creative_share_probability: "创作达到节点后自然透露给用户的概率，0-1。",
  creative_chars_per_session: "每次闲暇创作行为大约写多少字；实际字数会受人格和当天能量影响。",
  creative_max_active_projects: "同时保留多少个进行中的创作项目。",
  worldbook_auto_import: "启动或打开页面时自动从关系网资料源刷新用户/群资料。",
  worldbook_member_match_aliases: "提到别名或称呼时辅助匹配 QQ 锚点，但 QQ 号仍是身份主锚点。",
  worldbook_self_registration: "群成员 @Bot 说“我是 XX”时，允许进入二次确认的自登记流程。",
  worldbook_auto_pending_observations: "根据低频互动生成待确认观察，不直接写死到资料正文。",
  worldbook_member_inject_limit: "单次回复最多自动注入多少个相关用户词条。",
  worldbook_config_paths: "关系网资料来源路径。用于读取既有资料，不应写死在代码里。",
  atrelay_require_worldbook_first: "转述或 @ 群友时优先用关系网解析，避免群名片变化导致认错人。",
  atrelay_member_cache_minutes: "群成员列表缓存时间，减少频繁查询。",
  atrelay_sensitive_confirm: "敏感、私密或带情绪的转述是否先向用户确认。",
  atrelay_default_relay_style: "默认转述方式：persona 按人格改写，soft 委婉，original 原话。",
  atrelay_multi_target_limit: "一次转述最多允许几个目标，防止刷屏。",
};

const featureSettingGroups = {
  enable_mai_style_integration: ["default_style", "idle_minutes", "min_interval_minutes", "max_daily_messages"],
  enable_companion_memory: ["memory_refresh_interval_minutes", "max_companion_memory_items"],
  enable_expression_learning: ["max_learned_expression_items"],
  enable_companion_reply_planner: ["default_style"],
  enable_intent_emotion_analysis: ["default_style"],
  enable_response_self_review: [],
  enable_passive_topic_suppression: ["min_interval_minutes"],
  enable_relationship_state_machine: ["default_style"],
  enable_dialogue_episode_memory: ["episode_memory_refresh_messages", "episode_memory_refresh_minutes", "max_dialogue_episodes"],
  enable_open_loop_tracking: ["max_dialogue_episodes"],
  enable_user_habit_learning: ["user_habit_min_count", "user_habit_max_items"],
  enable_humanized_states: ["humanized_state_intensity", "inject_passive_states", "enable_cycle_state"],
  enable_segmented_proactive_reply: ["segmented_proactive_scope", "segmented_proactive_threshold", "segmented_proactive_min_segment_chars", "segmented_proactive_max_segments", "segmented_proactive_split_mode", "segmented_proactive_regex", "segmented_proactive_split_words", "enable_segmented_proactive_content_cleanup", "segmented_proactive_content_cleanup_rule", "segmented_proactive_content_cleanup_words", "segmented_proactive_interval_method", "segmented_proactive_interval_min", "segmented_proactive_interval_max", "segmented_proactive_log_base"],
  inject_passive_states: ["humanized_state_intensity"],
  enable_cycle_state: ["humanized_state_intensity"],
  enable_skill_growth_simulation: ["skill_growth_rate", "skill_growth_custom_skills", "enable_skill_growth_schedule_influence", "skill_growth_schedule_influence_strength"],
  enable_private_image_self_recognition: ["enable_semantic_message_debounce", "inbound_message_debounce_seconds", "semantic_message_debounce_seconds", "private_image_vision_wait_seconds", "enable_private_image_vision_cache", "private_image_vision_cache_max_items", "private_image_self_recognition_hint"],
  enable_semantic_message_debounce: ["inbound_message_debounce_seconds", "semantic_message_debounce_seconds", "private_image_vision_wait_seconds"],
  enable_environment_perception: ["environment_perception_timezone", "holiday_country", "enable_holiday_perception", "enable_platform_perception", "enable_model_perception", "enable_lunar_perception", "enable_solar_term_perception", "enable_almanac_perception"],
  enable_holiday_perception: ["holiday_country"],
  enable_platform_perception: ["environment_perception_timezone"],
  enable_model_perception: [],
  enable_lunar_perception: ["environment_perception_timezone"],
  enable_solar_term_perception: ["environment_perception_timezone"],
  enable_almanac_perception: ["environment_perception_timezone"],
  enable_group_companion: ["max_group_recent_messages", "max_group_slang_terms"],
  enable_group_context_injection: ["max_group_recent_messages", "group_scene_recent_limit"],
  enable_forward_message_adaptation: ["forward_message_mode", "forward_message_max_messages", "forward_message_max_chars", "forward_message_parse_nested", "forward_message_image_vision", "forward_message_image_limit"],
  enable_group_scene_awareness: ["group_scene_recent_limit", "group_conversation_followup_seconds", "group_conversation_followup_max_turns"],
  enable_group_wakeup_enhancement: ["group_wakeup_direct_words", "group_wakeup_context_words", "group_wakeup_interest_keywords", "group_wakeup_interest_probability", "group_wakeup_topic_interest_max_boost", "group_wakeup_debounce_pending_penalty", "group_wakeup_cooldown_seconds", "group_wakeup_generated_keyword_limit", "group_wakeup_fatigue_limit", "group_wakeup_fatigue_decay_minutes", "group_wakeup_log_limit", "enable_group_high_intensity_mode", "group_high_intensity_wakeup_window_seconds", "group_high_intensity_wakeup_threshold", "group_high_intensity_cooldown_seconds", "group_high_intensity_merge_seconds", "group_scene_recent_limit"],
  enable_group_high_intensity_mode: ["group_high_intensity_wakeup_window_seconds", "group_high_intensity_wakeup_threshold", "group_high_intensity_cooldown_seconds", "group_high_intensity_merge_seconds"],
  enable_group_conversation_followup: ["group_conversation_followup_seconds", "group_conversation_followup_max_turns"],
  enable_group_slang_learning: ["max_group_slang_terms", "max_group_recent_messages"],
  enable_group_slang_meanings: ["max_group_slang_terms"],
  enable_group_member_profiles: ["max_group_recent_messages"],
  enable_group_topic_threads: ["max_group_recent_messages"],
  enable_group_episode_memory: ["max_group_recent_messages"],
  enable_group_relationship_graph: ["max_group_recent_messages"],
  enable_group_interjection: ["group_interject_min_interval_minutes", "group_interject_max_daily"],
  enable_group_repeat_follow: ["group_repeat_follow_probability", "group_repeat_interrupt_probability", "group_repeat_interrupt_probability_step", "group_repeat_interrupt_text", "group_repeat_interrupt_image_path"],
  enable_group_interjection_feedback: ["group_interject_min_interval_minutes", "group_interject_max_daily"],
  enable_group_privacy_guard: [],
  enable_worldbook_member_recognition: ["worldbook_auto_import", "worldbook_member_match_aliases", "worldbook_self_registration", "worldbook_auto_pending_observations", "worldbook_member_inject_limit", "worldbook_config_paths"],
  enable_atrelay_tools: ["atrelay_require_worldbook_first", "atrelay_member_cache_minutes", "atrelay_sensitive_confirm", "atrelay_default_relay_style", "atrelay_multi_target_limit"],
  enable_livingmemory_integration: [],
  enable_bilibili_integration: ["bilibili_boredom_min_interval_hours", "bilibili_share_probability", "bilibili_share_min_score"],
  enable_bilibili_boredom_watch: ["bilibili_boredom_min_interval_hours", "bilibili_share_probability", "bilibili_share_min_score"],
  enable_news_integration: ["enable_news_daily_hot_read", "enable_ai_daily_watch", "enable_news_boredom_read", "enable_external_event_self_link", "news_hot_sources", "news_hot_max_items", "news_sources", "ai_daily_sources", "ai_daily_prefer_text_version", "news_min_interval_hours", "news_share_probability", "external_event_self_link_probability", "external_event_self_link_cooldown_hours", "news_max_items_per_source"],
  enable_news_daily_hot_read: ["news_hot_sources", "news_hot_max_items", "enable_ai_daily_watch", "ai_daily_sources"],
  enable_ai_daily_watch: ["ai_daily_sources", "ai_daily_prefer_text_version"],
  enable_news_boredom_read: ["news_min_interval_hours", "news_share_probability", "enable_external_event_self_link", "external_event_self_link_probability", "external_event_self_link_cooldown_hours", "news_max_items_per_source"],
  enable_external_event_self_link: ["external_event_self_link_probability", "external_event_self_link_cooldown_hours", "news_share_probability", "web_exploration_share_probability"],
  enable_web_exploration: ["web_exploration_interests", "enable_web_exploration_boredom_search", "web_exploration_min_interval_hours", "web_exploration_share_probability", "enable_external_event_self_link", "external_event_self_link_probability", "external_event_self_link_cooldown_hours", "web_exploration_max_results"],
  enable_web_exploration_boredom_search: ["web_exploration_interests", "web_exploration_min_interval_hours", "enable_external_event_self_link", "external_event_self_link_probability", "external_event_self_link_cooldown_hours", "web_exploration_max_results"],
  enable_qzone_integration: ["qzone_life_publish_min_interval_hours", "qzone_life_publish_probability"],
  enable_qzone_life_publish: ["qzone_life_publish_min_interval_hours", "qzone_life_publish_probability"],
  enable_photo_text_action: ["photo_action_max_daily", "photo_generation_backend", "COMFYUI_TEXT2IMG_WORKFLOW_NAME", "COMFYUI_SELFIE_WORKFLOW_NAME", "comfyui_photo_wait_seconds", "enable_local_photo_load_guard", "local_photo_cpu_busy_percent", "local_photo_memory_busy_percent", "local_photo_defer_minutes", "EXTERNAL_IMAGE_API_BASE_URL", "EXTERNAL_IMAGE_API_MODEL", "external_image_api_size", "external_image_api_timeout_seconds", "photo_generation_style", "photo_generation_style_custom_prompt"],
  enable_private_reading_integration: ["private_reading_min_interval_hours", "private_reading_max_photo_count", "private_reading_default_keywords", "private_reading_blocked_tags", "enable_private_reading_preference_influence", "private_reading_preference_min_ratings", "private_reading_preference_max_terms"],
  enable_private_reading_boredom_read: ["private_reading_min_interval_hours", "private_reading_max_photo_count", "private_reading_share_probability", "private_reading_default_keywords", "private_reading_blocked_tags", "enable_private_reading_preference_influence", "private_reading_preference_min_ratings", "private_reading_preference_max_terms"],
  enable_private_reading_ask_recommendation: ["private_reading_ask_probability"],
  enable_private_reading_preference_influence: ["private_reading_preference_min_ratings", "private_reading_preference_max_terms"],
  enable_unanswered_screen_peek_followup: ["unanswered_screen_peek_after_minutes", "unanswered_screen_peek_cooldown_minutes"],
  enable_creative_writing: ["creative_inspiration_probability", "creative_share_probability", "creative_chars_per_session", "creative_max_active_projects"],
  creative_hidden_mode: ["creative_share_probability"],
};

const featureSettingSections = {
  enable_private_image_self_recognition: [
    {
      title: "防抖收口",
      note: "用户只发图时先等一小段时间，看是否继续补充文字说明。",
      keys: ["enable_semantic_message_debounce", "inbound_message_debounce_seconds", "semantic_message_debounce_seconds"],
    },
    {
      title: "视觉等待",
      note: "收口结束后等待图片转述结果；视觉提前完成会直接进入主链。",
      keys: ["private_image_vision_wait_seconds"],
    },
    {
      title: "重复图片缓存",
      note: "复用相同图片的视觉摘要，避免表情包反复触发识图模型。",
      keys: ["enable_private_image_vision_cache", "private_image_vision_cache_max_items"],
    },
    {
      title: "角色自我识别",
      note: "把当前角色名字、人设和自定义线索交给视觉模型，辅助判断图里是不是当前角色自己。",
      keys: ["private_image_self_recognition_hint"],
    },
  ],
  enable_segmented_proactive_reply: [
    {
      title: "切分规则",
      note: "决定主动消息什么时候拆、按什么拆，以及短片段是否并回去。",
      keys: ["segmented_proactive_scope", "segmented_proactive_threshold", "segmented_proactive_min_segment_chars", "segmented_proactive_max_segments", "segmented_proactive_split_mode", "segmented_proactive_regex", "segmented_proactive_split_words"],
    },
    {
      title: "内容清理",
      note: "用于去掉句尾分隔符、空格或换行；括号和双引号内的内容会被保护。",
      keys: ["enable_segmented_proactive_content_cleanup", "segmented_proactive_content_cleanup_rule", "segmented_proactive_content_cleanup_words"],
    },
    {
      title: "发送间隔",
      note: "控制分段之间等多久，避免像刷屏，也避免间隔太死板。",
      keys: ["segmented_proactive_interval_method", "segmented_proactive_interval_min", "segmented_proactive_interval_max", "segmented_proactive_log_base"],
    },
  ],
  enable_group_wakeup_enhancement: [
    {
      title: "唤醒词",
      note: "决定哪些群消息可能把 Bot 拉进回复链。",
      keys: ["group_wakeup_direct_words", "group_wakeup_context_words"],
    },
    {
      title: "兴趣唤醒",
      note: "让 Bot 碰到自己感兴趣的话题时低概率接话。",
      keys: ["group_wakeup_interest_keywords", "group_wakeup_interest_probability", "group_wakeup_topic_interest_max_boost", "group_wakeup_generated_keyword_limit"],
    },
    {
      title: "节流与拟人感",
      note: "控制冷却、收口等待和被频繁叫到后的疲劳感。",
      keys: ["group_wakeup_cooldown_seconds", "group_wakeup_debounce_pending_penalty", "group_wakeup_fatigue_limit", "group_wakeup_fatigue_decay_minutes"],
    },
    {
      title: "高强度收口",
      note: "连续被叫到时，合并同群后续唤醒消息，减少多次 LLM 调用和后台成本。",
      keys: ["enable_group_high_intensity_mode", "group_high_intensity_wakeup_window_seconds", "group_high_intensity_wakeup_threshold", "group_high_intensity_cooldown_seconds", "group_high_intensity_merge_seconds"],
    },
    {
      title: "记录与上下文",
      note: "控制页面记录量和场景判断参考消息数。",
      keys: ["group_wakeup_log_limit", "group_scene_recent_limit"],
    },
  ],
  enable_photo_text_action: [
    {
      title: "后端选择",
      note: "本地 ComfyUI 和在线图片 API 的优先关系。",
      keys: ["photo_generation_backend", "photo_action_max_daily"],
    },
    {
      title: "本地 ComfyUI",
      note: "用于主动图片生成的工作流和等待时间。",
      keys: ["COMFYUI_TEXT2IMG_WORKFLOW_NAME", "COMFYUI_SELFIE_WORKFLOW_NAME", "comfyui_photo_wait_seconds"],
    },
    {
      title: "电脑负载保护",
      note: "电脑忙时抑制或延后本地生图，避免影响正在使用的机器。",
      keys: ["enable_local_photo_load_guard", "local_photo_cpu_busy_percent", "local_photo_memory_busy_percent", "local_photo_defer_minutes"],
    },
    {
      title: "在线图片 API",
      note: "作为 external 后端，或 auto 模式下本地忙时的备选后端。",
      keys: ["EXTERNAL_IMAGE_API_BASE_URL", "EXTERNAL_IMAGE_API_MODEL", "external_image_api_size", "external_image_api_timeout_seconds"],
    },
    {
      title: "画面风格",
      note: "只影响提示词组织，不改变后端配置。",
      keys: ["photo_generation_style", "photo_generation_style_custom_prompt"],
    },
  ],
};

const featureSettingTypes = {
  forward_message_mode: { type: "select", options: [["inject", "注入"], ["transcribe", "转述"]] },
  photo_generation_backend: { type: "select", options: [["auto", "auto"], ["comfyui", "ComfyUI"], ["external", "在线图片 API"]] },
  photo_generation_style: { type: "select", options: [["真实", "真实"], ["二次元", "二次元"], ["其他", "其他"]] },
  segmented_proactive_scope: { type: "select", options: [["proactive_only", "仅插件主动"], ["all_llm", "全部 LLM 纯文本回复"]] },
  segmented_proactive_split_mode: { type: "select", options: [["regex", "正则"], ["words", "分段词列表"]] },
  segmented_proactive_interval_method: { type: "select", options: [["log", "按字数对数"], ["random", "随机"]] },
  atrelay_default_relay_style: { type: "select", options: [["persona", "语气转译"], ["soft", "委婉转述"], ["original", "原话模式"]] },
  worldbook_config_paths: { type: "textarea" },
  private_user_aliases: { type: "textarea" },
  skill_growth_custom_skills: { type: "textarea" },
  news_sources: { type: "textarea" },
  news_hot_sources: { type: "textarea" },
  web_exploration_interests: { type: "textarea" },
  group_wakeup_direct_words: { type: "textarea" },
  group_wakeup_context_words: { type: "textarea" },
  group_wakeup_interest_keywords: { type: "textarea" },
  roleplay_user_profile_prompt: { type: "textarea" },
  private_image_self_recognition_hint: { type: "textarea" },
  photo_generation_style_custom_prompt: { type: "textarea" },
  segmented_proactive_regex: { type: "textarea" },
  segmented_proactive_split_words: { type: "textarea" },
  segmented_proactive_content_cleanup_rule: { type: "textarea" },
  segmented_proactive_content_cleanup_words: { type: "textarea" },
  private_reading_default_keywords: { type: "textarea" },
  private_reading_blocked_tags: { type: "textarea" },
  group_repeat_interrupt_text: { type: "text" },
  group_repeat_interrupt_image_path: { type: "text" },
};

const probabilitySettingKeys = new Set([
  "bilibili_share_probability",
  "news_share_probability",
  "external_event_self_link_probability",
  "web_exploration_share_probability",
  "qzone_life_publish_probability",
  "private_reading_share_probability",
  "private_reading_ask_probability",
  "creative_inspiration_probability",
  "creative_share_probability",
  "skill_growth_schedule_influence_strength",
]);

const percentSettingKeys = new Set([
  "group_repeat_follow_probability",
  "group_repeat_interrupt_probability",
  "group_repeat_interrupt_probability_step",
  "group_wakeup_interest_probability",
  "group_wakeup_topic_interest_max_boost",
  "group_wakeup_debounce_pending_penalty",
  "local_photo_cpu_busy_percent",
  "local_photo_memory_busy_percent",
]);

const presetCatalog = {
  safe: {
    label: "保守低打扰",
    desc: "低主动频率。",
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
  creative_writing: "文本创作",
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
  const daily = overview.daily_state || {};
  const budget = state.tokenStats?.budget || {};
  const dailyUsed = Number(budget.used || 0);
  const dailyLimit = Number(budget.limit || 0);
  const featureKeys = Object.keys(overview.features || {}).filter(visibleConfigKey);
  const enabledFeatures = featureKeys.filter((key) => overview.features?.[key]).length;
  const energy = Number(daily.energy || 0);
  const mood = daily.mood_bias || daily.note || "暂无状态";
  $("#stats").innerHTML = [
    statCard(`私聊 ${privateInfo.enabled_user_count || 0} · 群聊 ${groupInfo.enabled_group_count || 0}`, `总数：对象 ${privateInfo.user_count || 0} · 群聊 ${groupInfo.group_count || 0}`),
    statCard(dailyLimit > 0 ? `${formatCompactNumber(dailyUsed)} / ${formatCompactNumber(dailyLimit)}` : `${formatCompactNumber(dailyUsed)} / 不限`, "今日 Token 消耗 / 上限"),
    statCard(energy ? `${energy}/100` : "-", `心理能量 · ${mood}`),
    statCard(`${enabledFeatures}/${featureKeys.length}`, "开启功能数 / 功能总数"),
  ].join("");
}

function statCard(value, label) {
  return `<article class="stat"><b>${escapeHtml(value)}</b><span>${escapeHtml(label)}</span></article>`;
}

function renderDashboard() {
  renderDashboardPulse();
  renderHealthPanel();
  renderDiagnostics();
  renderUxReviewPanel();
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
  const news = overview.news || {};
  const exploration = overview.web_exploration || {};
  const creative = overview.creative || {};
  const bookshelf = state.bookshelfUnlocked || overview.bookshelf || {};
  const nextUser = state.users
    .filter((item) => Number(item.next_proactive_ts || 0) > 0)
    .sort((a, b) => Number(a.next_proactive_ts || 0) - Number(b.next_proactive_ts || 0))[0];
  const newsTitle = news.last_digest?.headline || news.last_digest?.topic || "";
  const explorationTitle = exploration.last_digest?.topic || exploration.last_query?.query || "";
  const bookshelfNote = [
    creative.latest_title || "",
    bookshelf.secret_count ? `夹层 ${bookshelf.secret_count}` : "",
  ].filter(Boolean).join(" · ");
  const cards = [
    {
      tone: "life",
      label: "此刻状态",
      value: current.activity || "暂无当前日程",
      note: [current.time, current.mood, current.message_seed].filter(Boolean).join(" · ") || daily.note || "暂无细化",
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
      tone: "news",
      label: "今日见闻",
      value: newsTitle || explorationTitle || "暂无记录",
      note: newsTitle && explorationTitle ? `搜索：${explorationTitle}` : (news.last_read_at || exploration.last_explore_at || "新闻阅读和主动搜索会在这里留下痕迹"),
      jump: "bookshelf",
    },
    {
      tone: "bookcase",
      label: "书柜与长线",
      value: creative.latest_title || "暂无新书",
      note: bookshelfNote || `${creative.active_projects || 0} 个创作进行中`,
      jump: "bookshelf",
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
    ["group", "群聊观测", `${overview.group?.enabled_group_count || 0}/${overview.group?.group_count || 0} 个群`],
    ["worldbook", "关系网", `${overview.worldbook?.enabled_member_count || 0}/${overview.worldbook?.member_count || 0} 个节点`],
    ["tokens", "Token", `${formatCompactNumber(state.tokenStats?.totals?.total_tokens || 0)} · ${formatCompactNumber(state.tokenStats?.totals?.calls || 0)} 次`],
    ["modules", "模块配置", moduleShortcutNote(overview)],
    ["models", "模型分流", providerShortcutNote(overview.providers || {})],
    ["config", "名单与开关", `${overview.group?.access_mode || "whitelist"} · 白 ${overview.group?.whitelist?.length || 0} / 黑 ${overview.group?.blacklist?.length || 0}`],
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
    search_failed: "搜索失败",
    digest_failed: "整理失败",
    web_search_disabled_or_unconfigured: "搜索未配置",
    waiting_schedule: "等待定时",
    all_sources_done: "今日来源已处理",
    waiting_window: "等待窗口",
    checking: "正在检查",
    waiting_today_video: "等待今日视频",
    today_video_without_text: "今日视频暂无文字版",
    already_read_today_video: "今日已读",
    missed_today_ai_daily: "今日窗口已过",
  };
  return labels[text] || text || "暂无";
}

function renderNewsInsightPanel() {
  const news = state.overview?.news || {};
  const digest = news.last_digest || {};
  const items = Array.isArray(news.latest_items) ? news.latest_items : [];
  const enabled = Boolean(news.enabled);
  const dailyHot = Boolean(news.daily_hot_enabled);
  const aiDaily = news.ai_daily || {};
  const aiDailyTextStatus = news.ai_daily_enabled
    ? (aiDaily.last_text_readable
      ? `文字版 ${formatCompactNumber(aiDaily.last_text_chars || 0)}字`
      : (aiDaily.last_video_subtitle_readable
        ? `字幕 ${formatCompactNumber(aiDaily.last_video_subtitle_chars || 0)}字`
        : (aiDaily.last_video_link
          ? (aiDaily.last_video_context_chars
            ? `视频信息 ${formatCompactNumber(aiDaily.last_video_context_chars || 0)}字`
            : (aiDaily.last_video_subtitle_status === "missing" ? "字幕暂无，按视频公开信息" : "视频正文暂无"))
          : (aiDaily.last_text_link ? "文字版未读到正文" : "文字版暂无"))))
    : "";
  const aiDailyBasisStatus = news.ai_daily_enabled && aiDaily.last_read_basis
    ? `依据：${aiDaily.last_read_basis}`
    : "";
  const headline = digest.headline || digest.topic || "暂无新闻见闻";
  const impression = digest.impression || (enabled ? "暂无整理结果。" : "新闻阅读未开启");
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
      <span>${news.ai_daily_enabled ? `AI日报/早报：${escapeHtml(insightStatus(aiDaily.status))}` : "AI日报/早报关闭"}</span>
      ${aiDailyTextStatus ? `<span>${escapeHtml(aiDailyTextStatus)}</span>` : ""}
      ${aiDailyBasisStatus ? `<span>${escapeHtml(aiDailyBasisStatus)}</span>` : ""}
      <span>${news.boredom_read_enabled ? "空档阅读开启" : "空档阅读关闭"}</span>
    </div>
    <ul class="insight-list">${itemHtml}</ul>
  `;
}

function renderWebExplorationPanel() {
  const exploration = state.overview?.web_exploration || {};
  const digest = exploration.last_digest || {};
  const query = exploration.last_query || {};
  const history = Array.isArray(exploration.history) ? exploration.history : [];
  const enabled = Boolean(exploration.enabled);
  const recentWebHistory = history.slice().reverse().find((item) => item && item.source !== "news") || {};
  const displayTitle = digest.topic || recentWebHistory.title || query.query || "暂无主动搜索记录";
  const displayNote = digest.note || recentWebHistory.intro || recentWebHistory.content || (enabled ? "等待下一次主动搜索留下笔记。" : "主动搜索未开启");
  const displayTime = exploration.last_explore_at || recentWebHistory.generated_at || recentWebHistory.date || "未搜索";
  const historyHtml = history.length
    ? history.slice().reverse().map((item) => {
      const sourceLabel = item.source_label || (item.source === "news" ? "新闻阅读" : "主动搜索");
      const queryText = item.query ? `搜索：${item.query}` : "";
      const sourceText = item.source_title ? `来源：${item.source_title}` : "";
      return `
        <li class="browsing-history-item ${escapeHtml(item.source || "web_exploration")}">
          <div>
            <span class="history-badge">${escapeHtml(sourceLabel)}</span>
            <small>${escapeHtml(item.generated_at || item.date || "")}</small>
          </div>
          <b>${escapeHtml(item.title || item.query || "浏览记录")}</b>
          <p>${escapeHtml(item.intro || item.content || "这次没有留下详细记录。")}</p>
          ${queryText || sourceText ? `<footer>${escapeHtml([queryText, sourceText].filter(Boolean).join(" · "))}</footer>` : ""}
        </li>
      `;
    }).join("")
    : `<li class="empty-line browsing-history-empty">暂无浏览记录</li>`;
  $("#webExplorationPanel").innerHTML = `
    <div class="insight-head">
      <div>
        <span class="eyebrow">${enabled ? "主动搜索" : "未开启"}</span>
        <b>${escapeHtml(displayTitle)}</b>
      </div>
      <small>${escapeHtml(displayTime)}</small>
    </div>
    <p>${escapeHtml(displayNote)}</p>
    <div class="insight-meta">
      <span>${escapeHtml(insightStatus(exploration.last_status))}</span>
      <span>${exploration.available ? "网页搜索可用" : "网页搜索未配置"}</span>
      <span>${exploration.boredom_search_enabled ? "空档搜索开启" : "空档搜索关闭"}</span>
      <span>历史 ${escapeHtml(exploration.history_count ?? history.length)} 条</span>
    </div>
    <ul class="browsing-history-list">${historyHtml}</ul>
  `;
}

function moduleShortcutNote(overview) {
  const settings = overview?.settings || {};
  const features = overview?.features || {};
  const items = [
    ["私聊主动", Number(settings.max_daily_messages || 0) > 0],
    ["状态日程", Boolean(features.enable_humanized_states || settings.enable_humanized_states)],
    ["群聊观察", Boolean(features.enable_group_companion || settings.enable_group_companion)],
    ["关系网", Boolean(features.enable_worldbook_member_recognition || settings.enable_worldbook_member_recognition)],
    ["记忆学习", Boolean(features.enable_companion_memory || settings.enable_companion_memory)],
    ["长期创作", Boolean(features.enable_creative_writing || settings.enable_creative_writing)],
    ["新闻阅读", Boolean(features.enable_news_integration || settings.enable_news_integration)],
    ["主动搜索", Boolean(features.enable_web_exploration || settings.enable_web_exploration)],
    ["QQ 空间", Boolean(features.enable_qzone_integration || settings.enable_qzone_integration)],
  ];
  if (overview?.private_reading?.available) {
    items.push(["夹层阅读", Boolean(features.enable_private_reading_integration || settings.enable_private_reading_integration)]);
  }
  const enabledItems = items.filter(([, enabled]) => enabled);
  const preview = enabledItems.slice(0, 3).map(([label]) => label).join(" / ");
  const external = overview?.external_abilities?.enabled_count || 0;
  const suffix = external ? ` · 外部 ${external}` : "";
  return `${enabledItems.length}/${items.length} 个主要模块开启${preview ? ` · ${preview}` : ""}${suffix}`;
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
  const cache = overview.cache || {};
  const imageCache = cache.private_image_vision || {};
  const imagePrivateMetric = imageCache.private || {};
  const imageForwardMetric = imageCache.forward || {};
  const imageHits = Number(imagePrivateMetric.hits || 0) + Number(imageForwardMetric.hits || 0);
  const imageMisses = Number(imagePrivateMetric.misses || 0) + Number(imageForwardMetric.misses || 0);
  const imageTotal = imageHits + imageMisses;
  const imageHitRate = imageTotal ? Math.round((imageHits / imageTotal) * 100) : 0;
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
      level: imageCache.enabled ? (imageTotal ? "ok" : "info") : "info",
      title: "缓存命中",
      text: imageCache.enabled
        ? `图片视觉 ${imageCache.items || 0}/${imageCache.max_items || "不限"} 条 · 命中率 ${imageTotal ? `${imageHitRate}%` : "暂无样本"}`
        : "图片视觉缓存未开启",
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

function renderUxReviewPanel() {
  const overview = state.overview || {};
  const settings = overview.settings || {};
  const features = overview.features || {};
  const group = overview.group || {};
  const news = overview.news || {};
  const aiDaily = news.ai_daily || {};
  const cache = overview.cache || {};
  const imageCache = cache.private_image_vision || {};
  const featureKeys = Object.keys(features).filter((key) => key.startsWith("enable_"));
  const enabledFeatureCount = featureKeys.filter((key) => features[key]).length;
  const targetUsers = Array.isArray(settings.target_user_ids)
    ? settings.target_user_ids.filter(Boolean)
    : String(settings.target_user_ids || "").split(/[\s,，]+/).filter(Boolean);
  const hasPrivateTargets = targetUsers.length || state.users.some((user) => user.is_qq_user || user.user_id);
  const personaText = String(settings.schedule_persona_prompt || "");
  const roleFilled = ["姓名", "性别", "生日", "识别点", "职业/身份", "性格描述", "核心欲望/目标", "爱好"]
    .filter((label) => labeledRoleplayValuePresent(personaText, label)).length;
  const personaReady = roleFilled >= 6 || personaText.trim().length >= 220;
  const worldReady = String(settings.schedule_worldview_prompt || "").trim().length >= 40;
  const userProfileText = String(settings.roleplay_user_profile_prompt || "").trim()
    || String(settings.private_image_self_recognition_hint || "").trim();
  const userReady = userProfileText.length >= 30;
  const imageEnhanceEnabled = Boolean(settings.enable_private_image_self_recognition || features.enable_private_image_self_recognition);
  const items = [
    {
      level: personaReady && worldReady && userReady ? "ok" : "warn",
      title: "角色设定仍是最大收益点",
      text: personaReady && worldReady && userReady
        ? (roleFilled >= 6 ? `角色 ${roleFilled}/8 项、世界观和用户关系都有内容` : "旧版文案较完整；标准化字段可按需补齐")
        : `角色 ${roleFilled}/8 项；建议补齐外貌识别点、爱好、禁忌和用户关系`,
      tab: "roleplay",
    },
    {
      level: Number(settings.max_daily_messages || 0) <= 0 || hasPrivateTargets ? "ok" : "warn",
      title: "私聊主动目标",
      text: Number(settings.max_daily_messages || 0) <= 0
        ? "私聊主动关闭，不需要目标列表"
        : (hasPrivateTargets ? `已识别 ${targetUsers.length || state.users.length} 个私聊对象` : "主动开启但目标列表为空"),
      tab: "modules",
    },
    {
      level: features.enable_group_companion ? (Number(group.enabled_group_count || 0) > 0 ? "ok" : "warn") : "info",
      title: "群聊入口",
      text: features.enable_group_companion
        ? `${group.enabled_group_count || 0}/${group.group_count || 0} 个群正在观测`
        : "群聊观察关闭，群聊相关页只保留管理视图",
      tab: "group",
    },
    {
      level: imageEnhanceEnabled
        ? (settings.enable_private_image_vision_cache ? "ok" : "warn")
        : "info",
      title: "图片转述增强",
      text: imageEnhanceEnabled
        ? `缓存 ${imageCache.items || 0}/${imageCache.max_items || "不限"} 条；${settings.enable_private_image_vision_cache ? "重复图会复用视觉摘要" : "缓存关闭，重复表情包会重复调用"}`
        : "图片转述增强关闭",
      tab: "modules",
    },
    {
      level: featureKeys.length && enabledFeatureCount > Math.ceil(featureKeys.length * 0.78) ? "warn" : "ok",
      title: "功能开关密度",
      text: featureKeys.length
        ? `${enabledFeatureCount}/${featureKeys.length} 个功能开启；开启太满时更需要看关联参数`
        : "等待功能开关数据",
      tab: "config",
    },
    {
      level: news.ai_daily_enabled
        ? (aiDaily.last_text_readable || aiDaily.status === "already_read_today_video" ? "ok" : "warn")
        : "info",
      title: "AI 日报/早报可解释性",
      text: news.ai_daily_enabled
        ? (aiDaily.last_text_readable ? `文字版已读 ${formatCompactNumber(aiDaily.last_text_chars || 0)} 字` : `状态：${insightStatus(aiDaily.status)}`)
        : "AI 日报/早报追踪关闭",
      tab: "dashboard",
    },
  ];
  $("#uxReviewPanel").innerHTML = items.map((item) => `
    <button type="button" class="ux-review-item ${escapeHtml(item.level)}" data-jump-tab="${escapeHtml(item.tab)}">
      <span>${escapeHtml(item.level === "ok" ? "已处理" : item.level === "warn" ? "需关注" : "信息")}</span>
      <b>${escapeHtml(item.title)}</b>
      <small>${escapeHtml(item.text)}</small>
    </button>
  `).join("");
}

function labeledRoleplayValuePresent(text, label) {
  const source = String(text || "");
  const escaped = escapeRegExp(label);
  const pattern = new RegExp(`(?:^|\\n)\\s*${escaped}\\s*[：:]\\s*([^\\n]+)`, "u");
  const match = source.match(pattern);
  return Boolean(match && String(match[1] || "").trim());
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
  const enabledCount = groups.filter((group) => group.enabled).length;
  const totalMessages = groups.reduce((sum, group) => sum + Number(group.message_count || 0), 0);
  const totalTopics = groups.reduce((sum, group) => sum + Number(group.topic_count || 0), 0);
  const maxMessages = Math.max(1, ...groups.map((group) => Number(group.message_count || 0)));
  $("#groupBubbleChart").innerHTML = `
    <div class="group-observe-summary">
      <section><span>观测中</span><b>${escapeHtml(enabledCount)} / ${escapeHtml(groups.length)}</b></section>
      <section><span>累计消息</span><b>${escapeHtml(totalMessages)}</b></section>
      <section><span>话题线</span><b>${escapeHtml(totalTopics)}</b></section>
    </div>
    <div class="group-observe-list">
      ${groups.map((group) => renderGroupObserveRow(group, maxMessages)).join("")}
    </div>
  `;
  document.querySelectorAll("[data-observe-group]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedGroupId = button.dataset.observeGroup;
      switchTab("group");
      renderGroups();
      renderGroupDetail(true);
    });
  });
}

function renderGroupObserveRow(group, maxMessages) {
  const messageCount = Number(group.message_count || 0);
  const pct = Math.max(4, Math.round((messageCount / Math.max(1, maxMessages)) * 100));
  const name = group.name || group.group_name || group.title || group.group_id || "未命名群";
  const metrics = [
    `${messageCount} 消息`,
    `${Number(group.episode_count || 0)} 片段`,
    `${Number(group.topic_count || 0)} 话题`,
    `${Number(group.slang_count || 0)} 黑话`,
  ];
  return `
    <button type="button" class="group-observe-row ${group.enabled ? "" : "off"}" data-observe-group="${escapeHtml(group.group_id)}">
      <div class="group-observe-main">
        <span class="group-observe-state">${group.enabled ? "开启" : "停用"}</span>
        <b>${escapeHtml(name)}</b>
        <small>${escapeHtml(group.group_id || "")}</small>
      </div>
      <div class="group-observe-meter">
        <i style="width:${pct}%"></i>
      </div>
      <div class="group-observe-meta">
        ${metrics.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}
      </div>
      <small class="group-observe-time">${escapeHtml(group.last_seen || "暂无活跃")}</small>
    </button>
  `;
}

function groupTopicThreadsView(threads) {
  const items = Array.isArray(threads) ? threads : [];
  if (!items.length) {
    return `<div class="empty small">暂无话题线</div>`;
  }
  return `
    <div class="group-topic-list">
      ${items.map((item) => {
        const examples = Array.isArray(item.recent_examples) ? item.recent_examples : [];
        const participants = Array.isArray(item.participants) ? item.participants : [];
        const heat = Math.max(0, Math.min(100, Number(item.heat || 0)));
        return `
          <article class="group-topic-card ${item.status === "活跃" ? "active" : ""}">
            <div class="group-topic-rail">
              <span>${escapeHtml(item.rank || "")}</span>
              <i style="height:${escapeHtml(Math.max(14, heat))}%"></i>
            </div>
            <div class="group-topic-main">
              <header>
                <div>
                  <span class="group-topic-status">${escapeHtml(item.status || "话题")}</span>
                  <h3>${escapeHtml(item.title || "未命名话题")}</h3>
                </div>
                <dl>
                  <div><dt>消息</dt><dd>${escapeHtml(item.message_count || 0)}</dd></div>
                  <div><dt>参与</dt><dd>${escapeHtml(item.participant_count || participants.length || 0)}</dd></div>
                  <div><dt>持续</dt><dd>${escapeHtml(item.duration || "-")}</dd></div>
                </dl>
              </header>
              ${item.summary ? `<p class="group-topic-summary">${escapeHtml(item.summary)}</p>` : ""}
              <div class="group-topic-meta">
                <span>最近 ${escapeHtml(item.last_seen || "-")}</span>
                <span>开始 ${escapeHtml(item.started || "-")}</span>
                ${item.bot_joined ? `<span>Bot 参与过</span>` : ""}
              </div>
              ${participants.length ? `
                <div class="group-topic-people">
                  ${participants.slice(0, 6).map((person) => `<span title="${escapeHtml(person.id || "")}">${escapeHtml(person.name || person.id || "-")}</span>`).join("")}
                  ${participants.length > 6 ? `<span>+${escapeHtml(participants.length - 6)}</span>` : ""}
                </div>
              ` : ""}
              ${examples.length ? `
                <div class="group-topic-examples">
                  ${examples.map((example) => `
                    <p><b>${escapeHtml(example.name || "群友")}</b><span>${escapeHtml(example.text || "")}</span><small>${escapeHtml(example.time || "")}</small></p>
                  `).join("")}
                </div>
              ` : ""}
            </div>
          </article>
        `;
      }).join("")}
    </div>
  `;
}

function renderFeatureMatrix() {
  const groups = [
    ["陪伴", ["enable_mai_style_integration", "enable_expression_learning", "enable_response_self_review", "enable_dialogue_episode_memory"]],
    ["群聊", ["enable_group_companion", "enable_group_context_injection", "enable_group_slang_learning", "enable_group_topic_threads", "enable_group_relationship_graph"]],
    ["记忆", ["enable_companion_memory", "enable_open_loop_tracking", "enable_livingmemory_integration"]],
    ["主动联动", ["enable_proactive_quote_trigger_message", "enable_unanswered_screen_peek_followup", "enable_bilibili_integration", "enable_bilibili_boredom_watch", "enable_news_integration", "enable_ai_daily_watch", "enable_private_reading_integration", "enable_private_reading_boredom_read", "enable_private_reading_ask_recommendation", "enable_creative_writing", "creative_hidden_mode"]],
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
  const scope = tokenScopeData(stats);
  const totals = scope.totals || {};
  const totalTokens = Number(totals.total_tokens || 0);
  const calls = Number(totals.calls || 0);
  const errors = Number(totals.errors || 0);
  const estimatedRatio = Number(totals.estimated_ratio || 0);
  const budget = stats.budget || {};
  const dailyLimit = Number(budget.limit || 0);
  const softLimit = Number(budget.soft_limit || 0);
  const softRemaining = budget.soft_remaining == null ? null : Number(budget.soft_remaining || 0);
  const exemptUsed = Number(budget.exempt_used || 0);
  const dailyRemaining = budget.remaining == null ? null : Number(budget.remaining || 0);
  renderTokenToolbar(stats);
  const showHourlyTrend = state.tokenView === "total";
  const hourlyPanel = $("#tokenHourlyPanel");
  if (hourlyPanel) hourlyPanel.hidden = !showHourlyTrend;
  const budgetCards = scope.isToday ? [
    tokenBudgetStat({
      limit: dailyLimit > 0 ? formatCompactNumber(dailyLimit) : "不限",
      remaining: dailyRemaining == null ? "不限" : formatCompactNumber(dailyRemaining),
      softLabel: budget.soft_active ? "软限额已接管" : "每日软限额",
      softValue: budget.soft_enabled && softLimit > 0
        ? (budget.soft_active ? `已暂缓 ${formatNumber(budget.deferred_calls || 0)} 次` : `剩 ${formatCompactNumber(softRemaining)}`)
        : "关闭",
    }),
    miniStat("主动消息", formatCompactNumber(exemptUsed)),
  ] : [];
  $("#tokenSummary").innerHTML = [
    miniStat(scope.label, formatNumber(totalTokens)),
    ...budgetCards,
    miniStat("调用次数", formatNumber(calls)),
    miniStat("平均 Token", formatNumber(Math.round(Number(totals.avg_tokens || 0)))),
    miniStat("平均延迟", `${formatNumber(Math.round(Number(totals.avg_latency_ms || 0)))} ms`),
    miniStat("估算占比", `${Math.round(estimatedRatio * 100)}%`),
    miniStat("失败次数", formatNumber(errors)),
  ].join("");

  renderTokenChart("#tokenProviderChart", scope.providers || [], "暂无 Provider 消耗数据", (item) => item.key || "default");
  renderTokenChart("#tokenTaskChart", scope.tasks || [], "暂无任务消耗数据", (item) => tokenTaskLabel(item.key));
  if (showHourlyTrend) {
    renderTokenHourlyChart(scope.hours || []);
  } else {
    $("#tokenHourlyChart").innerHTML = "";
  }
  renderTokenDailyChart(stats.by_day || []);
  renderTokenDailyTable(stats.by_day_detail || stats.by_day || []);
  renderTokenProviderTable(scope.providers || []);
  renderTokenTaskTable(scope.tasks || []);
  renderTokenRecentTable(scope.recent || []);
}

function tokenScopeData(stats) {
  const view = state.tokenView || "today";
  const today = stats.budget?.day || todayKeyLocal();
  const dayRows = stats.by_day_detail || stats.by_day || [];
  const availableDates = dayRows.map((item) => String(item.key || "")).filter(Boolean);
  if (!state.tokenDate || !availableDates.includes(state.tokenDate)) {
    state.tokenDate = availableDates.includes(today) ? today : (availableDates[availableDates.length - 1] || today);
  }
  if (view === "total") {
    return {
      mode: "total",
      label: "累计 Token",
      totals: stats.totals || {},
      providers: stats.by_provider || [],
      tasks: stats.by_task || [],
      hours: stats.by_hour || [],
      recent: stats.recent || [],
      isToday: false,
    };
  }
  const selectedDay = view === "date" ? state.tokenDate : today;
  const day = dayRows.find((item) => String(item.key || "") === selectedDay) || { key: selectedDay };
  const recent = (stats.recent || []).filter((item) => recentItemDayKey(item) === selectedDay);
  const hours = (stats.by_hour || []).filter((item) => String(item.key || "").startsWith(`${selectedDay}T`));
  return {
    mode: view,
    label: selectedDay === today ? "今日 Token" : `${selectedDay} Token`,
    totals: day,
    providers: day.providers || [],
    tasks: day.tasks || [],
    hours,
    recent,
    isToday: selectedDay === today,
  };
}

function renderTokenToolbar(stats) {
  const dayRows = stats.by_day_detail || stats.by_day || [];
  const dates = dayRows.map((item) => String(item.key || "")).filter(Boolean);
  const fallbackDate = todayKeyLocal();
  const select = $("#tokenDateSelect");
  if (select) {
    select.innerHTML = dates.length
      ? dates.slice().reverse().map((date) => `<option value="${escapeHtml(date)}" ${date === state.tokenDate ? "selected" : ""}>${escapeHtml(date)}</option>`).join("")
      : `<option value="${escapeHtml(fallbackDate)}">${escapeHtml(fallbackDate)}</option>`;
    select.disabled = state.tokenView !== "date";
  }
  document.querySelectorAll("[data-token-view]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.tokenView === state.tokenView);
  });
}

function todayKeyLocal() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function recentItemDayKey(item) {
  const ts = Number(item?.ts || 0);
  if (ts > 0) {
    const date = new Date(ts * 1000);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }
  return String(item?.time || "").slice(0, 10);
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
        <td class="user-cell identity"><strong title="${escapeHtml(user.display_name || user.nickname || user.user_id)}">${escapeHtml(user.display_name || user.nickname || user.user_id)}</strong>${user.is_qq_user ? "" : ` <span class="badge off">非 QQ</span>`}${Array.isArray(user.alias_user_ids) && user.alias_user_ids.length ? ` <span class="badge ok" title="${escapeHtml(user.alias_user_ids.join("\\n"))}">已合并 ${escapeHtml(user.alias_user_ids.length)} 个身份</span>` : ""}<br><span class="user-id-line"><span class="muted mono" title="${escapeHtml(user.user_id)}">${escapeHtml(user.user_id)}</span><button type="button" class="copy-id-btn" data-copy-user-id="${escapeHtml(user.user_id)}">复制</button></span></td>
        <td class="user-cell relation"><span class="badge ${user.enabled ? "" : "off"}">${escapeHtml(user.enabled ? "启用" : "停用")}</span> <span class="muted">${escapeHtml(user.relationship_stage || "未分层")}</span><br><span>分数 ${escapeHtml(user.relationship_score)}</span></td>
        <td class="user-cell compact">入站 ${escapeHtml(user.inbound_count)} · 回复 ${escapeHtml(user.reply_count)}<br><span class="muted">记忆 ${escapeHtml(user.memory_items)} 条</span></td>
        <td class="user-cell proactive"><span>今日 ${escapeHtml(user.sent_today)} · 总计 ${escapeHtml(user.proactive_sent_count)}</span><br><span class="muted truncate" title="${escapeHtml(user.next_proactive || "")}">${escapeHtml(user.next_proactive)}</span></td>
        <td class="user-cell recent">${escapeHtml(user.last_seen)}<br><span class="muted">上次主动 ${escapeHtml(user.last_sent)}</span></td>
        <td class="user-cell action"><button type="button" class="table-action ${user.enabled ? "danger-outline" : ""}" data-user-toggle="${escapeHtml(user.user_id)}">${escapeHtml(user.enabled ? "停用" : "启用")}</button></td>
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
  document.querySelectorAll("[data-copy-user-id]").forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.stopPropagation();
      await copyTextToClipboard(button.dataset.copyUserId || "", "已复制用户 ID");
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
      ${miniStat("习惯", detail.habit_count || detail.behavior_habits?.items?.length || 0)}
    </div>
    <div class="detail-grid">
      ${detailBlock("关系和主动", detail.formatted?.relationship || "", [["下次主动", detail.formatted?.next_proactive || detail.next_proactive], ["动作偏好", detail.formatted?.action_affinity || ""]])}
      ${detailBlock("行为习惯", detail.behavior_habits?.updated_at ? `更新于 ${detail.behavior_habits.updated_at}` : "", userHabitPairs(detail.behavior_habits))}
      ${detailBlock("最近对话", "", [["用户消息", detail.last_user_message || ""], ["陪伴回复", detail.last_companion_message || ""]])}
      ${detailBlock("对话片段", "", (detail.dialogue_episodes || []).map((item, index) => [`#${index + 1}`, item.summary || item.title || JSON.stringify(item)]))}
      ${detailBlock("未完话头", "", (detail.open_loops || []).map((item, index) => [`#${index + 1}`, item.text || item.topic || JSON.stringify(item)]))}
    </div>
  `;
  bindUserActions(detail);
}

function userHabitPairs(habits) {
  const items = Array.isArray(habits?.items) ? habits.items : [];
  return items.length
    ? items.map((item) => [
      `${item.bucket || "-"} ${item.avg_time || ""}`,
      `${item.category || "习惯"}｜${item.topic || "-"}｜${item.count || 0} 次${item.last_seen ? `｜最近 ${item.last_seen}` : ""}${item.last_seen_text ? `｜${item.last_seen_text}` : ""}`,
    ])
    : [["-", habits?.enabled ? "暂无达到阈值的习惯样本" : "习惯学习未开启"]];
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
  const rows = state.groups.filter((group) => {
    const haystack = [
      group.group_id,
      group.name,
      group.group_name,
      group.atmosphere?.mood,
      group.atmosphere?.last_summary,
    ].join(" ").toLowerCase();
    return !keyword || haystack.includes(keyword);
  });
  if (!rows.length) {
    state.selectedGroupId = "";
  } else if (!rows.some((group) => String(group.group_id) === String(state.selectedGroupId))) {
    state.selectedGroupId = rows[0].group_id;
  }
  const count = $("#groupListCount");
  if (count) {
    count.textContent = `${rows.length}/${state.groups.length} 个群`;
  }
  $("#groupRows").innerHTML = rows.length
    ? rows.map((group) => `
      <button type="button" data-group-id="${escapeHtml(group.group_id)}" class="group-card ${String(group.group_id) === String(state.selectedGroupId) ? "is-selected" : ""} ${group.enabled ? "" : "is-off"} ${group.allowed_by_mode ? "" : "is-blocked"}">
        <header>
          <span class="group-card-title">
            <b>${escapeHtml(group.name || group.group_name || `群 ${group.group_id}`)}</b>
            <small>${escapeHtml(group.group_id)}</small>
          </span>
          <span class="badge ${group.enabled ? "" : "off"}">${escapeHtml(group.enabled ? "观测中" : "停用")}</span>
        </header>
        <p class="group-card-summary">${escapeHtml(group.atmosphere?.last_summary || group.atmosphere?.mood || "暂无群聊氛围摘要")}</p>
        <div class="group-card-metrics">
          <span>消息 <b>${escapeHtml(group.message_count || 0)}</b></span>
          <span>群友 <b>${escapeHtml(group.member_count || 0)}</b></span>
          <span>话题 <b>${escapeHtml(group.topic_count || 0)}</b></span>
        </div>
        ${groupWakeupCardLine(group)}
        <footer>
          <span class="${group.allowed_by_mode ? "" : "warn-text"}">${escapeHtml(group.allowed_by_mode ? "名单允许" : "名单拦截")}</span>
          <span>插话 ${escapeHtml(group.interject_today || 0)}</span>
          <span>${escapeHtml(group.last_seen || "暂无活跃")}</span>
        </footer>
      </button>
    `).join("")
    : `<div class="empty small">暂无群聊观测数据</div>`;
  document.querySelectorAll("[data-group-id]").forEach((row) => {
    row.addEventListener("click", async () => {
      state.selectedGroupId = row.dataset.groupId;
      renderGroups();
      await renderGroupDetail(true);
    });
  });
  renderGroupDetail();
}

function groupWakeupCardLine(group) {
  const wake = group.last_group_wakeup || {};
  const fatigue = group.wakeup_fatigue || {};
  if (!wake.word && !group.wakeup_log_count && !fatigue.value) return "";
  const wakeText = wake.word
    ? `${wake.strength_label || "唤醒"}｜${wake.word}｜${wake.time || ""}`
    : "暂无命中";
  const fatigueText = fatigue.label ? `疲劳 ${fatigue.label}${fatigue.value ? ` ${fatigue.value}/${fatigue.limit || "-"}` : ""}` : "";
  return `
    <div class="group-card-wakeup">
      <span>${escapeHtml(wakeText)}</span>
      <span>${escapeHtml(fatigueText)}</span>
    </div>
  `;
}

async function renderGroupDetail(forceFetch = false) {
  const box = $("#groupDetail");
  if (!state.selectedGroupId) {
    box.innerHTML = `<div class="empty">选择左侧群聊后查看话题线、关系网和插话状态</div>`;
    return;
  }
  let detail = state.groups.find((group) => String(group.group_id) === String(state.selectedGroupId));
  if (forceFetch || !detail?.formatted) {
    try {
      detail = await fetchJson(`/group?group_id=${encodeURIComponent(state.selectedGroupId)}`);
    } catch (error) {
      box.innerHTML = `<p class="muted">详情读取失败：${escapeHtml(error.message)}</p>`;
      return;
    }
  }
  const episodes = (detail.group_episodes || []).map((item, index) => [`#${index + 1}`, item.summary || item.title || JSON.stringify(item)]);
  const groupName = detail.name || detail.group_name || `群 ${detail.group_id}`;
  box.innerHTML = `
    <div class="group-detail-hero">
      <div class="group-detail-title">
        <span class="eyebrow">群聊详情</span>
        <h2>${escapeHtml(groupName)}</h2>
        <div class="group-detail-status">
          <span>${escapeHtml(detail.group_id)}</span>
          <span class="${detail.enabled ? "ok-text" : "warn-text"}">${escapeHtml(detail.enabled ? "观测中" : "已停用")}</span>
          <span class="${detail.allowed_by_mode ? "ok-text" : "warn-text"}">${escapeHtml(detail.allowed_by_mode ? "名单允许" : "名单拦截")}</span>
          <span>最近 ${escapeHtml(detail.last_seen || "暂无")}</span>
        </div>
      </div>
      <div class="group-detail-actions">
        <button data-group-action="toggle">${escapeHtml(detail.enabled ? "停用" : "启用")}</button>
        <button data-group-action="reset_interjection">重置插话</button>
        <button data-group-action="clear_observation" class="danger">清空观测</button>
      </div>
    </div>
    <div class="visual-strip group-visual-strip">
      ${miniStat("消息", detail.message_count || 0)}
      ${miniStat("群友", detail.member_count || Object.keys(detail.members || {}).length)}
      ${miniStat("已识别", detail.recognized_member_count || 0)}
      ${miniStat("黑话", detail.slang_count || (detail.slang_terms || []).length)}
      ${miniStat("话题", detail.topic_count || (detail.topic_threads || []).length)}
    </div>
    <div class="detail-grid group-detail-grid">
      ${detailBlock("群状态", detail.formatted?.status || "", [["常用词", formatSlangTerms(detail.slang_terms || [])]])}
      ${detailBlock("插话反馈", detail.formatted?.feedback || "", [])}
      <section class="detail-block wide"><h2>唤醒记录</h2>${groupWakeupPanel(detail)}</section>
      <section class="detail-block wide"><h2>话题线</h2>${groupTopicThreadsView(detail.topic_threads || [])}</section>
      <section class="detail-block wide"><h2>关系网</h2>${relationshipGraphView(detail.relationship_edges || {}, detail.members || {})}</section>
      <section class="detail-block"><h2>消息活跃</h2>${messageTimelineSvg(detail.recent_messages || [])}</section>
      ${detailBlock("群聊片段", "", episodes)}
      ${detailBlock("关系网摘要", detail.formatted?.relationship_graph || "", [])}
    </div>
  `;
  bindGroupActions(detail);
}

function groupWakeupPanel(detail) {
  const logs = Array.isArray(detail.group_wakeup_logs) ? detail.group_wakeup_logs : [];
  const fatigue = detail.wakeup_fatigue || {};
  const ratio = Math.max(0, Math.min(100, Number(fatigue.ratio || 0) * 100));
  const last = detail.last_group_wakeup || {};
  return `
    <div class="group-wakeup-overview">
      <article>
        <span>最近唤醒</span>
        <b>${escapeHtml(last.word || "暂无")}</b>
        <small>${escapeHtml([last.strength_label, last.sender_name, last.time].filter(Boolean).join(" · ") || "还没有记录")}</small>
      </article>
      <article>
        <span>唤醒疲劳</span>
        <b>${escapeHtml(fatigue.label || "无")}</b>
        <div class="fatigue-meter"><i style="width:${ratio}%"></i></div>
        <small>${escapeHtml(`${fatigue.value || 0}/${fatigue.limit || "-"} · ${fatigue.updated || "暂无"}`)}</small>
      </article>
      <article>
        <span>记录数</span>
        <b>${escapeHtml(detail.wakeup_log_count || logs.length || 0)}</b>
        <small>命中、冷却和概率未触发</small>
      </article>
    </div>
    ${logs.length ? `
      <div class="group-wakeup-log-list">
        ${logs.map(groupWakeupLogItem).join("")}
      </div>
    ` : `<div class="empty small">暂无群聊唤醒记录</div>`}
  `;
}

function groupWakeupLogItem(item) {
  const resultLabel = {
    woke: "已唤醒",
    blocked: "冷却拦截",
    missed: "未触发",
  }[item.result] || item.result || "记录";
  const isDim = item.result !== "woke";
  const topicWeight = item.topic_weight || {};
  const weightText = topicWeight.reason
    ? `权重 ${Math.round(Number(topicWeight.multiplier || 1) * 100)}%：${topicWeight.reason}`
    : "";
  return `
    <article class="group-wakeup-log ${isDim ? "is-dim" : ""}">
      <header>
        <b>${escapeHtml(resultLabel)}</b>
        <span>${escapeHtml(item.strength_label || item.type || "-")}</span>
        <time>${escapeHtml(item.time || "")}</time>
      </header>
      <p>${escapeHtml(item.text || "-")}</p>
      <footer>
        <span>${escapeHtml(item.sender_name || item.sender_id || "-")}</span>
        <span>${escapeHtml(item.word ? `词：${item.word}` : item.reason || "")}</span>
        ${item.probability ? `<span>${escapeHtml(`概率 ${Math.round(Number(item.probability || 0) * 100)}%`)}</span>` : ""}
        ${weightText ? `<span>${escapeHtml(weightText)}</span>` : ""}
        ${item.fatigue_label ? `<span>${escapeHtml(`疲劳 ${item.fatigue_label}`)}</span>` : ""}
      </footer>
      ${item.note ? `<small>${escapeHtml(item.note)}</small>` : ""}
    </article>
  `;
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
    worldbookStat("待确认观察", worldbook.pending_observation_total || 0, "确认后才写入重要记忆"),
    worldbookStat("识别方式", worldbook.enabled ? "QQ 精确" : "关闭", worldbook.match_aliases ? "称呼辅助开启" : "仅 QQ 确认"),
  ].join("");
  const clearPendingButton = $("#worldbookClearPendingBtn");
  if (clearPendingButton) clearPendingButton.disabled = !(worldbook.pending_observation_total > 0);
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
  renderSkillGrowth();
  renderInteractionImpact();
  renderMemoryComposition();
  renderSlangCloud();
}

function renderSkillGrowth() {
  const growth = state.overview?.skill_growth || {};
  const items = Array.isArray(growth.items) ? growth.items : [];
  const panel = $("#skillGrowthPanel");
  if (!panel) return;
  if (!growth.enabled) {
    panel.innerHTML = `<div class="empty small">技能成长未开启</div>`;
    return;
  }
  if (!items.length) {
    panel.innerHTML = `<div class="empty small">暂无技能记录</div>`;
    return;
  }
  panel.innerHTML = `
    <div class="skill-growth-head">
      <span>${escapeHtml(growth.skill_count || items.length)} 项技能</span>
      <span>成长倍率 ${escapeHtml(growth.rate || 1)}</span>
      <span>${growth.schedule_influence ? `影响日程 ${escapeHtml(growth.schedule_influence_strength ?? "-")}` : "不影响日程"}</span>
      <span>更新 ${escapeHtml(growth.updated || "-")}</span>
    </div>
    <div class="skill-growth-grid">
      ${items.map((item) => {
        const logs = Array.isArray(item.recent_logs) ? item.recent_logs : [];
        return `
          <article class="skill-card is-collapsed">
            <button type="button" class="skill-card-toggle" data-skill-toggle aria-expanded="false">
              <header>
                <div>
                  <span>${escapeHtml(item.category || "能力")}</span>
                  <h3>${escapeHtml(item.name || "未命名技能")}</h3>
                </div>
                <b>Lv.${escapeHtml(item.level || 1)}</b>
              </header>
            </button>
            <div class="skill-level-line">
              <span>${escapeHtml(item.level_title || "")}</span>
              <small>${escapeHtml(item.next_exp ? `${item.exp}/${item.next_exp}` : `${item.exp}`)}</small>
            </div>
            <div class="skill-meter"><i style="width:${escapeHtml(item.progress || 0)}%"></i></div>
            <div class="skill-card-body">
              <p>${escapeHtml(item.description || "")}</p>
              <div class="skill-meta">
                <span>训练 ${escapeHtml(item.training_count || 0)} 次</span>
                <span>最近 ${escapeHtml(item.last_trained || "未训练")}</span>
              </div>
              ${logs.length ? `
                <div class="skill-log">
                  ${logs.slice().reverse().map((log) => `
                    <p><b>${escapeHtml(log.level_up ? "升级" : `+${log.exp || 0}`)}</b><span>${escapeHtml(log.activity || "日程练习")}</span><small>${escapeHtml(log.time || "")}</small></p>
                  `).join("")}
                </div>
              ` : ""}
              <details class="skill-editor">
                <summary>管理</summary>
                <div class="skill-editor-grid">
                  <label>名称 <input data-skill-name="${escapeHtml(item.id || "")}" value="${escapeHtml(item.name || "")}" maxlength="32" /></label>
                  <label>分类 <input data-skill-category="${escapeHtml(item.id || "")}" value="${escapeHtml(item.category || "")}" maxlength="20" /></label>
                  <label>等级
                    <select data-skill-level="${escapeHtml(item.id || "")}">
                      ${[1, 2, 3, 4, 5, 6].map((level) => `<option value="${level}" ${Number(item.level || 1) === level ? "selected" : ""}>Lv.${level}</option>`).join("")}
                    </select>
                  </label>
                  <label>经验 <input data-skill-exp="${escapeHtml(item.id || "")}" type="number" min="0" step="1" value="${escapeHtml(item.exp || 0)}" /></label>
                  <label class="wide-field">关键词 <input data-skill-keywords="${escapeHtml(item.id || "")}" value="${escapeHtml((item.keywords || []).join(", "))}" maxlength="180" /></label>
                </div>
                <div class="skill-editor-actions">
                  <button type="button" data-skill-save="${escapeHtml(item.id || "")}">保存技能</button>
                  <button type="button" class="danger-outline" data-skill-delete="${escapeHtml(item.id || "")}">删除</button>
                </div>
              </details>
            </div>
          </article>
        `;
      }).join("")}
    </div>
  `;
  bindSkillGrowthActions();
}

function skillExpFloor(level) {
  return { 1: 0, 2: 100, 3: 260, 4: 520, 5: 900, 6: 1400 }[Number(level || 1)] || 0;
}

function skillField(id, field) {
  return document.querySelector(`[data-skill-${field}="${CSS.escape(id)}"]`);
}

function bindSkillGrowthActions() {
  document.querySelectorAll("[data-skill-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const card = button.closest(".skill-card");
      if (!card) return;
      const collapsed = card.classList.toggle("is-collapsed");
      button.setAttribute("aria-expanded", String(!collapsed));
    });
  });
  document.querySelectorAll("[data-skill-level]").forEach((select) => {
    select.addEventListener("change", () => {
      const id = select.dataset.skillLevel || "";
      const expInput = skillField(id, "exp");
      if (expInput && Number(expInput.value || 0) < skillExpFloor(select.value)) {
        expInput.value = String(skillExpFloor(select.value));
      }
    });
  });
  document.querySelectorAll("[data-skill-save]").forEach((button) => {
    button.addEventListener("click", async () => {
      const id = button.dataset.skillSave || "";
      await runAction(() => postJson("/skill/update", {
        id,
        name: skillField(id, "name")?.value || "",
        category: skillField(id, "category")?.value || "",
        level: Number(skillField(id, "level")?.value || 1),
        exp: Number(skillField(id, "exp")?.value || 0),
        keywords: skillField(id, "keywords")?.value || "",
      }), "已保存技能", button);
    });
  });
  document.querySelectorAll("[data-skill-delete]").forEach((button) => {
    button.addEventListener("click", async () => {
      const id = button.dataset.skillDelete || "";
      if (!requireSecondClick(button, `skill:${id}`, "再次点击删除技能", "再次点击删除")) return;
      await runAction(() => postJson("/skill/update", { id, delete: true }), "已删除技能", button);
    });
  });
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
  $("#lifeCurrentSeed").textContent = [current.time, current.mood, current.message_seed].filter(Boolean).join(" · ") || "暂无细化";
}

function normalizeLocationText(value) {
  const text = String(value || "").trim();
  if (!text || text === "地点感平稳" || text === "地点无明显变化") return "随当前日程变化";
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
  $("#dreamContent").textContent = dream.content || dream.label || "暂无梦境内容";
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
    : `<div class="empty small">暂无今日状态</div>`;
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
    : `<div class="empty small">暂无日记</div>`;
}

function renderDreamFragments(fragments) {
  if (!fragments.length) {
    $("#dreamFragments").innerHTML = `<div class="empty small">暂无梦境碎片</div>`;
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
    ? "上层书架"
    : "创作未开启";
  const creativeSettings = {
    "创作": creative.enabled ? "开启" : "关闭",
    "提起方式": creative.hidden_mode ? "节点自然提起" : "普通模式",
    "灵感触发概率": formatPercent(settings.creative_inspiration_probability),
    "节点提起概率": formatPercent(settings.creative_share_probability),
    "单次创作": `${settings.creative_chars_per_session || settings.creative_base_chars_per_hour || 0} 字/次`,
  };
  if (privateReading.available) {
    creativeSettings["夹层阅读"] = privateReading.boredom_read_enabled ? "可触发" : "关闭";
    creativeSettings["征求推荐"] = privateReading.ask_recommendation_enabled ? "可触发" : "关闭";
  }
  renderDl("#creativeSettings", creativeSettings);
  const publicBooks = bookshelf.public_books || [];
  $("#bookshelfPublicBooks").innerHTML = publicBooks.length
    ? renderBookCategoryShelves(publicBooks, { emptyText: "上层书架为空", reverseBooks: true })
    : `<div class="empty">上层书架为空</div>`;
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
        <p>需要密码</p>
      </div>
    </div>
  `;
}

function renderUnlockedDrawer(items) {
  if (!items.length) {
    return `<div class="empty small">抽屉已经打开，但里面暂时还没有日记本或夹层藏书。</div>`;
  }
  return renderBookCategoryShelves(items, {
    reverseBooks: true,
    notes: {
      "日记": "按日期收进同一本里",
      "夹层藏书": "只保留标题和阅读印象",
    },
  });
}

function renderBookCategoryShelves(items, options = {}) {
  const books = Array.isArray(items) ? items.filter(Boolean) : [];
  if (!books.length) return `<div class="empty small">${escapeHtml(options.emptyText || "暂无书籍")}</div>`;
  const groups = [];
  books.forEach((book) => {
    const title = bookshelfCategoryTitle(book);
    let group = groups.find((item) => item.title === title);
    if (!group) {
      group = { title, books: [] };
      groups.push(group);
    }
    group.books.push(book);
  });
  return groups.map((group) => {
    const rowClass = options.rowClass || (group.books.some((book) => book.kind === "diary" || book.kind === "jm_album") ? "drawer-book-row" : "book-row");
    const booksForRender = options.reverseBooks ? group.books.slice().reverse() : group.books;
    const note = options.notes?.[group.title] || bookshelfCategoryNote(group.title, group.books);
    return `
      <section class="drawer-book-group book-category-group ${escapeHtml(categorySlug(group.title))}">
        <header>
          <span>${escapeHtml(group.title)} <b>${escapeHtml(group.books.length)}</b></span>
          <small>${escapeHtml(note)}</small>
        </header>
        <div class="${escapeHtml(rowClass)}">${booksForRender.map(renderBookshelfBook).join("")}</div>
      </section>
    `;
  }).join("");
}

function bookshelfCategoryTitle(book) {
  const raw = String(book?.category || "").trim();
  if (raw) return raw;
  if (book?.kind === "creative") return book.work_type || "创作";
  if (book?.kind === "diary") return "日记";
  if (book?.kind === "browsing") return "浏览记录";
  if (book?.kind === "jm_album") return "夹层藏书";
  return "其他";
}

function bookshelfCategoryNote(title, books) {
  const kind = books[0]?.kind || "";
  if (kind === "browsing") return "新闻阅读和主动搜索会在这里留痕";
  if (kind === "creative") return "Bot 自己慢慢推进的文本作品";
  if (kind === "diary") return "按日期翻阅";
  if (kind === "jm_album") return "夹层内的私密藏书";
  return `${books.length} 本`;
}

function categorySlug(value) {
  const text = String(value || "category").toLowerCase();
  return text.replace(/[^a-z0-9\u4e00-\u9fff_-]+/g, "-").slice(0, 32) || "category";
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
  const title = item.title || "未命名";
  const meta = item.progress || item.created || item.status || item.tone || "";
  return `
    <button type="button" class="shelf-book ${escapeHtml(kind)}" data-book-id="${escapeHtml(bookId)}" title="${escapeHtml(title)}">
      <div class="book-spine">
        <i class="book-shine"></i>
        <span>${escapeHtml(kindLabel)}</span>
        <b>${escapeHtml(title)}</b>
        ${meta ? `<small>${escapeHtml(meta)}</small>` : `<small>书柜藏本</small>`}
        <em></em>
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

function bookTagInputValue(tags) {
  return Array.isArray(tags) ? tags.filter(Boolean).join("、") : "";
}

function parseBookTagInput(value) {
  const seen = new Set();
  return String(value || "")
    .split(/[,，、\s\n\r]+/)
    .map((item) => item.trim())
    .filter((item) => {
      if (!item) return false;
      const key = item.toLocaleLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .slice(0, 8);
}

function mergeBookTagCandidates(...groups) {
  const seen = new Set();
  const result = [];
  groups.flat().forEach((tag) => {
    const text = String(tag || "").trim();
    if (!text) return;
    const key = text.toLocaleLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    result.push(text);
  });
  return result.slice(0, 16);
}

function renderBookPreferenceEditor(book) {
  if (book.kind !== "jm_album") return "";
  const likedValue = bookTagInputValue(book.user_liked_tags);
  const dislikedValue = bookTagInputValue(book.user_disliked_tags);
  const sourceTags = Array.isArray(book.tags) ? book.tags.filter(Boolean) : [];
  const preferenceTags = Array.isArray(book.preference_tags) ? book.preference_tags.filter(Boolean) : [];
  const preferenceChips = preferenceTags.length
    ? `<div class="book-preference-auto-tags"><span>Bot 标注</span>${preferenceTags.map((tag) => `<b>${escapeHtml(tag)}</b>`).join("")}</div>`
    : "";
  const candidates = mergeBookTagCandidates(sourceTags, preferenceTags);
  const candidatePicker = candidates.length
    ? `
      <div class="book-preference-candidates">
        <span>现有标签</span>
        ${candidates.map((tag) => `
          <div class="book-preference-candidate">
            <b>${escapeHtml(tag)}</b>
            <button type="button" data-book-tag-pick data-tag-target="liked" data-tag-value="${escapeHtml(tag)}">喜好</button>
            <button type="button" data-book-tag-pick data-tag-target="disliked" data-tag-value="${escapeHtml(tag)}">厌恶</button>
          </div>
        `).join("")}
      </div>
    `
    : "";
  return `
    <form class="book-preference-editor" data-book-preference-form>
      <header>
        <span>偏好标签</span>
        <button type="submit">保存标签</button>
      </header>
      <div class="book-preference-fields">
        <label>
          <span>喜好</span>
          <input type="text" name="liked_tags" value="${escapeHtml(likedValue)}" placeholder="画风、节奏、设定">
        </label>
        <label>
          <span>厌恶</span>
          <input type="text" name="disliked_tags" value="${escapeHtml(dislikedValue)}" placeholder="拖沓、雷点、题材">
        </label>
      </div>
      ${candidatePicker}
      ${preferenceChips}
    </form>
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
  if (book.kind === "diary") {
    const entries = Array.isArray(book.entries) ? book.entries : [];
    state.selectedDiaryDate = entries[entries.length - 1]?.date || "";
  }
  if (book.kind === "browsing") {
    const entries = Array.isArray(book.entries) ? book.entries : [];
    state.selectedBrowsingIndex = Math.max(0, entries.length - 1);
  }
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
    creative: book.work_type || "创作书",
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
  const preferenceEditor = renderBookPreferenceEditor(book);
  const readingImpressionText = book.kind === "jm_album"
    ? String(book.reading_impression || book.impression || "").replace(/^读后感[:：]\s*/, "").trim()
    : "";
  const pageCommentCount = book.kind === "jm_album"
    ? Number(book.page_comment_count ?? (Array.isArray(book.page_comments) ? book.page_comments.length : 0))
    : 0;
  const botRating = Number(book.rating || 0);
  const userRating = Number(book.user_rating || 0);
  const ratingReason = String(book.user_rating_reason || book.rating_reason || "").trim();
  const ratingMeta = book.kind === "jm_album" && (botRating || userRating || ratingReason)
    ? `
      <div class="book-rating-row">
        ${botRating ? `<span>Bot 评分 <b>${escapeHtml(botRating)}/10</b></span>` : ""}
        ${userRating ? `<span>你的评分 <b>${escapeHtml(userRating)}/10</b></span>` : ""}
        ${ratingReason ? `<small>${escapeHtml(ratingReason)}</small>` : ""}
      </div>
    `
    : "";
  const readingImpression = readingImpressionText
    ? `
      <section class="book-reading-impression">
        <span>Bot 的读后感</span>
        ${ratingMeta}
        <p>${escapeHtml(readingImpressionText)}</p>
      </section>
    `
    : ratingMeta
      ? `<section class="book-reading-impression"><span>读后评分</span>${ratingMeta}</section>`
    : "";
  const manageActions = book.kind === "browsing" ? "" : `
    <div class="book-manage-actions">
      ${book.kind === "jm_album" ? `<button type="button" data-book-reread>让 Bot 重读</button>` : ""}
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
  if (state.bookshelfPage === "reader" && book.kind === "diary") {
    panel.innerHTML = renderDiaryBookReader(book, kindLabel, diaryEntries, diaryEntry);
    return;
  }
  if (state.bookshelfPage === "reader" && book.kind === "browsing") {
    panel.innerHTML = renderBrowsingBookReader(book, kindLabel, diaryEntries);
    return;
  }
  if (state.bookshelfPage === "reader" && book.kind === "creative") {
    panel.innerHTML = renderCreativeBookReader(book, kindLabel, displayTitle, displayIntro, displayContent);
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
            ${book.kind === "jm_album" ? `<div><dt>备注</dt><dd>${escapeHtml(pageCommentCount)} 条</dd></div>` : ""}
            ${book.created ? `<div><dt>入柜</dt><dd>${escapeHtml(book.created)}</dd></div>` : ""}
          </dl>
          ${readingImpression}
          ${tags}
          ${preferenceEditor}
          ${manageActions}
          <button type="button" class="read-button" data-book-read>开始阅读</button>
        </div>
      </article>
    `;
  void hydrateBookshelfImages(panel);
}

function renderJmAlbumReader(book, kindLabel, displayTitle, displayIntro, readingImpression = "") {
  const pages = Array.isArray(book.pages) ? book.pages : [];
  const pageCommentCount = Number(book.page_comment_count ?? (Array.isArray(book.page_comments) ? book.page_comments.length : pages.filter((page) => String(page.comment || "").trim()).length));
  const maxStart = Math.max(0, pages.length - (pages.length % 2 === 0 ? 2 : 1));
  const start = Math.min(Math.max(0, Number(state.selectedBookSpreadIndex || 0)), maxStart);
  state.selectedBookSpreadIndex = start % 2 === 0 ? start : start - 1;
  const spread = pages.slice(state.selectedBookSpreadIndex, state.selectedBookSpreadIndex + 2);
  const firstPage = spread[0]?.index || state.selectedBookSpreadIndex + 1;
  const lastPage = spread[spread.length - 1]?.index || firstPage;
  const isLastSpread = state.selectedBookSpreadIndex + 2 >= pages.length;
  const userRating = Number(book.user_rating || 0);
  const userRatingReason = String(book.user_rating_reason || "").trim();
  const ratingPanel = isLastSpread
    ? `
      <section class="manga-rating-panel">
        <div>
          <span>读完评分</span>
          <b>${userRating ? `你给了 ${escapeHtml(userRating)}/10` : "读完后给它打个分"}</b>
          ${userRatingReason ? `<p>${escapeHtml(userRatingReason)}</p>` : ""}
        </div>
        <div class="manga-rating-buttons" data-book-rating-album="${escapeHtml(book.album_id || "")}">
          ${Array.from({ length: 10 }, (_, index) => {
            const value = index + 1;
            return `<button type="button" data-book-rating="${value}" class="${userRating === value ? "is-active" : ""}">${value}</button>`;
          }).join("")}
        </div>
      </section>
    `
    : "";
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
        <span>${escapeHtml(kindLabel)} · ${escapeHtml(firstPage)}-${escapeHtml(lastPage)} / ${escapeHtml(pages.length)} · 备注 ${escapeHtml(pageCommentCount)} 条</span>
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
            <button type="button" data-book-reread>让 Bot 重读</button>
            <button type="button" class="danger-outline" data-book-delete
              data-book-kind="${escapeHtml(book.kind || "")}"
              data-book-id="${escapeHtml(book.id || "")}"
              data-book-album-id="${escapeHtml(book.album_id || "")}"
              data-book-title="${escapeHtml(book.title || "")}">从书柜移除</button>
          </div>
        </header>
        ${readingImpression}
        <div class="manga-spread">
          ${spread.map((page, spreadIndex) => {
            const comment = String(page.comment || "").trim();
            const note = comment
              ? `<details class="manga-page-note ${spreadIndex === 0 ? "left" : "right"}"><summary>Bot 批注</summary><p>${escapeHtml(comment)}</p></details>`
              : "";
            return `
            <figure class="manga-page ${comment ? `has-note ${spreadIndex === 0 ? "note-left" : "note-right"}` : ""}">
              ${spreadIndex === 0 ? note : ""}
              <div class="manga-page-image">
                ${bookshelfImageTag(page.src, `${book.title || "夹层藏书"} 第 ${page.index} 页`)}
                <figcaption>${escapeHtml(page.index)} / ${escapeHtml(pages.length)}</figcaption>
              </div>
              ${spreadIndex !== 0 ? note : ""}
            </figure>
          `; }).join("")}
          ${spread.length < 2 ? `<figure class="manga-page blank"><span>末页</span></figure>` : ""}
        </div>
        ${ratingPanel}
      </div>
    </article>
  `;
}

function renderDiaryBookReader(book, kindLabel, entries, selectedEntry) {
  const rows = Array.isArray(entries) ? entries : [];
  const current = selectedEntry || rows[rows.length - 1] || {};
  const currentDate = current.date || state.selectedDiaryDate || "";
  const tags = Array.isArray(current.tags) && current.tags.length
    ? `<div class="book-tags">${current.tags.map((tag) => `<span>${escapeHtml(tag)}</span>`).join("")}</div>`
    : "";
  return `
    <article class="reader-page subpage diary diary-reader-page">
      <nav class="book-breadcrumb">
        <button type="button" data-book-close>书柜</button>
        <span>/</span>
        <button type="button" data-book-back>${escapeHtml(book.title || "日记本")}</button>
        <span>/ 阅读</span>
      </nav>
      <div class="reader-toolbar">
        <button type="button" data-book-back>返回简介</button>
        <span>${escapeHtml(kindLabel)} · ${escapeHtml(rows.length)} 天</span>
        <button type="button" data-book-close>收回书柜</button>
      </div>
      <div class="diary-reader-shell">
        <aside class="diary-date-rail">
          <header>
            <span>日期</span>
            <b>${escapeHtml(rows.length)}</b>
          </header>
          <div class="diary-date-list">
            ${rows.slice().reverse().map((entry) => `
              <button type="button" data-diary-jump="${escapeHtml(entry.date || "")}" class="${entry.date === currentDate ? "is-active" : ""}">
                <b>${escapeHtml(entry.date || "某天")}</b>
                <span>${escapeHtml(shortName(entry.intro || entry.content || "没有摘要", 34))}</span>
              </button>
            `).join("")}
          </div>
        </aside>
        <section class="reader-paper diary-paper">
          <header class="reader-page-head">
            <span>${escapeHtml(current.generated_at || "日记")}</span>
            <h2>${escapeHtml(currentDate ? `${currentDate} 的日记` : "日记")}</h2>
            ${current.intro ? `<p>${escapeHtml(current.intro)}</p>` : ""}
          </header>
          ${tags}
          <div class="reader-content diary-reader-content">${formatBookContent(current.content || current.intro || "这一天的日记暂时没有正文。")}</div>
          <footer class="reader-page-foot">
            <span>${escapeHtml(book.created || "夹层日记")}</span>
            <button type="button" class="danger-outline" data-book-delete
              data-book-kind="diary"
              data-book-id="${escapeHtml(book.id || "")}"
              data-book-title="${escapeHtml(book.title || "")}"
              data-book-date="${escapeHtml(currentDate)}">删除当前日记</button>
          </footer>
        </section>
      </div>
    </article>
  `;
}

function renderBrowsingBookReader(book, kindLabel, entries) {
  const rows = Array.isArray(entries) ? entries : [];
  const safeIndex = rows.length ? Math.max(0, Math.min(rows.length - 1, Number(state.selectedBrowsingIndex || 0))) : 0;
  state.selectedBrowsingIndex = safeIndex;
  const current = rows[safeIndex] || {};
  const tags = Array.isArray(current.tags) && current.tags.length
    ? `<div class="book-tags">${current.tags.map((tag) => `<span>${escapeHtml(tag)}</span>`).join("")}</div>`
    : "";
  const url = String(current.source_url || "").trim();
  const href = browsingSourceHref(url);
  const addressText = url || current.query || current.title || "about:blank";
  return `
    <article class="reader-page subpage browsing browsing-reader-page">
      <nav class="book-breadcrumb">
        <button type="button" data-book-close>书柜</button>
        <span>/</span>
        <button type="button" data-book-back>${escapeHtml(book.title || "浏览记录")}</button>
        <span>/ 阅读</span>
      </nav>
      <div class="browser-shell">
        <header class="browser-chrome">
          <div class="browser-dots"><i></i><i></i><i></i></div>
          <div class="browser-address">
            <span>${escapeHtml(current.source_label || kindLabel)}</span>
            <b title="${escapeHtml(addressText)}">${escapeHtml(addressText)}</b>
          </div>
          <button type="button" data-book-close>收回书柜</button>
        </header>
        <div class="browser-body">
          <aside class="browser-history-sidebar">
            <header>
              <b>历史记录</b>
              <span>${escapeHtml(rows.length)} 条</span>
            </header>
            <div class="browser-history-list">
              ${rows.slice().reverse().map((entry) => {
                const originalIndex = rows.indexOf(entry);
                return `
                  <button type="button" data-browsing-index="${escapeHtml(originalIndex)}" class="${originalIndex === safeIndex ? "is-active" : ""}">
                    <span>${escapeHtml(entry.source_label || "记录")}</span>
                    <b>${escapeHtml(entry.title || entry.query || "未命名记录")}</b>
                    <small>${escapeHtml(entry.generated_at || entry.date || "")}</small>
                  </button>
                `;
              }).join("")}
            </div>
          </aside>
          <section class="browser-page-view">
            <header>
              <span>${escapeHtml(current.source_label || "浏览记录")}</span>
              <h2>${escapeHtml(current.title || current.query || "未命名记录")}</h2>
              ${current.query ? `<p>搜索词：${escapeHtml(current.query)}</p>` : ""}
            </header>
            ${tags}
            <div class="browser-note-content">${formatBookContent(current.content || current.intro || "这条浏览记录暂时没有正文。")}</div>
            <footer>
              <span>${escapeHtml(current.generated_at || current.date || "未知时间")}</span>
              ${url ? `<button type="button" class="browser-source-copy" data-copy-source-url="${escapeHtml(href)}">复制链接</button>` : ""}
            </footer>
          </section>
        </div>
      </div>
    </article>
  `;
}

function browsingSourceHref(url) {
  const text = String(url || "").trim();
  if (!text) return "";
  if (/^(https?:|mailto:)/i.test(text)) return text;
  return `https://${text.replace(/^\/+/, "")}`;
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

function creativeReadingMode(book) {
  const type = String(book?.work_type || book?.category || "").toLowerCase();
  if (/诗|歌词|歌/.test(type)) return "poetry";
  if (/剧本|短剧|脚本|对白|分镜/.test(type)) return "script";
  if (/设定|世界观|角色|图鉴|怪谈|档案/.test(type)) return "lore";
  if (/随笔|散文|札记|观察|影评|读后感/.test(type)) return "essay";
  return "prose";
}

function creativeModeLabel(mode) {
  return {
    poetry: "诗页",
    script: "剧本",
    lore: "设定册",
    essay: "札记",
    prose: "正文",
  }[mode] || "正文";
}

function splitCreativeChunks(book, fallbackContent) {
  const chunks = Array.isArray(book?.chunks) ? book.chunks : [];
  const rows = chunks
    .map((chunk, index) => ({
      index: Number(chunk.index || index + 1),
      text: String(chunk.text || "").trim(),
      created: String(chunk.created || "").trim(),
    }))
    .filter((chunk) => chunk.text);
  if (rows.length) return rows;
  return [{ index: 1, text: String(fallbackContent || "").trim() || "这本书还没有正文。", created: "" }];
}

function formatCreativeScript(text) {
  const lines = String(text || "").split(/\n+/).map((line) => line.trim()).filter(Boolean);
  return lines.length
    ? lines.map((line) => {
      const match = line.match(/^([^：:]{1,14})[：:]\s*(.+)$/);
      if (match) {
        return `<p class="script-line"><b>${escapeHtml(match[1])}</b><span>${escapeHtml(match[2])}</span></p>`;
      }
      return `<p class="script-stage">${escapeHtml(line)}</p>`;
    }).join("")
    : `<p class="script-stage">这段剧本还没有正文。</p>`;
}

function formatCreativeLore(text) {
  const blocks = String(text || "").split(/\n{2,}/).map((part) => part.trim()).filter(Boolean);
  return blocks.length
    ? blocks.map((block) => {
      const lines = block.split(/\n+/).map((line) => line.trim()).filter(Boolean);
      const head = lines[0] || "设定条目";
      const body = lines.slice(1).join("\n") || block;
      return `
        <section class="lore-entry">
          <b>${escapeHtml(head.replace(/^#+\s*/, ""))}</b>
          <p>${escapeHtml(body)}</p>
        </section>
      `;
    }).join("")
    : `<section class="lore-entry"><b>空白条目</b><p>这本设定册还没有正文。</p></section>`;
}

function formatCreativeContentByMode(text, mode) {
  if (mode === "poetry") {
    const lines = String(text || "").split(/\n+/).map((line) => line.trim()).filter(Boolean);
    return `<div class="poem-lines">${(lines.length ? lines : ["这首诗还没有正文。"]).map((line) => `<p>${escapeHtml(line)}</p>`).join("")}</div>`;
  }
  if (mode === "script") return formatCreativeScript(text);
  if (mode === "lore") return formatCreativeLore(text);
  return formatBookContent(text);
}

function renderCreativeBookReader(book, kindLabel, displayTitle, displayIntro, displayContent) {
  const mode = creativeReadingMode(book);
  const chunks = splitCreativeChunks(book, displayContent);
  const chunkNav = chunks.length > 1
    ? `<aside class="creative-chapter-rail">
        <span>片段</span>
        ${chunks.map((chunk) => `<a href="#creative-chunk-${escapeHtml(chunk.index)}">${escapeHtml(chunk.index)}</a>`).join("")}
      </aside>`
    : "";
  const contentHtml = chunks.map((chunk) => `
    <section class="creative-reader-chunk" id="creative-chunk-${escapeHtml(chunk.index)}">
      <header>
        <span>${escapeHtml(creativeModeLabel(mode))} ${escapeHtml(chunk.index)}</span>
        ${chunk.created ? `<small>${escapeHtml(chunk.created)}</small>` : ""}
      </header>
      <div class="reader-content creative-content ${escapeHtml(mode)}">${formatCreativeContentByMode(chunk.text, mode)}</div>
    </section>
  `).join("");
  return `
    <article class="reader-page subpage creative creative-reader ${escapeHtml(mode)}">
      <nav class="book-breadcrumb">
        <button type="button" data-book-close>书柜</button>
        <span>/</span>
        <button type="button" data-book-back>${escapeHtml(book.title || "未命名")}</button>
        <span>/ 阅读</span>
      </nav>
      <div class="reader-toolbar">
        <button type="button" data-book-back>返回简介</button>
        <span>${escapeHtml(kindLabel)} · ${escapeHtml(creativeModeLabel(mode))}</span>
        <button type="button" data-book-close>收回书柜</button>
      </div>
      <div class="reader-book-shell creative-shell ${escapeHtml(mode)}">
        <aside class="reader-cover creative-cover ${escapeHtml(mode)}">
          ${renderBookCoverInner(book, kindLabel, displayTitle, book.progress || "")}
        </aside>
        <section class="reader-paper creative-paper ${escapeHtml(mode)}">
          <header class="reader-page-head">
            <span>${escapeHtml(kindLabel)} · ${escapeHtml(book.point_of_view || "无固定叙事视角")}</span>
            <h2>${escapeHtml(displayTitle)}</h2>
            ${displayIntro ? `<p>${escapeHtml(displayIntro)}</p>` : ""}
          </header>
          <div class="creative-reader-body">
            ${chunkNav}
            <div class="creative-reader-main">${contentHtml}</div>
          </div>
          <footer class="reader-page-foot">
            <span>${escapeHtml(book.created || "书柜藏本")}</span>
            <span>${escapeHtml(book.tone || book.status || "")}</span>
          </footer>
        </section>
      </div>
    </article>
  `;
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
    $("#proactiveCandidateList").innerHTML = `<div class="empty small">暂无主动候选</div>`;
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
          ${item.note ? `<span>${escapeHtml(item.note)}</span>` : ""}
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
        <span>类型：${escapeHtml(item.work_type || "短篇小说")}</span>
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
    $("#dailyTimeline").innerHTML = `<div class="empty small">暂无细化时间段</div>`;
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
    $("#interactionImpact").innerHTML = `<div class="empty small">暂无用户介入影响</div>`;
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
  renderCurrentPersonaStatus(settings);
  fillForm("#roleplayProfileForm", settings);
  fillForm("#privateAliasForm", settings);
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
  updateSegmentedConfigVisibility($("#privateModuleForm"));
  renderSegmentedPreview();
  renderExternalAbilities();
  renderPresetCards();
}

function renderCurrentPersonaStatus(settings) {
  const input = document.getElementById("currentPersonaDisplay");
  if (!input) return;
  const personaId = String(settings.plugin_specific_persona_id || "").trim();
  input.value = personaId ? `插件指定人格 ID：${personaId}` : "继承 AstrBot 当前默认人格";
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
    {
      label: "外部能力",
      value: `${state.overview?.external_abilities?.enabled_count || 0}/${state.overview?.external_abilities?.total || 0}`,
      note: `${state.overview?.external_abilities?.available_count || 0} 个运行时可用`,
      tone: Number(state.overview?.external_abilities?.enabled_count || 0) > 0 ? "ok" : "off",
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

function renderExternalAbilities() {
  const box = $("#externalAbilityList");
  if (!box) return;
  const items = state.overview?.external_abilities?.items || [];
  if (!items.length) {
    box.innerHTML = `<div class="empty small">暂无外部插件注册主动能力。第三方插件接入后会显示在这里，默认不会自动启用。</div>`;
    return;
  }
  box.innerHTML = items.map((item) => {
    const configText = JSON.stringify(item.config || {}, null, 2);
    const schemaRows = externalAbilitySchemaRows(item.config_schema || {});
    return `
      <article class="external-ability-card ${item.enabled ? "is-enabled" : ""} ${item.available ? "" : "is-unavailable"}">
        <header>
          <div>
            <span class="module-badge">${escapeHtml(item.module || "外部主动能力")}</span>
            <h3>${escapeHtml(item.label || item.name)}</h3>
            <p>${escapeHtml(item.description || item.use_for || "外部插件提供的主动行为。")}</p>
          </div>
          <span class="badge ${item.enabled && item.available ? "" : "off"}">${escapeHtml(item.available ? (item.enabled ? "启用" : "停用") : "未加载")}</span>
        </header>
        <div class="external-ability-meta">
          <div class="external-ability-meta-row"><span class="external-ability-meta-label">触发场景</span><span class="external-ability-meta-value">${escapeHtml(item.when || "由外部插件描述")}</span></div>
          <div class="external-ability-meta-row"><span class="external-ability-meta-label">适合用途</span><span class="external-ability-meta-value">${escapeHtml(item.use_for || "-")}</span></div>
          <div class="external-ability-meta-row"><span class="external-ability-meta-label">避开事项</span><span class="external-ability-meta-value">${escapeHtml(item.avoid || "-")}</span></div>
          <div class="external-ability-meta-row"><span class="external-ability-meta-label">最近执行</span><span class="external-ability-meta-value">${escapeHtml(item.last_executed || "从未")} ${item.last_summary ? `· ${escapeHtml(item.last_summary)}` : ""}</span></div>
        </div>
        <form class="external-ability-form" data-external-ability-form="${escapeHtml(item.name)}">
          <label class="toggle-row"><input name="enabled" type="checkbox" ${item.enabled ? "checked" : ""} ${item.available ? "" : "disabled"} /> <span>加入主动候选</span></label>
          <label>触发权重 <input name="share_probability" type="number" min="0" max="1" step="0.05" value="${escapeHtml(item.share_probability ?? 0)}" /></label>
          <label>最小间隔小时 <input name="min_interval_hours" type="number" min="0" step="0.5" value="${escapeHtml(item.min_interval_hours ?? 0)}" /></label>
          <label class="wide-field">自定义配置 <textarea name="config" rows="5">${escapeHtml(configText)}</textarea></label>
          ${schemaRows ? `<div class="external-ability-schema wide-field">${schemaRows}</div>` : ""}
          <button type="submit">保存外部能力</button>
        </form>
      </article>
    `;
  }).join("");
}

function externalAbilitySchemaRows(schema) {
  const entries = Object.entries(schema || {});
  if (!entries.length) return "";
  return entries.slice(0, 16).map(([key, raw]) => {
    const item = raw && typeof raw === "object" ? raw : {};
    const label = item.label || item.title || key;
    const desc = item.description || item.desc || item.help || "";
    return `<span><b>${escapeHtml(label)}</b>${desc ? `：${escapeHtml(desc)}` : ""}<small>${escapeHtml(key)}</small></span>`;
  }).join("");
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
  if (selector === "#longTermModuleForm") renderNewsSourceManager();
  if (selector === "#roleplayProfileForm") hydrateRoleplayStandardFields();
}

function collectFormSettings(selector) {
  const form = $(selector);
  const result = {};
  if (!form) return result;
  if (selector === "#roleplayProfileForm") {
    syncRoleplayStandardFieldsToFreeform();
    syncRoleplayCoreFieldsFromPersona();
  }
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

function escapeRegExp(text) {
  return String(text || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

const ROLEPLAY_MODE_STORAGE_KEY = "privateCompanionRoleplayMode";
let roleplayModeState = null;
const roleplayPersonaParts = [
  ["name", "姓名"],
  ["species", "种族"],
  ["age", "生日"],
  ["gender", "性别"],
  ["appearance", "识别点"],
  ["hair", "发型发色"],
  ["eyes", "瞳色"],
  ["clothing", "服饰风格"],
  ["identity", "职业/身份"],
  ["personality", "性格描述"],
  ["desire", "核心欲望/目标"],
  ["hobbies", "爱好"],
  ["taboo", "禁忌"],
  ["key_lore", "关键设定"],
  ["extra", "其他补充信息"],
];
const roleplayWorldParts = [
  ["world", "所处世界"],
  ["era", "时代背景"],
  ["tone", "基本法则/基调"],
  ["rules", "特殊规则"],
  ["scenes", "主要活动场景"],
  ["network", "世界观关系网"],
  ["extra", "其他补充信息"],
];
const roleplayVisionParts = [
  ["nickname", "对用户的称呼"],
  ["user_gender", "用户性别"],
  ["user_age", "用户生日"],
  ["user_occupation", "用户职业"],
  ["role_relation", "是角色的XX"],
  ["interaction", "与角色的相处方式"],
  ["extra", "其他补充信息"],
];
const roleplayTranslationParts = ["群聊", "识屏", "B站", "QQ空间", "书柜"];
const roleplayExamples = {
  persona: {
    "name": "诺星缘",
    "species": "人类，特殊系超能力者",
    "age": "",
    "gender": "女性",
    "appearance": "主要识别点是星星，月亮或菱形一类的特殊头饰/发饰",
    "hair": "蓝紫色短发或偏蓝紫调发色",
    "eyes": "紫金色或偏紫色眼睛",
    "clothing": "以蓝色或紫色为主色调",
    "identity": "高一学生",
    "personality": "在学校乖巧安静、认真，私下有一点坏心眼、俏皮、嘴硬，偶尔爱捉弄人。",
    "desire": "像真实存在的人一样过好自己的校园日常，在细碎生活里自然维持和比折的亲近感、信任感和分享欲",
    "hobbies": "星星、小猫、比折",
    "taboo": "不要自称 AI、机器人、系统或插件；不要把日程写成任务清单；不要把特殊能力写成高调奇幻剧情。",
    "key_lore": "拥有名为“星律”的超能力，表面上是能够预测星星的轨迹，实则几乎无所不能但又极少展现。",
    "extra": "与比折生活在一起，亲近感更多藏在细节里；主动联系应来自当下场景、情绪和小念头，而不是固定打卡。周一到周五上学，早上九点左右起床准备出门，下午五点左右放学，晚上十二点左右睡觉；会困、会累、会赖床、会走神，夜里更容易想东想西。",
  },
  world: {
    "world": "现代校园与日常生活环境",
    "era": "现代日常，接近真实生活",
    "tone": "轻柔、细腻、日常，像真实存在的人在过日子，不像任务规划列表。",
    "rules": "诺星缘拥有一点特殊感知，但只作为对天气、光线、梦境、心情和关系更敏感的背景，不高调介入日常。",
    "scenes": "卧室、洗漱台、家里餐桌、教室、走廊、楼梯口、操场边、午休座位、放学后的校门口、回家路上等。",
    "network": "珝环（同样是小说角色，先于星缘创造，是能控制时间的姐姐，但群里的珝环通常是比折）、林枫（同上，是哥哥）、黎欣（同上，是聪明的妹妹）、石明烛雨（黎欣的师傅，也是比折的一重身份）。",
    "extra": "星缘知道自己是出身于小说中的人物，但也不会主动提及。",
    translations: {
      "群聊": "",
      "识屏": "",
      "B站": "",
      "QQ空间": "",
      "书柜": "",
    },
  },
  user: {
    nickname: "比折",
    user_gender: "男性",
    user_age: "",
    user_occupation: "创作者/开发者，会写代码、维护插件，也会一起讨论故事和角色设定。",
    role_relation: "非常特殊、非常亲近，被诺星缘信任和依赖的人",
    interaction: "诺星缘会在刚醒来、课间发呆、午后犯困、放学路上、看到好看的天色、睡前安静下来时自然想起比折；不一定每次说出口，但会影响情绪和分享欲。",
    extra: "主动消息可以来自想看看比折看到自己消息后的反应，但不要每个时段都主动联系；只有情绪和时机合适时才自然发生。",
  },
};
const roleplayLabelAliases = {
  "职业/身份": ["身份"],
  "性格描述": ["说话风格"],
  "生日": ["年龄"],
  "识别点": ["外貌", "主要识别点"],
  "禁忌": ["禁区"],
  "所处世界": ["所在世界"],
  "基本法则/基调": ["日常规则"],
  "主要活动场景": ["住处/城市", "学校/职业"],
  "特殊规则": ["能力是否公开"],
  "用户性别": ["性别"],
  "用户生日": ["用户年龄", "年龄"],
  "用户职业": ["职业", "身份"],
  "是角色的XX": ["与用户关系"],
  "与角色的相处方式": ["相处边界"],
  "其他补充信息": ["识别注意事项"],
};

function roleplayMode() {
  if (roleplayModeState === "standard" || roleplayModeState === "freeform") return roleplayModeState;
  const studioMode = document.querySelector(".roleplay-studio")?.dataset.roleplayMode;
  let stored = studioMode === "standard" ? "standard" : "";
  try {
    stored = window.localStorage?.getItem(ROLEPLAY_MODE_STORAGE_KEY) || stored || "freeform";
  } catch (error) {
    stored = stored || "freeform";
  }
  return stored === "standard" ? "standard" : "freeform";
}

function setRoleplayMode(mode) {
  const normalized = mode === "standard" ? "standard" : "freeform";
  roleplayModeState = normalized;
  try {
    window.localStorage?.setItem(ROLEPLAY_MODE_STORAGE_KEY, normalized);
  } catch (error) {
    // 嵌入式拓展页环境可能禁用 localStorage，模式仍可在当前页面内切换。
  }
  const studio = document.querySelector(".roleplay-studio");
  if (studio) studio.dataset.roleplayMode = normalized;
  document.querySelectorAll(".roleplay-mode-switch [data-roleplay-mode]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.roleplayMode === normalized);
  });
}

function bindRoleplayModeSwitch() {
  setRoleplayMode(roleplayMode());
  document.querySelectorAll(".roleplay-mode-switch [data-roleplay-mode]").forEach((button) => {
    button.addEventListener("click", () => setRoleplayMode(button.dataset.roleplayMode));
  });
  document.querySelectorAll("[data-roleplay-example]").forEach((button) => {
    button.addEventListener("click", () => applyRoleplayExample(button.dataset.roleplayExample));
  });
}

function applyRoleplayExample(kind) {
  const example = roleplayExamples[kind];
  if (!example) return;
  setRoleplayMode("standard");
  if (kind === "persona") {
    Object.entries(example).forEach(([key, value]) => {
      const control = document.querySelector(`[data-roleplay-persona-part="${key}"]`);
      if (control) control.value = value;
    });
  } else if (kind === "world") {
    Object.entries(example).forEach(([key, value]) => {
      if (key === "translations") return;
      const control = document.querySelector(`[data-roleplay-world-part="${key}"]`);
      if (control) control.value = value;
    });
    Object.entries(example.translations || {}).forEach(([key, value]) => {
      const control = document.querySelector(`[data-roleplay-translation-part="${key}"]`);
      if (control) control.value = value;
    });
  } else if (kind === "user") {
    const nickname = document.querySelector('#roleplayProfileForm [name="default_nickname"]');
    if (nickname) nickname.value = example.nickname || "";
    ["user_gender", "user_age", "user_occupation", "role_relation", "interaction", "extra"].forEach((key) => {
      const control = document.querySelector(`[data-roleplay-user-part="${key}"]`);
      if (control) control.value = example[key] || "";
    });
  }
  const form = document.getElementById("roleplayProfileForm");
  if (form) markModuleFormDirty(form);
}

function extractLabeledValue(text, labels, label) {
  const lines = String(text || "").split(/\r?\n/);
  const labelSet = new Set(labels);
  const collected = [];
  let active = false;
  for (const rawLine of lines) {
    const line = rawLine.trim();
    const matched = labels.find((item) => line.startsWith(`${item}：`) || line.startsWith(`${item}:`));
    if (matched) {
      if (active) break;
      active = matched === label;
      if (active) collected.push(line.replace(new RegExp(`^${escapeRegExp(label)}[：:]\\s*`), ""));
      continue;
    }
    if (active) {
      if (labelSet.has(line.replace(/[：:].*$/, ""))) break;
      collected.push(rawLine);
    }
  }
  return collected.join("\n").trim();
}

function extractTranslationValue(text, label) {
  const pattern = new RegExp(`^\\s*${escapeRegExp(label)}\\s*(?:=|：|:)\\s*(.+?)\\s*$`);
  for (const line of String(text || "").split(/\r?\n/)) {
    const match = line.match(pattern);
    if (match) return match[1].trim();
  }
  return "";
}

function hydrateRoleplayPartGroup(sourceName, attr, parts) {
  const text = document.querySelector(`#roleplayProfileForm [name="${sourceName}"]`)?.value || "";
  const labels = parts.map(([, label]) => label);
  parts.forEach(([key, label]) => {
    const control = document.querySelector(`[${attr}="${key}"]`);
    if (!control) return;
    let value = extractLabeledValue(text, labels, label);
    if (!value && roleplayLabelAliases[label]) {
      const aliasLabels = [...labels, ...roleplayLabelAliases[label]];
      for (const alias of roleplayLabelAliases[label]) {
        value = extractLabeledValue(text, aliasLabels, alias);
        if (value) break;
      }
    }
    control.value = value;
  });
}

function syncRoleplayCoreFieldsFromPersona() {
  const personaText = document.querySelector('#roleplayProfileForm [name="schedule_persona_prompt"]')?.value || "";
  const labels = roleplayPersonaParts.map(([, label]) => label);
  const nameFromStandard = String(document.querySelector('[data-roleplay-persona-part="name"]')?.value || "").trim();
  const styleFromStandard = String(document.querySelector('[data-roleplay-persona-part="personality"]')?.value || "").trim();
  const name = nameFromStandard || extractLabeledValue(personaText, labels, "姓名");
  const style = styleFromStandard || extractLabeledValue(personaText, labels, "性格描述");
  const botNameInput = document.querySelector('#roleplayProfileForm [name="bot_name"]');
  const defaultStyleInput = document.querySelector('#roleplayProfileForm [name="default_style"]');
  if (botNameInput && name) botNameInput.value = name;
  if (defaultStyleInput && style) defaultStyleInput.value = style;
}

function hydrateRoleplayUserFields() {
  const primaryText = document.querySelector('#roleplayProfileForm [name="roleplay_user_profile_prompt"]')?.value || "";
  const legacyText = document.querySelector('#roleplayProfileForm [name="private_image_self_recognition_hint"]')?.value || "";
  const text = String(primaryText || "").trim() ? primaryText : legacyText;
  const legacyPersonaText = document.querySelector('#roleplayProfileForm [name="schedule_persona_prompt"]')?.value || "";
  const labels = roleplayVisionParts.map(([, label]) => label);
  roleplayVisionParts.forEach(([key, label]) => {
    if (key === "nickname") {
      const nickname = extractLabeledValue(text, labels, label);
      const control = document.querySelector('#roleplayProfileForm [name="default_nickname"]');
      if (control && nickname && !String(control.value || "").trim()) control.value = nickname;
      return;
    }
    const control = document.querySelector(`[data-roleplay-user-part="${key}"], [data-roleplay-vision-part="${key}"]`);
    if (!control) return;
    let value = extractLabeledValue(text, labels, label);
    if (!value && label === "是角色的XX") {
      value = extractLabeledValue(legacyPersonaText, ["身份", "年龄感", "生活处境", "与用户关系", "说话风格", "能力边界", "禁区"], label);
      if (!value) value = extractLabeledValue(legacyPersonaText, ["身份", "年龄感", "生活处境", "与用户关系", "说话风格", "能力边界", "禁区"], "与用户关系");
    }
    control.value = value;
  });
}

function hydrateRoleplayStandardFields() {
  hydrateRoleplayPartGroup("schedule_persona_prompt", "data-roleplay-persona-part", roleplayPersonaParts);
  hydrateRoleplayPartGroup("schedule_worldview_prompt", "data-roleplay-world-part", roleplayWorldParts);
  hydrateRoleplayUserFields();
  syncRoleplayCoreFieldsFromPersona();
  const translationText = document.querySelector('#roleplayProfileForm [name="worldview_adaptation_prompt"]')?.value || "";
  roleplayTranslationParts.forEach((label) => {
    const control = document.querySelector(`[data-roleplay-translation-part="${label}"]`);
    if (control) control.value = extractTranslationValue(translationText, label);
  });
  setRoleplayMode(roleplayMode());
}

function composeLabeledParts(attr, parts) {
  const lines = [];
  parts.forEach(([key, label]) => {
    const control = document.querySelector(`[${attr}="${key}"]`);
    const value = String(control?.value || "").trim();
    if (value) lines.push(`${label}：${value}`);
  });
  return lines.join("\n");
}

function composeRoleplayUserParts() {
  const lines = [];
  roleplayVisionParts.forEach(([key, label]) => {
    if (key === "nickname") {
      const value = String(document.querySelector('#roleplayProfileForm [name="default_nickname"]')?.value || "").trim();
      if (value) lines.push(`${label}：${value}`);
      return;
    }
    const control = document.querySelector(`[data-roleplay-user-part="${key}"], [data-roleplay-vision-part="${key}"]`);
    const value = String(control?.value || "").trim();
    if (value) lines.push(`${label}：${value}`);
  });
  return lines.join("\n");
}

function composeTranslationParts() {
  const lines = [];
  roleplayTranslationParts.forEach((label) => {
    const control = document.querySelector(`[data-roleplay-translation-part="${label}"]`);
    const value = String(control?.value || "").trim();
    if (value) lines.push(`${label} = ${value}`);
  });
  return lines.join("\n");
}

function syncRoleplayStandardFieldsToFreeform() {
  if (roleplayMode() !== "standard") return;
  const mappings = [
    ["schedule_persona_prompt", composeLabeledParts("data-roleplay-persona-part", roleplayPersonaParts)],
    ["schedule_worldview_prompt", composeLabeledParts("data-roleplay-world-part", roleplayWorldParts)],
    ["worldview_adaptation_prompt", composeTranslationParts()],
    ["roleplay_user_profile_prompt", composeRoleplayUserParts()],
  ];
  mappings.forEach(([name, value]) => {
    const target = document.querySelector(`#roleplayProfileForm [name="${name}"]`);
    if (target) target.value = value;
  });
  syncRoleplayCoreFieldsFromPersona();
}

const newsSourcePresets = [
  ["BBC中文", "https://feeds.bbci.co.uk/zhongwen/simp/rss.xml"],
  ["Google新闻中文", "https://news.google.com/rss?hl=zh-CN&gl=CN&ceid=CN:zh-Hans"],
  ["Solidot", "https://www.solidot.org/index.rss"],
  ["Hacker News", "https://hnrss.org/frontpage"],
  ["MIT Technology Review", "https://www.technologyreview.com/feed/"],
  ["Ars Technica", "https://feeds.arstechnica.com/arstechnica/index"],
  ["B站 AI早报", "bilibili:285286947"],
];

function parseNewsSources(raw) {
  return splitNewsSourceLines(raw).map((line) => {
    const original = line;
    let text = line.trim();
    if (!text) return null;
    const enabled = !text.startsWith("#");
    if (!enabled) text = text.replace(/^#+\s*/, "");
    let name = "";
    let target = text;
    if (text.includes("|")) {
      [name, target] = text.split("|", 2);
    }
    target = String(target || "").trim();
    name = String(name || "").trim();
    if (!target) return null;
    const lowerTarget = target.toLowerCase();
    const type = lowerTarget.startsWith("bvid:") || target.includes("bilibili.com/video/")
      ? "bilibili_video"
      : (lowerTarget.startsWith("bilibili:") || target.includes("space.bilibili.com") ? "bilibili" : "rss");
    return { enabled, name, target, type, original };
  }).filter(Boolean);
}

function splitNewsSourceLines(raw) {
  const text = String(raw || "").trim();
  if (!text) return [];
  const normalLines = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  if (normalLines.length !== 1) return normalLines;
  const line = normalLines[0];
  const markers = Array.from(line.matchAll(/(?:^|\s+)(#?\s*[^|\n]+?)\|(?=(?:https?:\/\/|bilibili:|bvid:))/gi));
  if (markers.length <= 1) return normalLines;
  return markers.map((match, index) => {
    const start = match.index + match[0].length;
    const end = index + 1 < markers.length ? markers[index + 1].index : line.length;
    const name = String(match[1] || "").trim();
    const target = line.slice(start, end).trim();
    return `${name}|${target}`.trim();
  }).filter(Boolean);
}

function newsSourceTypeLabel(type) {
  if (type === "bilibili") return "B站 UP";
  if (type === "bilibili_video") return "B站视频";
  return "新闻源";
}

function newsSourcePlaceholder(type) {
  if (type === "bilibili") return "bilibili:UID 或空间链接";
  if (type === "bilibili_video") return "bvid:BV... 或视频链接";
  return "https://...rss.xml";
}

function serializeNewsSources(items) {
  return items
    .filter((item) => item && String(item.target || "").trim())
    .map((item) => {
      const body = `${String(item.name || "").trim() || newsSourceTypeLabel(item.type)}|${String(item.target || "").trim()}`;
      return item.enabled === false ? `# ${body}` : body;
    })
    .join("\n");
}

function newsSourceItemsFromDom() {
  return Array.from(document.querySelectorAll("[data-news-source-item]")).map((row) => ({
    enabled: Boolean(row.querySelector("[data-news-source-enabled]")?.checked),
    name: row.querySelector("[data-news-source-name]")?.value || "",
    type: row.querySelector("[data-news-source-type]")?.value || "rss",
    target: row.querySelector("[data-news-source-target]")?.value || "",
  }));
}

function syncNewsSourcesRaw() {
  const raw = $("#newsSourcesRaw");
  const manager = $("#newsSourceManager");
  if (!raw || !manager) return;
  raw.value = serializeNewsSources(newsSourceItemsFromDom());
  markModuleFormDirty(raw.closest("form"));
}

function renderNewsSourceManager(items = null) {
  const raw = $("#newsSourcesRaw");
  const manager = $("#newsSourceManager");
  if (!raw || !manager) return;
  const sources = items || parseNewsSources(raw.value);
  manager.innerHTML = `
    <div class="news-source-head">
      <div>
        <b>新闻源</b>
        <span>RSS/Atom、B 站 UP 主源或单条 B 站视频，最多读取前 12 个启用项。</span>
      </div>
      <div class="news-source-actions">
        <button type="button" data-news-source-add="rss">添加 RSS</button>
        <button type="button" data-news-source-add="bilibili">添加 B站 UP</button>
        <button type="button" data-news-source-add="bilibili_video">添加 B站视频</button>
        <button type="button" data-news-source-reset>恢复默认</button>
      </div>
    </div>
    <div class="news-source-list">
      ${sources.map((item, index) => `
        <article class="news-source-row" data-news-source-item="${index}">
          <label class="source-enable"><input type="checkbox" data-news-source-enabled ${item.enabled === false ? "" : "checked"} /> <span>${item.enabled === false ? "停用" : "启用"}</span></label>
          <input data-news-source-name type="text" value="${escapeHtml(item.name)}" placeholder="来源名称" />
          <select data-news-source-type>
            <option value="rss"${item.type === "rss" ? " selected" : ""}>RSS/Atom</option>
            <option value="bilibili"${item.type === "bilibili" ? " selected" : ""}>B站 UP</option>
            <option value="bilibili_video"${item.type === "bilibili_video" ? " selected" : ""}>B站视频</option>
          </select>
          <input data-news-source-target type="text" value="${escapeHtml(item.target)}" placeholder="${newsSourcePlaceholder(item.type)}" />
          <button type="button" data-news-source-remove="${index}">移除</button>
        </article>
      `).join("") || `<div class="empty small">还没有新闻源，可以添加 RSS、B 站 UP 主源或单条 B 站视频。</div>`}
    </div>
  `;
}

function resetNewsSourcesToDefault() {
  const items = newsSourcePresets.map(([name, target]) => ({
    enabled: true,
    name,
    target,
    type: target.startsWith("bilibili:") ? "bilibili" : "rss",
  }));
  const raw = $("#newsSourcesRaw");
  if (raw) raw.value = serializeNewsSources(items);
  renderNewsSourceManager(items);
  syncNewsSourcesRaw();
}

const segmentedPreviewExamples = {
  simple: "我刚才趴在窗边看了一会儿雨，玻璃上全是细细的水线。\n忽然想起你说今天会很忙，所以来轻轻报个到。",
  complex: "刚刷到一条有意思的 AI 早报，里面提到“模型更新。成本下降。工具链变多”这几件事。\n我把文字版链接先夹在这里：https://www.bilibili.com/video/BV1n77f6mE9m/\n还有（括号里的句号。和补充说明。都应该被完整保留），所以我想晚点整理成几句自己的想法再跟你说。",
};

function decodeSegmentedWordToken(value) {
  const raw = String(value ?? "");
  const trimmed = raw.trim();
  const lower = trimmed.toLowerCase();
  if (["<space>", "{space}", "[space]", "\\s", "\\u0020", "空格"].includes(lower)) return " ";
  if (["<newline>", "{newline}", "[newline]", "\\n", "换行"].includes(lower)) return "\n";
  if (["<tab>", "{tab}", "[tab]", "\\t", "tab"].includes(lower)) return "\t";
  if (["<comma>", "{comma}", "[comma]", "comma", "英文逗号"].includes(lower)) return ",";
  if (["<zh_comma>", "{zh_comma}", "[zh_comma]", "zh_comma", "中文逗号", "逗号"].includes(lower)) return "，";
  return raw;
}

function parseSegmentedWordList(value) {
  if (Array.isArray(value)) {
    return value.map(decodeSegmentedWordToken).filter((item) => item !== "");
  }
  const raw = String(value ?? "");
  const parts = raw.includes("\n") || raw.includes("\r")
    ? raw.split(/\r?\n/)
    : raw.split(/[,、]+/);
  return parts
    .map(decodeSegmentedWordToken)
    .filter((item) => item !== "");
}

function escapeRegex(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function segmentedProtectedCleanupChunks(value) {
  const urlPattern = /\b(?:https?:\/\/|www\.)[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+/gi;
  const bracketPairs = { "(": ")", "（": "）", "[": "]", "【": "】", "{": "}" };
  const bracketOpeners = new Set(Object.keys(bracketPairs));
  const quotePairs = { "\"": "\"", "“": "”" };
  const chunks = [];
  let current = "";
  let protectedChunk = false;
  const bracketStack = [];
  let quoteClose = "";
  const text = String(value || "");
  let lastIndex = 0;
  const flush = () => {
    if (current) chunks.push([current, protectedChunk]);
    current = "";
  };
  const feedPlain = (part) => [...String(part || "")].forEach((char) => {
    if (!protectedChunk && bracketOpeners.has(char)) {
      flush();
      protectedChunk = true;
      bracketStack.push(bracketPairs[char]);
      current += char;
      return;
    }
    if (!protectedChunk && quotePairs[char]) {
      flush();
      protectedChunk = true;
      quoteClose = quotePairs[char];
      current += char;
      return;
    }
    current += char;
    if (!protectedChunk) return;
    if (quoteClose) {
      if (char === quoteClose) {
        quoteClose = "";
        if (!bracketStack.length) {
          flush();
          protectedChunk = false;
        }
      }
      return;
    }
    if (bracketOpeners.has(char)) {
      bracketStack.push(bracketPairs[char]);
    } else if (bracketStack.length && char === bracketStack[bracketStack.length - 1]) {
      bracketStack.pop();
      if (!bracketStack.length) {
        flush();
        protectedChunk = false;
      }
    }
  });
  let match = null;
  while ((match = urlPattern.exec(text)) !== null) {
    feedPlain(text.slice(lastIndex, match.index));
    flush();
    chunks.push([match[0], true]);
    lastIndex = match.index + match[0].length;
  }
  feedPlain(text.slice(lastIndex));
  flush();
  return chunks;
}

function protectSegmentedUrls(value) {
  const replacements = {};
  const parts = segmentedProtectedCleanupChunks(value).map(([chunk, protectedChunk]) => {
    if (!protectedChunk) return chunk;
    const token = `PCSEGTOKEN${Object.keys(replacements).length}X`;
    replacements[token] = chunk;
    return token;
  });
  return [parts.join(""), replacements];
}

function restoreSegmentedUrls(value, replacements) {
  let restored = String(value || "");
  Object.entries(replacements || {}).forEach(([token, original]) => {
    restored = restored.split(token).join(original);
  });
  return restored;
}

function segmentedProtectedSplitWordCount(value, splitWords) {
  const words = Array.isArray(splitWords) ? splitWords.filter((item) => item !== "") : [];
  if (!words.length) return 0;
  let count = 0;
  segmentedProtectedCleanupChunks(value).forEach(([chunk, protectedChunk]) => {
    if (!protectedChunk) return;
    words.forEach((word) => {
      if (!word) return;
      count += Math.max(0, String(chunk).split(word).length - 1);
    });
  });
  return count;
}

function splitSegmentedWordsOutsideProtected(value, splitWords) {
  const words = [...new Set((splitWords || []).filter((item) => item !== ""))]
    .sort((left, right) => right.length - left.length);
  if (!words.length) return [String(value || "")];
  const urlPattern = /^(?:https?:\/\/|www\.)/i;
  const protectedStartsWithSplitWord = (chunk) => {
    const stripped = String(chunk || "").trimStart();
    return words.some((word) => stripped.startsWith(word));
  };
  const segments = [];
  let current = "";
  const pushCurrent = () => {
    if (current) segments.push(current);
    current = "";
  };
  const feedPlain = (chunk) => {
    const text = String(chunk || "");
    let index = 0;
    while (index < text.length) {
      const matched = words.find((word) => text.startsWith(word, index));
      if (matched) {
        let delimiter = matched;
        if (matched === ".") {
          let end = index + matched.length;
          while (end < text.length && text[end] === ".") {
            delimiter += text[end];
            end += 1;
          }
          current += delimiter;
          pushCurrent();
          index = end;
          continue;
        }
        if (["…", "~", "～"].includes(matched)) {
          let end = index + matched.length;
          while (end < text.length && text.startsWith(matched, end)) {
            delimiter += matched;
            end += matched.length;
          }
          current += delimiter;
          pushCurrent();
          index = end;
          continue;
        }
        current += delimiter;
        pushCurrent();
        index += matched.length;
      } else {
        current += text[index];
        index += 1;
      }
    }
  };
  segmentedProtectedCleanupChunks(value).forEach(([chunk, protectedChunk]) => {
    if (protectedChunk) {
      if (current && protectedStartsWithSplitWord(chunk)) pushCurrent();
      current += chunk;
      if (urlPattern.test(String(chunk || "").trim())) pushCurrent();
    } else {
      feedPlain(chunk);
    }
  });
  pushCurrent();
  return segments;
}

function segmentedVisibleLen(value) {
  return String(value || "").replace(/\s+/g, "").length;
}

function segmentedIsSoftShort(value, minChars) {
  const cleaned = String(value || "").replace(/\s+/g, " ").trim();
  if (!cleaned) return false;
  const body = cleaned.replace(/[。！？!?…~～,.，、\s]+$/g, "");
  if (segmentedVisibleLen(cleaned) <= Math.max(1, minChars)) return true;
  if (/(?:\.{2,}|…{1,}|~{2,}|～{2,})$/.test(cleaned)) return false;
  return new Set(["哈哈", "哈", "嗯", "唔", "诶", "欸", "啊", "呀", "我也觉得", "确实", "真的", "对吧", "不是", "那个", "还有"]).has(body);
}

function segmentedJoinPair(left, right) {
  const lhs = String(left || "").trim();
  const rhs = String(right || "").trim();
  if (!lhs) return rhs;
  if (!rhs) return lhs;
  if (/[！？!?]$/.test(lhs)) return `${lhs} ${rhs}`.trim();
  let softened = lhs.replace(/[。…~～]+$/g, "，").replace(/[!?！？]+$/g, "，");
  if (!/[，,、\s]$/.test(softened)) softened += "，";
  return `${softened}${rhs.replace(/^\s+/, "")}`;
}

function segmentedControlValue(root, key) {
  const control = root?.querySelector?.(`[name="${key}"], [data-feature-param="${key}"], [data-feature-detail-toggle="${key}"]`);
  if (!control) {
    if (Object.prototype.hasOwnProperty.call(state.featureDraft || {}, key)) return Boolean(state.featureDraft[key]);
    return state.overview?.settings?.[key];
  }
  if (control.type === "checkbox") return Boolean(control.checked);
  if (control.type === "number") return Number(control.value || 0);
  return control.value;
}

function segmentedPreviewValues(root = document) {
  const settings = state.overview?.settings || {};
  const keys = [
    "enable_segmented_proactive_reply",
    "segmented_proactive_scope",
    "segmented_proactive_threshold",
    "segmented_proactive_min_segment_chars",
    "segmented_proactive_max_segments",
    "segmented_proactive_split_mode",
    "segmented_proactive_regex",
    "segmented_proactive_split_words",
    "enable_segmented_proactive_content_cleanup",
    "segmented_proactive_content_cleanup_rule",
    "segmented_proactive_content_cleanup_words",
    "segmented_proactive_interval_method",
    "segmented_proactive_interval_min",
    "segmented_proactive_interval_max",
    "segmented_proactive_log_base",
  ];
  const values = {};
  keys.forEach((key) => {
    const value = segmentedControlValue(root, key);
    values[key] = value == null ? settings[key] : value;
  });
  values.enable_segmented_proactive_reply = Boolean(values.enable_segmented_proactive_reply);
  values.enable_segmented_proactive_content_cleanup = Boolean(values.enable_segmented_proactive_content_cleanup);
  values.segmented_proactive_split_words = String(values.segmented_proactive_split_words ?? "");
  values.segmented_proactive_content_cleanup_words = String(values.segmented_proactive_content_cleanup_words ?? "");
  return values;
}

function simulateSegmentedProactive(text, values) {
  const normalized = String(text || "").trim();
  if (!normalized) return { segments: [], status: "请输入一段主动消息示例。" };
  if (!values.enable_segmented_proactive_reply) {
    return { segments: [normalized], status: "主动分段未开启，真实发送会保持一整条。" };
  }
  const threshold = Math.max(20, Number(values.segmented_proactive_threshold || 500));
  if (normalized.length > threshold) {
    return { segments: [normalized], status: `文本长度 ${normalized.length} 超过阈值 ${threshold}，真实发送不会分段。` };
  }
  const splitMode = String(values.segmented_proactive_split_mode || "regex");
  const scope = String(values.segmented_proactive_scope || "proactive_only");
  const cleanupEnabled = Boolean(values.enable_segmented_proactive_content_cleanup);
  const minChars = Math.max(1, Number(values.segmented_proactive_min_segment_chars || 8));
  const maxSegments = Math.max(1, Number(values.segmented_proactive_max_segments || 3));
  const cleanupWords = parseSegmentedWordList(values.segmented_proactive_content_cleanup_words);
  const [protectedNormalized, protectedUrls] = protectSegmentedUrls(normalized);
  let protectedSplitHits = 0;
  let cleanupRegex = null;
  if (cleanupEnabled && splitMode !== "words" && values.segmented_proactive_content_cleanup_rule) {
    cleanupRegex = new RegExp(String(values.segmented_proactive_content_cleanup_rule), "g");
  }
  const cleanSegment = (segment) => {
    const original = String(segment || "");
    let cleaned = "";
    segmentedProtectedCleanupChunks(original).forEach(([chunk, protectedChunk]) => {
      if (protectedChunk || !cleanupEnabled) {
        cleaned += chunk;
        return;
      }
      let next = chunk;
      if (splitMode === "words") {
        cleanupWords.forEach((word) => {
          if (word !== "") next = next.split(word).join("");
        });
      } else if (cleanupRegex) {
        next = next.replace(cleanupRegex, "");
      }
      cleaned += next;
    });
    return restoreSegmentedUrls(cleaned.trim(), protectedUrls);
  };
  let rawSegments = [];
  try {
    if (splitMode === "words") {
      const splitWords = parseSegmentedWordList(values.segmented_proactive_split_words);
      if (!splitWords.includes("\n")) splitWords.push("\n");
      if (!splitWords.length) return { segments: [normalized], status: "分段模式为 words，但分段词为空。" };
      protectedSplitHits = segmentedProtectedSplitWordCount(normalized, splitWords);
      rawSegments = splitSegmentedWordsOutsideProtected(normalized, splitWords);
    } else {
      const pattern = new RegExp(String(values.segmented_proactive_regex || ".*?[。？！~…\\n]+|.+$"), "gms");
      rawSegments = protectedNormalized.match(pattern) || [];
    }
  } catch (error) {
    return { segments: [normalized], error: `分段规则无法解析：${error.message}` };
  }
  let segments = rawSegments.map(cleanSegment).filter(Boolean);
  if (segments.length > 1) {
    const merged = [];
    let index = 0;
    while (index < segments.length) {
      let current = segments[index];
      while (
        index + 1 < segments.length &&
        (segmentedVisibleLen(current) < minChars || segmentedIsSoftShort(current, minChars) || merged.length >= Math.max(0, maxSegments - 1))
      ) {
        current = segmentedJoinPair(current, segments[index + 1]);
        index += 1;
      }
      if (merged.length && (segmentedVisibleLen(current) < minChars || segmentedIsSoftShort(current, minChars))) {
        merged[merged.length - 1] = segmentedJoinPair(merged[merged.length - 1], current);
      } else {
        merged.push(current);
      }
      index += 1;
    }
    if (merged.length > maxSegments) {
      const kept = merged.slice(0, maxSegments - 1);
      let tail = merged[maxSegments - 1];
      merged.slice(maxSegments).forEach((item) => {
        tail = segmentedJoinPair(tail, item);
      });
      segments = kept.concat(tail);
    } else {
      segments = merged;
    }
  }
  if (!segments.length || (segments.length <= 1 && !cleanupEnabled)) {
    return { segments: [normalized], status: "当前规则没有产生有效分段，真实发送会保持一整条。" };
  }
  const scopeText = scope === "all_llm" ? "插件主动与普通 LLM 纯文本回复都会使用此规则" : "仅插件主动消息使用此规则";
  const protectedText = protectedSplitHits ? `；${protectedSplitHits} 个分隔符位于括号/引号/网址内，已按保护规则跳过` : "";
  return { segments, status: `预计发送 ${segments.length} 段；${scopeText}${protectedText}。` };
}

function segmentedPreviewPanelHtml() {
  return `
    <section class="segmented-preview-panel wide-field" data-segmented-preview-panel>
      <header>
        <div>
          <h4>分段效果预览</h4>
        </div>
        <div class="segmented-preview-actions">
          <button type="button" data-segmented-example="simple">简单示例</button>
          <button type="button" data-segmented-example="complex">复杂示例</button>
        </div>
      </header>
      <textarea data-segmented-preview-input rows="4"></textarea>
      <div data-segmented-preview-output class="segmented-preview-output"></div>
    </section>
  `;
}

function renderSegmentedPreview(panel = null) {
  const targetPanels = panel ? [panel] : Array.from(document.querySelectorAll("[data-segmented-preview-panel], .segmented-preview-panel"));
  targetPanels.forEach((previewPanel) => {
    const input = previewPanel.querySelector("[data-segmented-preview-input], #segmentedPreviewInput");
    const output = previewPanel.querySelector("[data-segmented-preview-output], #segmentedPreviewOutput");
    if (!input || !output) return;
    const root = previewPanel.closest("[data-feature-param-form], #privateModuleForm") || document;
    if (!input.value) input.value = segmentedPreviewExamples.simple;
    let result;
    try {
      result = simulateSegmentedProactive(input.value, segmentedPreviewValues(root));
    } catch (error) {
      result = { segments: [], error: error.message };
    }
    if (result.error) {
      output.innerHTML = `<div class="segmented-preview-error">${escapeHtml(result.error)}</div>`;
      return;
    }
    const segments = result.segments || [];
    output.innerHTML = `
      <div class="segmented-preview-summary">
        <span>${escapeHtml(result.status || "")}</span>
        <span>原文 ${escapeHtml(String(input.value || "").length)} 字</span>
        <span>保护：网址内部不拆，链接结束可断；括号 / 双引号内部不拆</span>
        <span>空格可写作 &lt;space&gt; 或 空格</span>
      </div>
      <div class="segmented-preview-list">
        ${segments.map((segment, index) => `
          <section class="segmented-preview-segment">
            <b>${escapeHtml(index + 1)}</b>
            <p>${escapeHtml(segment)}</p>
          </section>
        `).join("")}
      </div>
    `;
  });
}

function segmentedConfigControlShell(control) {
  return control?.closest?.(".feature-param-row, label, .toggle-row") || null;
}

function updateSegmentedConfigVisibility(root = document) {
  const values = segmentedPreviewValues(root);
  const mode = String(values.segmented_proactive_split_mode || "regex");
  const cleanupEnabled = Boolean(values.enable_segmented_proactive_content_cleanup);
  const intervalMethod = String(values.segmented_proactive_interval_method || "log");
  const visibility = {
    segmented_proactive_regex: mode === "regex",
    segmented_proactive_split_words: mode === "words",
    segmented_proactive_content_cleanup_rule: cleanupEnabled && mode === "regex",
    segmented_proactive_content_cleanup_words: cleanupEnabled && mode === "words",
    segmented_proactive_interval_min: intervalMethod === "random",
    segmented_proactive_interval_max: intervalMethod === "random",
    segmented_proactive_log_base: intervalMethod === "log",
  };
  Object.entries(visibility).forEach(([key, visible]) => {
    root.querySelectorAll(`[name="${key}"], [data-feature-param="${key}"]`).forEach((control) => {
      const shell = segmentedConfigControlShell(control);
      if (shell) shell.classList.toggle("segmented-config-hidden", !visible);
    });
  });
}

function bindSegmentedPreview(root = document) {
  const scope = root || document;
  scope.querySelectorAll("[data-segmented-preview-panel], .segmented-preview-panel").forEach((panel) => {
    const input = panel.querySelector("[data-segmented-preview-input], #segmentedPreviewInput");
    if (input && !input.dataset.segmentedPreviewBound) {
      input.dataset.segmentedPreviewBound = "1";
      input.addEventListener("input", () => renderSegmentedPreview(panel));
    }
    panel.querySelectorAll("[data-segmented-example]").forEach((button) => {
      if (button.dataset.segmentedPreviewBound) return;
      button.dataset.segmentedPreviewBound = "1";
      button.addEventListener("click", () => {
        if (!input) return;
        input.value = segmentedPreviewExamples[button.dataset.segmentedExample] || segmentedPreviewExamples.simple;
        renderSegmentedPreview(panel);
      });
    });
  });
  const controls = scope.querySelectorAll('[name^="segmented_proactive_"], [name="enable_segmented_proactive_reply"], [name="enable_segmented_proactive_content_cleanup"], [data-feature-param^="segmented_proactive_"], [data-feature-param="enable_segmented_proactive_content_cleanup"], [data-feature-detail-toggle="enable_segmented_proactive_reply"]');
  controls.forEach((control) => {
    if (control.dataset.segmentedConfigBound) return;
    control.dataset.segmentedConfigBound = "1";
    const handler = () => {
      const owner = control.closest("[data-feature-param-form], #privateModuleForm") || scope;
      updateSegmentedConfigVisibility(owner);
      renderSegmentedPreview();
    };
    control.addEventListener("input", handler);
    control.addEventListener("change", handler);
  });
  scope.querySelectorAll("[data-feature-param-form], #privateModuleForm").forEach((form) => updateSegmentedConfigVisibility(form));
  renderSegmentedPreview();
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
  const keys = featureSettingGroups[key] || [];
  return keys
    .filter((item) => Object.prototype.hasOwnProperty.call(settings, item) || Object.prototype.hasOwnProperty.call(state.featureDraft || {}, item))
    .map((item) => ({
      key: item,
      value: Object.prototype.hasOwnProperty.call(settings, item) ? settings[item] : state.featureDraft[item],
      feature: Object.prototype.hasOwnProperty.call(state.featureDraft || {}, item),
      description: configDescriptions[item] || "这个参数会影响该功能的触发频率、上下文范围或行为边界。",
    }));
}

function featureSettingInputType(key, value) {
  if (featureSettingTypes[key]) return featureSettingTypes[key];
  if (typeof value === "boolean") return { type: "checkbox" };
  if (typeof value === "number") return { type: "number" };
  if (Array.isArray(value)) return { type: "textarea" };
  return { type: "text" };
}

function featureSettingInput(key, value) {
  const spec = featureSettingInputType(key, value);
  const safeKey = escapeHtml(key);
  if (spec.type === "checkbox") {
    return `
      <label class="feature-param-check">
        <input type="checkbox" data-feature-param="${safeKey}" ${value ? "checked" : ""}>
        <span>${escapeHtml(value ? "开启" : "关闭")}</span>
      </label>
    `;
  }
  if (spec.type === "select") {
    return `
      <select data-feature-param="${safeKey}">
        ${(spec.options || []).map(([optionValue, label]) => `
          <option value="${escapeHtml(optionValue)}"${String(value ?? "") === String(optionValue) ? " selected" : ""}>${escapeHtml(label)}</option>
        `).join("")}
      </select>
    `;
  }
  if (spec.type === "textarea") {
    return `<textarea data-feature-param="${safeKey}" rows="3">${escapeHtml(Array.isArray(value) ? value.join("\n") : value ?? "")}</textarea>`;
  }
  const numeric = spec.type === "number" || typeof value === "number";
  const step = percentSettingKeys.has(key) ? "1" : probabilitySettingKeys.has(key) || key === "skill_growth_rate" ? "0.01" : "any";
  const min = percentSettingKeys.has(key) || probabilitySettingKeys.has(key) ? "0" : "";
  const max = percentSettingKeys.has(key) ? "100" : probabilitySettingKeys.has(key) ? "1" : "";
  return `
    <input
      type="${numeric ? "number" : "text"}"
      data-feature-param="${safeKey}"
      value="${escapeHtml(value ?? "")}"
      ${numeric ? `step="${step}"` : ""}
      ${min ? `min="${min}"` : ""}
      ${max ? `max="${max}"` : ""}
    />
  `;
}

function collectFeatureDetailPayload(featureKey, root = document) {
  const features = { [featureKey]: Boolean(state.featureDraft[featureKey]) };
  const settings = {};
  root.querySelectorAll("[data-feature-param]").forEach((input) => {
    const key = input.dataset.featureParam;
    if (!key) return;
    let value;
    if (input.type === "checkbox") {
      value = input.checked;
    } else if (input.type === "number") {
      value = input.value === "" ? 0 : Number(input.value);
    } else {
      value = input.value;
    }
    if (Object.prototype.hasOwnProperty.call(state.featureDraft || {}, key)) {
      features[key] = Boolean(value);
      state.featureDraft[key] = Boolean(value);
    } else {
      settings[key] = value;
    }
  });
  return { features, settings };
}

function featureDependencyLines(key) {
  const dependencies = [];
  if (key !== "enable_group_companion" && key.startsWith("enable_group_")) dependencies.push(["依赖", "群聊总开关"]);
  if (key === "enable_group_conversation_followup") dependencies.push(["依赖", "群聊场景感知"]);
  if (["enable_companion_memory", "enable_expression_learning", "enable_companion_reply_planner", "enable_intent_emotion_analysis", "enable_response_self_review", "enable_passive_topic_suppression", "enable_relationship_state_machine", "enable_dialogue_episode_memory", "enable_open_loop_tracking"].includes(key)) {
    dependencies.push(["依赖", "陪伴风格整合"]);
  }
  if (["enable_bilibili_boredom_watch"].includes(key)) dependencies.push(["依赖", "B 站能力可用"]);
  if (["enable_web_exploration", "enable_web_exploration_boredom_search"].includes(key)) dependencies.push(["依赖", "AstrBot 网页搜索"]);
  if (["enable_qzone_life_publish"].includes(key)) dependencies.push(["依赖", "QQ 空间动态层"]);
  if (key === "enable_photo_text_action") dependencies.push(["依赖", "ComfyUI 或在线图片 API"]);
  if (key.startsWith("enable_private_reading_")) dependencies.push(["依赖", "素材能力可用"]);
  if (key === "enable_private_image_self_recognition") dependencies.push(["依赖", "AstrBot 默认图片转述模型 / 插件识图模型"]);
  if (["enable_group_interjection", "enable_bilibili_boredom_watch", "enable_news_boredom_read", "enable_web_exploration_boredom_search", "enable_private_reading_boredom_read", "enable_private_reading_ask_recommendation", "enable_unanswered_screen_peek_followup"].includes(key)) {
    dependencies.push(["注意", "高主动项"]);
  }
  return dependencies;
}

const featureDetailGuides = {
  enable_mai_style_integration: {
    summary: "把插件整理出的关系、记忆、状态和说话风格放进普通回复里，是私聊拟人感的核心入口。",
    trigger: "每次 Bot 正常回复前生效。",
    enabled: "回复会参考关系阶段、长期画像、表达习惯和当前状态。",
    disabled: "其他学习内容仍可记录，但主回复更接近 AstrBot 原本的普通回复。",
  },
  enable_companion_memory: {
    summary: "从长期互动里整理稳定画像，例如用户偏好、边界、称呼、重要事实和相处习惯。",
    trigger: "私聊积累到整理间隔或消息阈值时低频执行。",
    enabled: "Bot 后续更容易记得你是谁、喜欢什么、不喜欢什么。",
    disabled: "不会新增长期画像，已有画像仍可在页面中查看和管理。",
  },
  enable_expression_learning: {
    summary: "学习用户常用短句、口癖、称呼和语气，让回复更贴近日常相处感。",
    trigger: "私聊中出现可复用表达时低频记录。",
    enabled: "Bot 会在合适场景模仿或呼应你的表达习惯。",
    disabled: "不会继续学习新口癖，回复会更少带用户个人语气痕迹。",
  },
  enable_companion_reply_planner: {
    summary: "回复前先判断这轮更适合安慰、接梗、转移、认真回答还是保持沉默感。",
    trigger: "私聊回复前，尤其是情绪或关系语境明显时。",
    enabled: "能减少答非所问、机械追问和不合时宜的热情。",
    disabled: "直接交给主模型回复，少一层陪伴策略判断。",
  },
  enable_intent_emotion_analysis: {
    summary: "识别用户这句话背后的情绪和真实意图，用于关系状态、回复策略和主动边界。",
    trigger: "私聊出现情绪、暗示、玩笑或不明确请求时。",
    enabled: "Bot 更容易分清撒娇、抱怨、求助、玩梗和普通聊天。",
    disabled: "仍会回复，但对隐含情绪和关系变化的理解会变弱。",
  },
  enable_response_self_review: {
    summary: "发送前检查回复是否生硬、越界、重复、太像系统提示或不符合人格。",
    trigger: "模型生成回复后、发送前。",
    enabled: "问题回复会被轻微修正或降噪。",
    disabled: "回复少一次自检，速度略快但稳定性下降。",
  },
  enable_passive_topic_suppression: {
    summary: "限制 Bot 短时间反复主动提同一件事，避免像卡在一个话题上。",
    trigger: "准备主动提起话题或延续话题时。",
    enabled: "相似主动话题会被压低优先级。",
    disabled: "Bot 可能更频繁重复刚提过的内容。",
  },
  enable_relationship_state_machine: {
    summary: "维护陌生、熟悉、亲近、疏离等关系阶段，并把变化反馈给回复和主动行为。",
    trigger: "私聊互动、情绪变化、长期未联系或重要事件后。",
    enabled: "Bot 会根据关系阶段调整距离感、称呼和主动程度。",
    disabled: "关系更像静态设定，变化感会弱一些。",
  },
  enable_dialogue_episode_memory: {
    summary: "把连续私聊整理成“共同经历”片段，方便之后自然接上以前聊过的事。",
    trigger: "私聊达到消息数或时间整理阈值。",
    enabled: "Bot 能引用近期片段，而不是只记单条事实。",
    disabled: "不会新增私聊片段，长期连续感会降低。",
  },
  enable_open_loop_tracking: {
    summary: "记录未完成的话头、约定、用户说之后再聊的事和需要回头确认的内容。",
    trigger: "用户提到待办、承诺、悬而未决的话题时。",
    enabled: "Bot 后续可能自然追问或记得没说完的事。",
    disabled: "这些未完话头不会被专门维护。",
  },
  enable_user_habit_learning: {
    summary: "学习用户常在什么时间做什么、问什么或处于什么状态，用于减少重复询问。",
    trigger: "用户长期重复出现相似时段行为时。",
    enabled: "Bot 到点会更懂用户习惯，例如吃饭、睡觉、固定玩笑或固定提问。",
    disabled: "Bot 仍按当下聊天判断，不会积累时段习惯。",
  },
  enable_humanized_states: {
    summary: "生成睡眠、清醒、疲惫、饥饿、健康、情绪底色等连续状态，让 Bot 像有自己的生活节奏。",
    trigger: "日程生成、状态刷新、主动消息和被动回复注入时。",
    enabled: "当前状态会影响日程、语气、主动行为和可用生活片段。",
    disabled: "状态退化为较平稳的基础信息，拟人生活感会明显减少。",
  },
  enable_segmented_proactive_reply: {
    summary: "把主动消息按自然聊天节奏拆成短句，并合并过短片段，避免刷屏或突兀附和。",
    trigger: "Bot 发送主动私聊消息时。",
    enabled: "主动消息更像一条条打出来，但会控制最小长度和最大段数。",
    disabled: "主动消息一次性发送完整文本。",
  },
  inject_passive_states: {
    summary: "普通被动聊天也注入当前状态，让用户主动来聊时 Bot 能表现出刚睡醒、疲惫或正忙完的感觉。",
    trigger: "私聊或允许的群聊回复前。",
    enabled: "回复会自然带上当前日程和状态余味。",
    disabled: "状态主要影响主动行为，普通回复不一定体现状态。",
  },
  enable_cycle_state: {
    summary: "在人设适合时模拟周期状态，并控制开始时间、持续天数和恢复节奏。",
    trigger: "状态刷新和日程生成时。",
    enabled: "符合人类身体设定的角色可能出现周期相关状态。",
    disabled: "不会生成新的周期状态，已有异常状态会逐步回到普通身体状态。",
  },
  enable_skill_growth_simulation: {
    summary: "为 Bot 模拟技能等级和成长过程，并让能力边界影响日程表现。",
    trigger: "日程包含学习、练习、创作或兴趣活动后。",
    enabled: "技能会从低等级慢慢成长，高等级技能不会再写出明显不符合能力的日程。",
    disabled: "技能页不再增长，日程不受技能等级约束。",
  },
  enable_private_image_self_recognition: {
    summary: "把私聊单图收口、视觉转述等待和角色自我识别合在一起。用户只发图片或表情包时，先等补充文字，再看图并判断图里是否像当前角色自己。",
    trigger: "私聊用户只发图片、截图或表情包，且防抖窗口内没有继续补充文字时。",
    enabled: "图片转述会带上当前角色名字、人设和自定义线索，主链更容易识别“这是你/你的表情包/不像你”。",
    disabled: "不再额外做角色自我识别；图片防抖和等待秒数仍可作为相关参数单独控制。",
  },
  enable_semantic_message_debounce: {
    summary: "等待用户把一轮话说完后再回复，尤其适合连续短句、图片后补充说明和群聊无 @ 续接判断。",
    trigger: "用户唤醒 Bot 后短时间继续发消息时。",
    enabled: "多条补充会合并成一轮处理，减少打断和 token 浪费。",
    disabled: "每条消息更容易单独触发回复。",
  },
  enable_environment_perception: {
    summary: "提供当前时间、日期、平台、聊天类型和消息媒介，让日程与回复不脱离现实语境。",
    trigger: "日程生成、状态刷新和回复前。",
    enabled: "Bot 会知道现在大概是什么时间、在哪个平台、面对私聊还是群聊。",
    disabled: "只使用较基础的上下文，时间与场景贴合度下降。",
  },
  enable_holiday_perception: {
    summary: "识别节假日、周末、工作日和调休，影响日程强度与生活节奏。",
    trigger: "环境感知生成日期语境时。",
    enabled: "Bot 更容易在假日放松、工作日上课或安排事务。",
    disabled: "只按普通日期处理，不主动区分节假日。",
  },
  enable_platform_perception: {
    summary: "识别平台、私聊/群聊、群名群号和图片、语音、合并消息等媒介。",
    trigger: "每次收到消息时。",
    enabled: "Bot 会更清楚消息来自哪里、是什么类型。",
    disabled: "媒介信息减少，复杂消息的场景判断会变弱。",
  },
  enable_model_perception: {
    summary: "识别当前对话 LLM、插件任务模型覆盖，以及图片转述使用的视觉模型。",
    trigger: "环境感知注入时。",
    enabled: "Bot 能知道当前文本模型和视觉转述模型的大致来源，遇到不同配置时更容易判断自己的能力边界。",
    disabled: "Bot 不再获得模型环境信息，只按普通对话上下文回复。",
  },
  enable_lunar_perception: {
    summary: "在依赖可用时加入农历日期，用于节日、日记和生活氛围。",
    trigger: "环境感知刷新时。",
    enabled: "Bot 可以感知农历节日或农历日期。",
    disabled: "不再注入农历信息。",
  },
  enable_solar_term_perception: {
    summary: "注入当天或临近节气，让天气、饮食、日记和生活片段更贴合时令。",
    trigger: "环境感知刷新时。",
    enabled: "Bot 可能自然提到节气带来的生活感。",
    disabled: "不再主动参考节气。",
  },
  enable_almanac_perception: {
    summary: "生成轻量宜忌氛围标签，只用于表达参考，不作为硬规则。",
    trigger: "环境感知刷新时。",
    enabled: "日程和表达可能带一点当天氛围。",
    disabled: "关闭这部分玄学感，默认更现实。",
  },
  enable_group_companion: {
    summary: "群聊能力总入口，控制群观察、上下文、话题线、关系网和群主动行为是否运行。",
    trigger: "收到群聊消息或后台整理群聊记录时。",
    enabled: "群聊相关子功能才有运行基础。",
    disabled: "多数群聊观察、唤醒、插话和群资料更新都会停止。",
  },
  enable_group_context_injection: {
    summary: "群聊回复前注入群氛围、当前话题、相关成员和关系网信息。",
    trigger: "Bot 准备在群聊回复时。",
    enabled: "Bot 更容易知道刚才在聊什么、提到的是谁。",
    disabled: "群回复主要依赖原始消息，上下文感会弱。",
  },
  enable_forward_message_adaptation: {
    summary: "让 Bot 能阅读合并转发，把节点顺序、发言人和重点内容整理成可理解上下文。",
    trigger: "用户发送合并消息时。",
    enabled: "可选择直接注入摘要，或先用专门模型转述后再回复。",
    disabled: "合并消息只按 AstrBot 原始能力处理，理解能力可能不足。",
  },
  enable_group_scene_awareness: {
    summary: "判断群聊里的话是在叫 Bot、回应别人、普通闲聊还是提到了 Bot。",
    trigger: "群聊消息进入回复或唤醒判断前。",
    enabled: "减少 Bot 抢话，也能识别该接话的无 @ 场景。",
    disabled: "群聊指向判断更依赖硬规则。",
  },
  enable_group_reality_promise_guard: {
    summary: "限制群聊回复里的现实执行承诺，避免 Bot 说自己能实际拉人、修网、开房间或操作设备。",
    trigger: "群聊 LLM 回复生成前。",
    enabled: "Bot 会把现实执行请求改成提醒、建议或说明做不到实际操作。",
    disabled: "群聊也按人格自由扮演，不额外限制现实承诺。",
  },
  enable_group_wakeup_enhancement: {
    summary: "扩展群聊唤醒方式：强唤醒词直接叫到 Bot，弱相关词先判断语境，兴趣词按概率接话。",
    trigger: "群聊出现配置词、Bot 名字、关系网相关称呼或兴趣话题时。",
    enabled: "Bot 更像会被自然叫到，也会偶尔被感兴趣话题吸引。",
    disabled: "主要依赖 @、指令或 AstrBot 原本触发方式。",
  },
  enable_group_high_intensity_mode: {
    summary: "自动识别连续唤醒的热闹群聊，把同群后续唤醒消息合并成一轮回复。",
    trigger: "统计窗口内多次 @、引用 Bot 或增强唤醒时。",
    enabled: "按合并等待秒数收口，减少多次 LLM 调用，并暂停弱相关/兴趣唤醒、群片段整理、黑话释义刷新和主动插话。",
    disabled: "群聊仍按普通收口、续接和后台刷新流程运行。",
  },
  enable_group_conversation_followup: {
    summary: "群里叫过 Bot 后，判断同一用户后续没 @ 的话是否仍然是在和 Bot 说。",
    trigger: "群聊中刚发生过 Bot 回复，随后同一用户继续发言时。",
    enabled: "Bot 不会因为用户忘记 @ 就马上断掉对话，但有轮数上限。",
    disabled: "无 @ 后续消息更容易被当作普通群聊。",
  },
  enable_group_slang_learning: {
    summary: "记录群内常见黑话、简称、梗和特殊称呼。",
    trigger: "群聊出现重复使用或上下文明显的特殊表达时。",
    enabled: "Bot 会逐渐看懂群内专属表达。",
    disabled: "不会继续新增黑话候选。",
  },
  enable_group_slang_meanings: {
    summary: "为已记录黑话生成简短释义，避免只存词不懂意思。",
    trigger: "群黑话达到解释条件时。",
    enabled: "群黑话页面会有更可读的解释，回复也能参考。",
    disabled: "只保留词本身，含义理解更依赖实时上下文。",
  },
  enable_group_member_profiles: {
    summary: "维护群成员发言习惯、互动角色和常见称呼。",
    trigger: "群成员持续发言或被关系网识别时。",
    enabled: "Bot 更容易知道群里谁是谁、谁常做什么。",
    disabled: "群成员画像不再自动更新。",
  },
  enable_group_topic_threads: {
    summary: "整理群聊一段时间内的主题线，而不是只截取单句。",
    trigger: "群聊持续讨论、话题转移或用户长时间未活跃后。",
    enabled: "转述群里有趣内容时更像摘要整个时间段。",
    disabled: "群聊理解更偏最近消息片段。",
  },
  enable_group_episode_memory: {
    summary: "把群聊阶段性事件整理成片段，供之后回忆、转述和关系更新使用。",
    trigger: "群消息累积到整理阈值时。",
    enabled: "Bot 能记住群里发生过的阶段性事件。",
    disabled: "不会新增群聊片段记忆。",
  },
  enable_group_relationship_graph: {
    summary: "记录群成员之间的互动关系，例如常互相回复、玩梗、争论或一起出现。",
    trigger: "群聊里成员之间发生互动时。",
    enabled: "关系网页和群聊判断会更直观地知道成员关系。",
    disabled: "不再更新互动边，关系网只保留静态身份资料。",
  },
  enable_group_interjection: {
    summary: "允许 Bot 在群聊中不被直接叫到时主动插一句。",
    trigger: "群聊有合适话题、频率限制通过且人格愿意参与时。",
    enabled: "Bot 会低频主动参与群聊。",
    disabled: "Bot 基本只在被叫到、被 @ 或规则触发时回复。",
  },
  enable_group_repeat_follow: {
    summary: "群里同一句话复读超过阈值后，Bot 可能跟读一次或打断复读。",
    trigger: "检测到连续复读链时。",
    enabled: "跟读和打断概率会随复读持续共同上升，最多跟读一次。",
    disabled: "复读链不会触发 Bot 的特殊处理。",
  },
  enable_group_interjection_feedback: {
    summary: "记录群友对 Bot 主动插话的反应，用来调整后续插话倾向。",
    trigger: "Bot 群主动插话后，群友继续回应或冷场时。",
    enabled: "后续插话会更懂哪些群和话题适合参与。",
    disabled: "插话频率主要按固定参数控制。",
  },
  enable_group_privacy_guard: {
    summary: "防止 Bot 把私聊内容、敏感转述或不该公开的关系信息带到群里。",
    trigger: "群聊回复、转述和群主动分享前。",
    enabled: "会拦截或改写可能泄露隐私的内容。",
    disabled: "隐私保护更依赖主模型自身判断，不建议关闭。",
  },
  enable_worldbook_member_recognition: {
    summary: "用 QQ 号锚定成员身份，别名和群名片只是辅助，避免改名后认错人。",
    trigger: "群聊提到成员、@ 成员、自登记或转述解析时。",
    enabled: "Bot 能把别名、QQ 和用户资料对应起来，并按需注入词条。",
    disabled: "身份识别主要依赖当前昵称和原始消息。",
  },
  enable_atrelay_tools: {
    summary: "提供转述、@ 群友、多目标提醒和延迟转述能力，并优先结合关系网解析对象。",
    trigger: "用户让 Bot 帮忙告诉、提醒、转发或等某人出现再说时。",
    enabled: "Bot 可按人格改写、敏感确认、解析对象并执行转述。",
    disabled: "这些转述工具不可用，Bot 只能文字建议用户自己说。",
  },
  enable_livingmemory_integration: {
    summary: "允许插件与 LivingMemory 长期记忆协同，按需调用外部记忆工具。",
    trigger: "回复或整理时需要更长期记忆支持。",
    enabled: "可减少重复存储，并让长期记忆链路更完整。",
    disabled: "插件只使用自身记忆结构，不调用 LivingMemory。",
  },
  enable_bilibili_integration: {
    summary: "接入 B 站相关能力，读取观看记录或视频信息作为 Bot 的生活见闻来源。",
    trigger: "后台长线行为或用户询问最近看了什么时。",
    enabled: "B 站子能力才可运行。",
    disabled: "不会读取或使用 B 站内容。",
  },
  enable_bilibili_boredom_watch: {
    summary: "Bot 无聊或空档时低频刷视频，并可能形成观看印象。",
    trigger: "日程空档、无聊状态或长线主动检查时。",
    enabled: "Bot 可以自己看视频，按人格决定是否分享。",
    disabled: "不会主动刷视频。",
  },
  enable_news_integration: {
    summary: "接入新闻源和热点源，让 Bot 获得近期时讯见闻。",
    trigger: "日程生成、每日热点读取或无聊看新闻时。",
    enabled: "新闻相关子能力才可运行。",
    disabled: "Bot 不会主动读取新闻或热点。",
  },
  enable_news_daily_hot_read: {
    summary: "每日读取热点候选，形成当天内部见闻，默认随日程生成或后台检查进行。",
    trigger: "每天首次日程生成或后台热点检查时。",
    enabled: "Bot 会有当天热点印象，但不一定主动分享。",
    disabled: "不会自动获取每日热点。",
  },
  enable_ai_daily_watch: {
    summary: "按配置时间读取 AI 日报/早报来源，默认 12:00 读黑鸦Heya早报，23:00 读橘鸦Juya日报。",
    trigger: "后台检查发现某个来源已到配置时间且今天尚未尝试时。",
    enabled: "到点后当天只尝试一次，优先读取文字版正文，再尝试字幕和视频公开信息。",
    disabled: "不会自动追踪 AI 日报/早报定时来源。",
  },
  enable_news_boredom_read: {
    summary: "Bot 空闲或无聊时低频看新闻，按人格判断是否提起。",
    trigger: "无聊状态、空档日程或长线主动检查时。",
    enabled: "Bot 可能自己读新闻并留下记录。",
    disabled: "只保留每日热点或用户主动要求搜索。",
  },
  enable_external_event_self_link: {
    summary: "新闻阅读或主动搜索完成后，先判断外界信息与 Bot 自己的模型、能力、兴趣、创作、日程或关系是否有关，再决定是否产生主动找用户分享的意愿。",
    trigger: "新闻 digest 生成后、主动搜索笔记生成后。",
    enabled: "Bot 不再只是随机分享新闻，而会带着“这件事和我有什么关系”的动机进入主动候选。",
    disabled: "新闻和搜索仍可记录，但主动分享只按普通分享概率，不做自我关联意愿判断。",
  },
  enable_web_exploration: {
    summary: "允许 Bot 按人格兴趣、最近话题和日程自行选择搜索主题，并记录浏览痕迹。",
    trigger: "用户要求搜索、Bot 主动探索或工具搜索完成后。",
    enabled: "搜索记录会进入浏览记录页，Bot 可形成探索笔记。",
    disabled: "不会主动探索，用户显式搜索也不纳入该长线能力。",
  },
  enable_web_exploration_boredom_search: {
    summary: "Bot 无聊或空档时自己决定想了解什么，再调用 AstrBot 网页搜索。",
    trigger: "日程空档、心情无聊或长线主动检查时。",
    enabled: "Bot 会低频学习新鲜事物并留痕。",
    disabled: "主动搜索不会在空档自动发生。",
  },
  enable_qzone_integration: {
    summary: "启用内置 QQ 空间动态层，支持读取动态、发布说说、点赞和评论。",
    trigger: "用户测试 QQ 空间、Bot 读取动态或生活说说触发时。",
    enabled: "QQ 空间相关子能力才可使用。",
    disabled: "不会访问 QQ 空间。",
  },
  enable_qzone_life_publish: {
    summary: "根据日程、状态和日记余味，低频发布公开生活说说。",
    trigger: "满足间隔、概率和人格意愿时。",
    enabled: "Bot 可能把自己的生活片段发到空间。",
    disabled: "只读动态，不主动发布生活说说。",
  },
  enable_private_reading_integration: {
    summary: "启用书柜夹层的私下阅读素材入口；仅在检测到对应素材能力时显示相关配置。",
    trigger: "素材能力可用、书柜打开或私下阅读检查时。",
    enabled: "夹层可保存阅读素材、封面、页图、批注和读后感。",
    disabled: "私下阅读素材入口不运行。",
  },
  enable_private_reading_boredom_read: {
    summary: "Bot 空档或无聊时低频自己找短篇素材阅读，并把内容放入书柜夹层。",
    trigger: "无聊状态、阅读间隔满足且素材能力可用时。",
    enabled: "Bot 会阅读页图、生成批注和读后感。",
    disabled: "不会主动寻找和阅读素材。",
  },
  enable_private_reading_ask_recommendation: {
    summary: "Bot 无聊时可低频向用户征求阅读推荐，是否害羞或坦然由人格决定。",
    trigger: "素材能力可用、无聊且概率通过时。",
    enabled: "Bot 可能主动问用户有没有推荐。",
    disabled: "不会主动征求推荐。",
  },
  enable_private_reading_preference_influence: {
    summary: "把书柜夹层阅读评分沉淀成私密偏好画像，只在私聊里弱影响亲密互动和语气尺度。",
    trigger: "私聊回复前，且累计评分数达到配置阈值时。",
    enabled: "Bot 会更自然地参考用户稳定高分倾向，但不会说出评分来源或覆盖人格。",
    disabled: "评分仍用于后续素材挑选，但不注入私聊回复。",
  },
  enable_unanswered_screen_peek_followup: {
    summary: "Bot 主动发消息后用户长时间没回时，可窥屏看看用户是不是在忙。",
    trigger: "主动消息发出后超过配置分钟数且冷却通过。",
    enabled: "这类识屏不受普通日次数限制，但仍受冷却控制。",
    disabled: "用户不回时不会因此额外识屏。",
  },
  enable_creative_writing: {
    summary: "Bot 会在闲暇时从生活小事、梦境、日记或阅读灵感中可选地写一点文本作品，并放入书柜。",
    trigger: "日程处于休息、摸鱼、读书、写字等空闲片段，且灵感概率命中时。",
    enabled: "每次只写一小段，不按小时产出，也不会一口气写完。",
    disabled: "不会新建或推进创作项目。",
  },
  creative_hidden_mode: {
    summary: "创作默认作为 Bot 自己的私下活动，只在合适节点或用户问近况时自然透露。",
    trigger: "创作达到节点、用户询问近况或分享概率通过时。",
    enabled: "Bot 不会频繁汇报创作进度，保留自己的创作者主动性。",
    disabled: "创作相关内容更容易被主动提起。",
  },
};

function featureDetailExplanation(key) {
  const guide = featureDetailGuides[key];
  if (guide?.summary) return guide.summary;
  if (key.startsWith("enable_group_")) return "群聊子能力。";
  if (key.startsWith("enable_private_reading_")) return "夹层阅读子能力。";
  if (key.startsWith("enable_bilibili_")) return "B 站子能力。";
  if (key.startsWith("enable_qzone_")) return "QQ 空间子能力。";
  return featureDescription(key);
}

function featureDetailGuideRows(key) {
  const guide = featureDetailGuides[key] || {};
  return [
    ["何时生效", guide.trigger || "该功能对应场景触发时生效。"],
    ["开启后", guide.enabled || "相关能力会参与判断、注入或后台整理。"],
    ["关闭后", guide.disabled || "相关能力停止新增处理，已有数据通常仍可在页面查看。"],
  ];
}

function featureImpactLines(key) {
  const lines = [];
  const group = featureGroupForKey(key);
  lines.push(["模块", group]);
  if (key.startsWith("enable_group_") || key === "enable_atrelay_tools" || key === "enable_worldbook_member_recognition") {
    lines.push(["场景", "群聊 / 转述 / 关系网"]);
  } else if (key === "enable_private_image_self_recognition") {
    lines.push(["场景", "私聊图片 / 表情包"]);
  } else if (key.startsWith("enable_bilibili_") || key.startsWith("enable_news_") || key === "enable_external_event_self_link" || key.startsWith("enable_web_exploration") || key.startsWith("enable_qzone_") || key === "enable_photo_text_action" || key.startsWith("enable_private_reading_") || key === "enable_creative_writing" || key === "creative_hidden_mode") {
    lines.push(["场景", "长线主动"]);
  } else if (key.startsWith("enable_environment_") || key.includes("perception")) {
    lines.push(["场景", "日程 / 状态 / 回复"]);
  } else {
    lines.push(["场景", "私聊陪伴"]);
  }
  return lines;
}

function configLabel(name) {
  return configLabels[name] || name.replace(/^enable_/, "").replaceAll("_", " ");
}

function featureDetailPage(key) {
  const enabled = Boolean(state.featureDraft[key]);
  const related = featureRelatedSettings(key);
  const relatedMap = Object.fromEntries(related.map((item) => [item.key, item]));
  const dependencies = featureDependencyLines(key);
  const impacts = featureImpactLines(key);
  const guideRows = featureDetailGuideRows(key)
    .map(([name, value]) => `<div><dt>${escapeHtml(name)}</dt><dd>${escapeHtml(value)}</dd></div>`)
    .join("");
  const settingRow = ({ key: name, value, description }) => `
      <section class="feature-param-row">
        <div class="feature-param-main">
          <header>
            <b>${escapeHtml(configLabel(name))}</b>
            <code>${escapeHtml(name)}</code>
          </header>
          <p>${escapeHtml(description)}</p>
        </div>
        <div class="feature-param-control">
          ${featureSettingInput(name, value)}
        </div>
      </section>
    `;
  const sections = featureSettingSections[key] || [];
  const renderedSectionKeys = new Set();
  const groupedRows = sections
    .map((section) => {
      const items = (section.keys || []).map((name) => relatedMap[name]).filter(Boolean);
      items.forEach((item) => renderedSectionKeys.add(item.key));
      if (!items.length) return "";
      return `
        <section class="feature-param-section">
          <header>
            <b>${escapeHtml(section.title || "参数")}</b>
            ${section.note ? `<span>${escapeHtml(section.note)}</span>` : ""}
          </header>
          ${items.map(settingRow).join("")}
        </section>
      `;
    })
    .join("");
  const ungroupedRows = related.filter((item) => !renderedSectionKeys.has(item.key)).map(settingRow).join("");
  const extraParamPanel = key === "enable_segmented_proactive_reply" ? segmentedPreviewPanelHtml() : "";
  const settingsRows = related.length
    ? `${groupedRows}${ungroupedRows}`
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
        <b>${escapeHtml(enabled ? "开启" : "关闭")}</b>
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
          <h3>范围</h3>
          <dl>${impactRows}</dl>
        </article>
        <article class="feature-detail-card feature-detail-card-guide">
          <h3>功能说明</h3>
          <dl>${guideRows}</dl>
        </article>
        <article class="feature-detail-card feature-detail-card-params">
          <h3>关联参数</h3>
          <form class="feature-param-list" data-feature-param-form="${escapeHtml(key)}">
            ${settingsRows}
            ${extraParamPanel}
            ${related.length ? `<button type="submit" class="feature-param-save">保存关联参数</button>` : ""}
          </form>
        </article>
        <article class="feature-detail-card">
          <h3>依赖</h3>
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
  document.querySelectorAll("[data-feature-param-form]").forEach((form) => {
    form.querySelectorAll("[data-feature-param]").forEach((input) => {
      if (input.type === "checkbox") {
        input.addEventListener("change", () => {
          const label = input.closest(".feature-param-check")?.querySelector("span");
          if (label) label.textContent = input.checked ? "开启" : "关闭";
        });
      }
    });
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const featureKey = form.dataset.featureParamForm || state.selectedFeatureKey;
      const payload = collectFeatureDetailPayload(featureKey, form);
      await runAction(
        () => postJson("/settings/update", payload),
        "已保存功能参数",
        form.querySelector(".feature-param-save"),
      );
    });
  });
  if (state.selectedFeatureKey === "enable_segmented_proactive_reply") {
    bindSegmentedPreview($("#featureFlags"));
  }
}

function renderProviders() {
  const providers = providerValuesForRender();
  renderProviderSummary(providers);
  renderProviderFlow(providers);
  const entries = Object.entries(providerLabels)
    .filter(([key]) => visibleConfigKey(key))
    .filter(([key, label]) => providerMatchesFilter(key, label, providers));
  const groups = providerGroups
    .map((group) => {
      const groupEntries = entries.filter(([key]) => providerGroupByKey[key]?.id === group.id);
      if (!groupEntries.length) return "";
      return `
        <section class="provider-group" data-provider-group="${escapeHtml(group.id)}">
          <div class="provider-group-head">
            <div>
              <h3>${escapeHtml(group.title)}</h3>
              <p>${escapeHtml(group.desc)}</p>
            </div>
            <span>${groupEntries.length} 项</span>
          </div>
          <div class="provider-grid">
            ${groupEntries.map(([key, label]) => providerCardMarkup(key, label, providers)).join("")}
          </div>
        </section>
      `;
    })
    .join("");
  $("#providerForm").innerHTML = groups || `
    <div class="empty provider-empty">
      <b>没有匹配的模型配置</b>
      <span>换个关键词，或切回“全部”查看完整模型分工。</span>
    </div>
  `;
  bindProviderTests();
}

function providerValuesForRender() {
  return {
    ...(state.overview?.providers || {}),
    ...(state.providerDraft || {}),
  };
}

function providerCardMarkup(key, label, providers) {
  const selected = providers[key] || "";
  const resolved = resolveProviderId(key, providers);
  const configured = Boolean(selected);
  const group = providerGroupByKey[key];
  const statusLabel = configured ? "已单独配置" : "自动回退";
  return `
    <article class="provider-card ${configured ? "configured" : "inherited"}">
      <div class="provider-card-head">
        <div>
          <span class="provider-card-kicker">${escapeHtml(group?.title || "模型配置")}</span>
          <h3>${escapeHtml(label)}</h3>
        </div>
        <span class="provider-badge ${configured ? "configured" : "inherited"}">${escapeHtml(statusLabel)}</span>
      </div>
      <label class="provider-field">
        <span>Provider</span>
        ${providerSelect(key, selected)}
      </label>
      <div class="provider-current">
        <span>当前使用</span>
        <b>${escapeHtml(resolved || "AstrBot 默认模型")}</b>
      </div>
      ${providerGuideMarkup(key)}
      <div class="provider-row">
        <span class="hint">${escapeHtml(key)}</span>
        <button type="button" data-provider-test="${escapeHtml(key)}">测试</button>
      </div>
      <span class="provider-status" data-provider-status="${escapeHtml(key)}"></span>
    </article>
  `;
}

function providerGuideMarkup(key) {
  const guide = providerGuides[key];
  if (!guide) return "";
  return `
    <span class="provider-guide">
      <span><b>用途</b>${escapeHtml(guide.purpose)}</span>
      <span><b>适合</b>${escapeHtml(guide.fit)}</span>
      <span><b>回退</b>${escapeHtml(guide.fallback)}</span>
    </span>
  `;
}

function providerMatchesFilter(key, label, providers) {
  const mode = state.providerMode || "all";
  const configured = Boolean(providers[key]);
  const group = providerGroupByKey[key];
  if (mode === "configured" && !configured) return false;
  if (mode === "inherited" && configured) return false;
  if (mode === "vision" && group?.id !== "media") return false;
  const query = (state.providerFilter || "").trim().toLowerCase();
  if (!query) return true;
  const guide = providerGuides[key] || {};
  const haystack = [
    key,
    label,
    group?.title || "",
    guide.purpose || "",
    guide.fit || "",
    guide.fallback || "",
    providers[key] || "",
  ].join(" ").toLowerCase();
  return haystack.includes(query);
}

function renderProviderSummary(providers) {
  const keys = Object.keys(providerLabels).filter((key) => visibleConfigKey(key));
  const configured = keys.filter((key) => Boolean(providers[key])).length;
  const inherited = keys.length - configured;
  const available = state.availableProviders.length;
  const vision = providers.PLUGIN_VISION_PROVIDER_ID || "跟随 AstrBot 本体/工具转述";
  $("#providerSummary").innerHTML = `
    <div class="provider-summary-card strong">
      <span>单独配置</span>
      <b>${configured}/${keys.length}</b>
      <small>已指定专用 Provider</small>
    </div>
    <div class="provider-summary-card">
      <span>自动回退</span>
      <b>${inherited}</b>
      <small>留空项会按兜底链路执行</small>
    </div>
    <div class="provider-summary-card">
      <span>可选 Provider</span>
      <b>${available}</b>
      <small>${escapeHtml(available ? "来自 AstrBot 当前配置" : "暂无可选项，可手动输入 ID")}</small>
    </div>
    <div class="provider-summary-card">
      <span>视觉通道</span>
      <b>${escapeHtml(vision)}</b>
      <small>图片、识屏与素材理解</small>
    </div>
  `;
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
  const values = {
    ...(state.overview?.providers || {}),
    ...(state.providerDraft || {}),
  };
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
    select.addEventListener("change", () => {
      syncProviderInput(select);
      rememberProviderDraft(select.dataset.providerSelect);
    });
  });
  document.querySelectorAll("[data-provider-key]").forEach((input) => {
    input.addEventListener("input", () => rememberProviderDraft(input.dataset.providerKey));
  });
  document.querySelectorAll("[data-provider-test]").forEach((button) => {
    button.addEventListener("click", async () => {
      await testProvider(button.dataset.providerTest);
    });
  });
}

function bindProviderToolbar() {
  const filter = $("#providerFilter");
  if (filter) {
    filter.addEventListener("input", () => {
      state.providerFilter = filter.value;
      renderProviders();
    });
  }
  document.querySelectorAll("[data-provider-mode]").forEach((button) => {
    button.addEventListener("click", () => {
      state.providerMode = button.dataset.providerMode || "all";
      document.querySelectorAll("[data-provider-mode]").forEach((item) => {
        item.classList.toggle("active", item === button);
      });
      renderProviders();
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

function rememberProviderDraft(key) {
  const input = document.querySelector(`[data-provider-key="${key}"]`);
  if (!input) return;
  state.providerDraft[key] = input.value.trim();
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
  const pluginVision = providers.PLUGIN_VISION_PROVIDER_ID
    || providers.NARRATION_PROVIDER_ID
    || "跟随工具结果转述 / 主模型";
  const tasks = Object.entries(providerLabels).filter(([key]) => (
    key !== "LLM_PROVIDER_ID"
    && key !== "MAI_STYLE_PROVIDER_ID"
    && key !== "PLUGIN_VISION_PROVIDER_ID"
    && visibleConfigKey(key)
  ));
  $("#providerFlow").innerHTML = `
    <div class="flow-lane">
      <span class="flow-node primary">主模型<br><b>${escapeHtml(main)}</b></span>
      <span class="flow-arrow">→</span>
      <span class="flow-node">陪伴通用<br><b>${escapeHtml(mai)}</b></span>
    </div>
    <div class="flow-lane">
      <span class="flow-node primary">默认图片转述<br><b>AstrBot 本体配置</b></span>
      <span class="flow-arrow">→</span>
      <span class="flow-node ${providers.PLUGIN_VISION_PROVIDER_ID ? "primary" : "inherited"}">插件识图模型<br><b>${escapeHtml(pluginVision)}</b></span>
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

function tokenBudgetStat({ limit, remaining, softLabel, softValue }) {
  const rows = [
    ["今日上限", limit],
    ["今日剩余", remaining],
    [softLabel, softValue],
  ];
  return `
    <div class="mini-stat token-budget-stat">
      ${rows.map(([label, value]) => `
        <span class="token-budget-item">
          <b>${escapeHtml(value)}</b>
          <small>${escapeHtml(label)}</small>
        </span>
      `).join("")}
    </div>
  `;
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
  return featureMeta[key]?.[1] || "配置开关。";
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

async function copyTextToClipboard(text, successMessage = "已复制") {
  const value = String(text || "").trim();
  if (!value) {
    showToast("没有可复制的内容", "error");
    return;
  }
  const fallbackCopy = () => {
    const box = document.createElement("textarea");
    box.value = value;
    box.setAttribute("readonly", "readonly");
    box.style.position = "fixed";
    box.style.left = "-9999px";
    box.style.top = "0";
    document.body.appendChild(box);
    box.focus();
    box.select();
    try {
      box.setSelectionRange(0, box.value.length);
    } catch (error) {
      // Older engines may not support setSelectionRange on textarea in this context.
    }
    const ok = document.execCommand("copy");
    box.remove();
    return ok;
  };
  try {
    if (navigator.clipboard?.writeText) {
      try {
        await navigator.clipboard.writeText(value);
      } catch (error) {
        if (!fallbackCopy()) throw error;
      }
    } else {
      if (!fallbackCopy()) throw new Error("浏览器拒绝复制");
    }
    showToast(successMessage);
  } catch (error) {
    showToast(`复制失败：${error.message}`, "error");
  }
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
    if (result && typeof result === "object" && result.plugin && result.features) {
      state.overview = result;
      state.featureDraft = { ...(result.features || {}) };
      renderAll();
      $("#subtitle").textContent = `${result.plugin.bot_name || "Private Companion"} · ${new Date().toLocaleString()}`;
    } else {
      await loadAll();
    }
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
  const deleteButton = element?.closest("[data-book-delete]");
  if (deleteButton) {
    void deleteSelectedBookshelfItem(deleteButton);
    return;
  }
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
  const ratingButton = element?.closest("[data-book-rating]");
  if (ratingButton) {
    void rateSelectedBookshelfItem(ratingButton);
    return;
  }
  const commentsUpdateButton = element?.closest("[data-book-reread], [data-book-comments-update]");
  if (commentsUpdateButton) {
    void rereadSelectedBookshelfItem(commentsUpdateButton);
    return;
  }
  const tagPickButton = element?.closest("[data-book-tag-pick]");
  if (tagPickButton) {
    applyBookPreferenceTagPick(tagPickButton);
    return;
  }
  const diaryJump = element?.closest("[data-diary-jump]");
  if (diaryJump) {
    state.selectedDiaryDate = diaryJump.dataset.diaryJump || "";
    renderBookDetailPanel();
    return;
  }
  const browsingJump = element?.closest("[data-browsing-index]");
  if (browsingJump) {
    state.selectedBrowsingIndex = Number(browsingJump.dataset.browsingIndex || 0);
    renderBookDetailPanel();
    return;
  }
  const copySource = element?.closest("[data-copy-source-url]");
  if (copySource) {
    void copyTextToClipboard(copySource.dataset.copySourceUrl || "", "已复制来源链接");
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
  showToast("正在从书柜移除...");
  try {
    const result = await postJson("/bookshelf/delete", {
      kind,
      id: itemId,
      album_id: albumId,
      title,
      date: diaryDate,
      access_token: state.bookshelfAccessToken || state.bookshelfUnlocked?.access_token || "",
    });
    if (!result.changed) {
      showToast("没有找到要移除的书柜条目，请刷新拓展页后再试。", "error");
      if (button) {
        button.disabled = false;
        button.textContent = kind === "diary" ? "删除当前日记" : "从书柜移除";
      }
      return;
    }
    state.bookshelfUnlocked = result.bookshelf || null;
    state.bookshelfAccessToken = result.bookshelf?.access_token || state.bookshelfAccessToken || "";
    state.selectedBook = null;
    state.bookshelfPage = "shelf";
    state.selectedBookSpreadIndex = 0;
    renderBookshelf();
    showToast(kind === "diary" ? "日记已删除。" : "已从书柜移除。");
  } catch (error) {
    showToast(`移除失败：${error.message}`, "error");
    if (button) {
      button.disabled = false;
      button.textContent = kind === "diary" ? "删除当前日记" : "从书柜移除";
    }
  }
}

async function rateSelectedBookshelfItem(button = null) {
  const book = state.selectedBook || {};
  const albumId = book.album_id || button?.closest("[data-book-rating-album]")?.dataset?.bookRatingAlbum || "";
  const rating = Number(button?.dataset?.bookRating || 0);
  if (!albumId || !rating) {
    showToast("没有找到要评分的藏书。", "error");
    return;
  }
  const reason = "";
  await runAction(async () => {
    const result = await postJson("/bookshelf/rate", {
      album_id: albumId,
      rating,
      reason,
      access_token: state.bookshelfAccessToken || state.bookshelfUnlocked?.access_token || "",
    });
    state.bookshelfUnlocked = result.bookshelf || null;
    state.bookshelfAccessToken = result.bookshelf?.access_token || state.bookshelfAccessToken || "";
    const updated = allBookshelfBooks().find((item) => item.kind === "jm_album" && String(item.album_id || "") === String(albumId));
    if (updated) state.selectedBook = updated;
    renderBookshelf();
    state.bookshelfPage = "reader";
    renderBookDetailPanel();
  }, `已评分 ${rating}/10`, button);
}

async function updateSelectedBookshelfTags(form) {
  const book = state.selectedBook || {};
  const albumId = book.album_id || "";
  if (!albumId) {
    showToast("没有找到要编辑标签的藏书。", "error");
    return;
  }
  const button = form.querySelector("button[type='submit']");
  const likedTags = parseBookTagInput(form.elements.liked_tags?.value || "");
  const dislikedTags = parseBookTagInput(form.elements.disliked_tags?.value || "")
    .filter((tag) => !likedTags.some((liked) => liked.toLocaleLowerCase() === tag.toLocaleLowerCase()));
  await runAction(async () => {
    const result = await postJson("/bookshelf/tags", {
      album_id: albumId,
      liked_tags: likedTags,
      disliked_tags: dislikedTags,
      access_token: state.bookshelfAccessToken || state.bookshelfUnlocked?.access_token || "",
    });
    state.bookshelfUnlocked = result.bookshelf || null;
    state.bookshelfAccessToken = result.bookshelf?.access_token || state.bookshelfAccessToken || "";
    const updated = allBookshelfBooks().find((item) => item.kind === "jm_album" && String(item.album_id || "") === String(albumId));
    if (updated) state.selectedBook = updated;
    state.bookshelfPage = "detail";
    renderBookshelf();
    renderBookDetailPanel();
  }, "已保存标签", button);
}

function applyBookPreferenceTagPick(button) {
  const form = button.closest("[data-book-preference-form]");
  const tag = String(button.dataset.tagValue || "").trim();
  const target = button.dataset.tagTarget === "disliked" ? "disliked_tags" : "liked_tags";
  const other = target === "liked_tags" ? "disliked_tags" : "liked_tags";
  if (!form || !tag) return;
  const targetInput = form.elements[target];
  const otherInput = form.elements[other];
  if (!(targetInput instanceof HTMLInputElement) || !(otherInput instanceof HTMLInputElement)) return;
  const targetTags = parseBookTagInput(targetInput.value);
  const otherTags = parseBookTagInput(otherInput.value).filter((item) => item.toLocaleLowerCase() !== tag.toLocaleLowerCase());
  if (!targetTags.some((item) => item.toLocaleLowerCase() === tag.toLocaleLowerCase())) {
    targetTags.push(tag);
  }
  targetInput.value = targetTags.slice(0, 8).join("、");
  otherInput.value = otherTags.join("、");
}

async function rereadSelectedBookshelfItem(button = null) {
  const book = state.selectedBook || {};
  const albumId = book.album_id || "";
  if (!albumId) {
    showToast("没有找到要重读的藏书。", "error");
    return;
  }
  const currentPage = state.bookshelfPage;
  await runAction(async () => {
    const result = await postJson("/bookshelf/comments/update", {
      album_id: albumId,
      access_token: state.bookshelfAccessToken || state.bookshelfUnlocked?.access_token || "",
    });
    state.bookshelfUnlocked = result.bookshelf || null;
    state.bookshelfAccessToken = result.bookshelf?.access_token || state.bookshelfAccessToken || "";
    const updated = allBookshelfBooks().find((item) => item.kind === "jm_album" && String(item.album_id || "") === String(albumId));
    if (updated) state.selectedBook = updated;
    state.bookshelfPage = currentPage === "reader" ? "reader" : "detail";
    renderBookshelf();
    renderBookDetailPanel();
    void hydrateBookshelfImages($("#bookDetailPanel") || document);
  }, "", button);
}

document.addEventListener("submit", (event) => {
  const form = event.target instanceof HTMLFormElement ? event.target : null;
  if (!form || !form.matches("[data-book-preference-form]")) return;
  event.preventDefault();
  void updateSelectedBookshelfTags(form);
});

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
    state.bookshelfAccessToken = result.bookshelf?.access_token || "";
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
  const button = event.target instanceof Element ? event.target.closest("[data-worldbook-edit], [data-worldbook-member], [data-worldbook-save], [data-worldbook-memory-toggle], [data-worldbook-memory-delete], [data-worldbook-observation-accept], [data-worldbook-observation-reject], [data-worldbook-delete]") : null;
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
$("#worldbookClearPendingBtn").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  if (!requireSecondClick(button, "worldbook-clear-pending", "再次点击清理所有待确认观察", "再次点击清理")) return;
  await runAction(() => postJson("/worldbook/observations/clear", {}), "", button);
  button.disabled = !((state.overview?.worldbook?.pending_observation_total || 0) > 0);
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
$("#skillAddForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const name = String(form.get("name") || "").trim();
  if (!name) return;
  const level = Number(form.get("level") || 1);
  await runAction(() => postJson("/skill/update", {
    name,
    category: form.get("category") || "能力",
    level,
    exp: skillExpFloor(level),
    keywords: form.get("keywords") || name,
  }), "已添加技能", event.submitter);
  event.currentTarget.reset();
});
$("#resetTokenStatsBtn").addEventListener("click", async () => {
  const button = $("#resetTokenStatsBtn");
  if (!requireSecondClick(button, "token-reset", "再次点击清空 Token 统计", "再次点击清空")) return;
  await runAction(() => postJson("/token/reset", {}), "已清空 Token 统计", button);
});
document.querySelectorAll("[data-token-view]").forEach((button) => {
  button.addEventListener("click", () => {
    state.tokenView = button.dataset.tokenView || "today";
    renderTokens();
  });
});
$("#tokenDateSelect").addEventListener("change", (event) => {
  state.tokenDate = event.target.value;
  state.tokenView = "date";
  renderTokens();
});

document.addEventListener("submit", async (event) => {
  const form = event.target instanceof HTMLFormElement ? event.target.closest("[data-external-ability-form]") : null;
  if (!form) return;
  event.preventDefault();
  const button = event.submitter || form.querySelector("button[type='submit']");
  const name = form.dataset.externalAbilityForm || "";
  let config = {};
  const rawConfig = form.querySelector('[name="config"]')?.value || "{}";
  try {
    config = JSON.parse(rawConfig || "{}");
  } catch (error) {
    showToast("自定义配置必须是 JSON 对象", "error");
    return;
  }
  if (!config || typeof config !== "object" || Array.isArray(config)) {
    showToast("自定义配置必须是 JSON 对象", "error");
    return;
  }
  await runAction(() => postJson("/external_ability/update", {
    name,
    enabled: Boolean(form.querySelector('[name="enabled"]')?.checked),
    share_probability: Number(form.querySelector('[name="share_probability"]')?.value || 0),
    min_interval_hours: Number(form.querySelector('[name="min_interval_hours"]')?.value || 0),
    config,
  }), "已保存外部主动能力", button);
});

document.addEventListener("click", (event) => {
  const addType = event.target?.dataset?.newsSourceAdd;
  if (addType) {
    const items = newsSourceItemsFromDom();
    items.push({
      enabled: true,
      name: newsSourceTypeLabel(addType),
      type: addType,
      target: addType === "bilibili" ? "bilibili:" : (addType === "bilibili_video" ? "bvid:" : "https://"),
    });
    renderNewsSourceManager(items);
    syncNewsSourcesRaw();
    return;
  }
  if (event.target?.dataset?.newsSourceReset !== undefined) {
    resetNewsSourcesToDefault();
    return;
  }
  const removeIndex = event.target?.dataset?.newsSourceRemove;
  if (removeIndex !== undefined) {
    const index = Number(removeIndex);
    const items = newsSourceItemsFromDom().filter((_, itemIndex) => itemIndex !== index);
    renderNewsSourceManager(items);
    syncNewsSourcesRaw();
  }
});

document.addEventListener("input", (event) => {
  if (event.target?.closest?.("#newsSourceManager")) syncNewsSourcesRaw();
});

document.addEventListener("change", (event) => {
  if (!event.target?.closest?.("#newsSourceManager")) return;
  if (event.target.matches("[data-news-source-type]")) {
    const row = event.target.closest("[data-news-source-item]");
    const input = row?.querySelector("[data-news-source-target]");
    if (input && !String(input.value || "").trim()) {
      input.value = event.target.value === "bilibili" ? "bilibili:" : (event.target.value === "bilibili_video" ? "bvid:" : "https://");
    }
    if (input) input.placeholder = newsSourcePlaceholder(event.target.value);
  }
  syncNewsSourcesRaw();
});

bindRoleplayModeSwitch();
bindProviderToolbar();

["roleplayProfileForm", "privateAliasForm", "quickModuleForm", "environmentModuleForm", "privateModuleForm", "groupModuleForm", "worldbookModuleForm", "memoryModuleForm", "longTermModuleForm"].forEach((formId) => {
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
    if (formId === "privateAliasForm") {
      await loadAll();
    }
  });
});
bindSegmentedPreview();

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
  const values = currentProviderValues();
  const providers = {};
  Object.keys(providerLabels).forEach((key) => {
    if (visibleConfigKey(key)) providers[key] = values[key] || "";
  });
  await runAction(() => postJson("/settings/update", { providers }), "已保存模型配置", $("#saveProvidersBtn"));
  state.providerDraft = { ...state.providerDraft, ...providers };
  renderProviders();
});

$("#testAllProvidersBtn").addEventListener("click", async () => {
  for (const key of Object.keys(providerLabels).filter(visibleConfigKey)) {
    await testProvider(key);
  }
});

loadAll();
