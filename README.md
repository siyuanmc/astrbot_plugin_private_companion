# 我会永远陪着你

`astrbot_plugin_private_companion` 是面向 AstrBot 的人格连续性、关系识别与主动行为编排插件。它把 Bot 从“收到消息后临时回复”的聊天对象，扩展成拥有生活状态、日程节奏、记忆沉淀、群聊观察、长期创作、可选外部动作和可视化管理页的持续存在体。

- 插件名：`astrbot_plugin_private_companion`
- 版本：`3.2.2`
- 适配平台：`aiocqhttp`
- AstrBot 版本：`>=4.22.0`
- 编码要求：UTF-8

## 功能简介

本插件不是单一的主动私聊插件，也不是单独的记忆插件。它更像 AstrBot 之上的“陪伴编排层”：把人格、状态、日程、私聊关系、群聊上下文、长期记忆、外部动作和模型 Provider 组织到同一个长期体验里。

核心目标是让 Bot 拥有“连续存在感”。Bot 会有自己的当天状态、生活节奏、梦境残留、日记、长期小计划、关系认知和群聊观察，而不是只在用户发消息时临时拼一段回复。

主要能力：

- 生活状态：维护睡眠、梦境、体力、心情、饥饿、身体小状态、周期状态、天气和当前位置感。
- 日程与细化：每天生成生活框架，并在临近时间段时展开成具体场景、状态变量和主动契机。
- 私聊陪伴：按每日上限、最小间隔、免打扰时间、用户活跃度、关系状态和当前日程决定是否主动开口。
- 被动回复增强：在 AstrBot 原人格之外注入关系站位、当前状态、日程细节、记忆、用户意图、未完话题和回复自检。
- 消息防抖：把用户短时间内连续补充的消息合并理解；私聊单图会等待用户补充说明，必要时并行进行视觉转述。
- 环境感知：识别当前时间、时段、节假日/工作日、农历节气、平台、群聊/私聊和图片/语音/视频等消息媒介。
- 群聊观察：在允许的群内学习群气氛、黑话、群友轻画像、话题线、群聊片段、复读状态和关系网。
- 连续对话保持：群里用户叫过 Bot 后，可判断后续未继续 @ 的消息是否仍在对 Bot 说话，并限制续接轮数。
- 合并消息适配：支持读取合并转发，可选择“注入”或“转述”两种方式，让 Bot 自然理解转发内容。
- QQ 关系网：以 QQ 号稳定识别用户，昵称、群名片和别名只作为辅助线索，避免改名后认错人。
- 群聊自登记：未登记成员 @Bot 说明“我是 XX / 你可以叫我 XX”时，可进入确认流程并建立关系节点。
- 跨群转述与 @ 群友：可按群名查群号、按关系网解析群友，并进行群聊/私聊转述。
- 群聊到私聊分享：当群聊里出现公开、有趣或值得提醒的时间段话题，且用户长时间未活跃时，可低频私聊转述。
- QQ 空间动态：内置说说查看、点赞、评论、发布和低频生活说说编排，让公开动态成为 Bot 生活连续性的一部分。
- 新闻阅读：按日程或空档读取热点、新闻源和可配置 B 站消息源，形成近期见闻；若文字版可读，会优先阅读完整正文。
- 主动搜索：按人格兴趣、当前状态、日程和最近聊天决定想了解什么，并调用 AstrBot 全局网页搜索留下探索笔记。
- 外界信息自我关联：新闻或搜索读到内容后，会先判断这件事与 Bot 自己的模型、能力、兴趣、创作、日程或关系是否有关，再决定是否产生主动找用户分享的意愿。
- 梦境与日记：生成梦境、梦境碎片和日记，让第二天的状态和主动话题有自然残留。
- 书柜与创作：Bot 可能在闲暇时因生活小事、日记或梦境灵感写一点小说、诗、随笔、短剧、分镜脚本、角色设定或世界观片段；书柜收纳创作、日记本和其他私密文本。安装某些特殊插件后，Bot 也许还会往书柜里放些奇怪的东西，并用插件识图模型按人设口吻留下第一人称读后感和页边批注。
- 技能成长：模拟符合人格的技能等级，从 Lv.1 到 Lv.6 缓慢成长，并影响日程中的能力边界。
- 重要日期：记录生日、纪念日、考试、约定等日期，并影响日程、主动话题和长期准备。
- 多能力主动行为：可选文字、图片、语音、戳一戳、轻窥屏、主动后沉默窥屏、正在输入和 QQ 状态同步。
- 世界观适配：可把现代能力转译成当前人设能理解的世界内说法，例如公会闲谈、行囊书匣、水晶映像或终端频道。
- 模型与成本编排：为日程、细化、日记与梦境、创作、新闻整理、主动搜索、回复自检、关系分析、记忆整理、合并消息转述、群聊判断等任务分别指定 Provider。
- Token 监控：记录插件内部任务的调用次数、Token 消耗、失败记录和每日统计，并支持每日插件 Token 限额。
- 扩展页管理：在 AstrBot WebUI 中查看和管理私聊、群聊、关系网、状态、梦境、书柜、主动计划、功能开关、模型配置和 Token 消耗；模型页会按用途分组展示 Provider、回退关系、当前使用项和测试入口。

常用私聊命令：

```text
陪伴 状态
陪伴 查看主动判定
陪伴 生成状态
陪伴 增添状态 <状态描述>[|持续小时]
陪伴 查看今日日程
陪伴 重置日程
陪伴 当前细化
陪伴 梦境
陪伴 梦境碎片
陪伴 日记
陪伴 生成日记
陪伴 新闻
陪伴 AI新闻
陪伴 日期列表
陪伴 日期添加 <标题> <YYYY-MM-DD或MM-DD> [备注]
陪伴 昵称 <称呼>
陪伴 语气 温柔|活泼|工作
陪伴 长期记忆
陪伴 能力列表
陪伴 查看提示词 日程|细化|主动|回复注入
```

常用群聊命令：

```text
陪伴群 状态
陪伴群 黑话
陪伴群 群友
陪伴群 话题
陪伴群 片段
陪伴群 插话反馈
陪伴群 关系网
陪伴群 开启
陪伴群 关闭
```

## 安装方式

### 方式一：AstrBot 插件市场安装

在 AstrBot WebUI 的插件市场中搜索：

```text
astrbot_plugin_private_companion
```

安装后重启 AstrBot，并进入插件配置页填写目标用户、目标群和模型配置。

### 方式二：从 GitHub 安装

在 AstrBot WebUI 中进入“插件管理”，选择从 Git 安装，填写仓库地址：

```text
https://github.com/menglimi/astrbot_plugin_private_companion
```

### 方式三：手动安装

将插件目录放入 AstrBot 插件目录，并确保目录名为：

```text
astrbot_plugin_private_companion
```

Windows 常见路径：

```text
C:\Users\你的用户名\.astrbot\data\plugins\astrbot_plugin_private_companion
```

安装完成后重启 AstrBot。

### 初次使用

第一次启用时，建议先跑通“私聊能稳定回复”，再逐步打开群聊观察和外部联动：

1. 建议先进入 AstrBot WebUI 的插件拓展页进行配置。确认 `enabled` 已开启，并检查 `target_platform`。QQ/OneBot 通常使用 `aiocqhttp`。
2. 设置模型。`LLM_PROVIDER_ID` 留空时会使用 AstrBot 默认会话模型；如果你准备了专门给陪伴后台任务用的模型，可以在这里指定。拓展页“模型”页会按基础兜底、日程表达、记忆关系、群聊能力、视觉与外界信息分组展示各 Provider，并标注用途、适合模型和回退链路。
3. 填写 `target_user_ids`。这里放需要预热私聊陪伴的 QQ 号，插件启动后会自动为这些用户初始化私聊状态。
4. 先降低主动频率。建议把 `max_daily_messages` 设为 2 到 5，`idle_minutes` 和 `min_interval_minutes` 保持默认或略微调大，`quiet_hours` 设置为不希望被打扰的时间段。
5. 重启 AstrBot 后，在私聊发送 `陪伴 状态`。能看到日程、拟人状态、主动候选和关系信息，就说明基础私聊链路已经跑通。
6. 需要群聊观察时，再到拓展页开启 `enable_group_companion`。建议先使用白名单模式：设置 `group_access_mode=whitelist`，并把允许观察的群填入 `group_whitelist_ids`。
7. 在目标群发送 `陪伴群 状态`，确认当前群已启用；需要临时开关时使用 `陪伴群 开启` / `陪伴群 关闭`。

初次使用不建议立刻打开全部外部动作。图片、语音、戳一戳、识屏、B 站、QQ 空间、ComfyUI、私密阅读等都属于可选联动；等文字回复、状态、日程、群聊观察和记忆行为稳定后，再按需要逐项开启。

如果启用书柜夹层阅读或希望 Bot 给本子生成读后感/批注，建议在模型页单独配置 `PLUGIN_VISION_PROVIDER_ID`（插件识图模型）。它负责读取封面和抽样正文页，并按 Bot 当前人格生成第一人称读后感、页边批注、评分和偏好标签；`NARRATION_PROVIDER_ID` 只是工具结果转述兜底，不适合作为主要读图模型。

关系识别建议保持 `enable_worldbook_member_recognition` 开启。世界观适配 `worldview_adaptation_mode` 默认使用 `auto` 即可，插件会尽量把现代能力转成当前人格能理解的说法。

### 成本建议

建议使用火山引擎火山方舟“协作计划”的免费模型额度覆盖日常成本。按当前插件调用结构估算，在私聊、群聊观察、日程、梦境、记忆整理、关系网、自登记、新闻/搜索、创作和 Token 监控等功能全开的情况下，高活跃环境可能每天消耗约 `500K-800K tokens`。

如果使用火山方舟协作计划，可以直接把 `Doubao-Seed-2.0-pro` 设置为主模型；在每日 `2M tokens` 免费额度内，通常足够覆盖本插件的日常运行。免费额度、模型名称和平台政策可能变化，实际以火山方舟控制台展示为准。

插件提供 `daily_token_limit` 每日 Token 硬限额配置，默认 `1,000,000`。达到限额后，插件会跳过日程、梦境、记忆整理、群聊分析、创作等内部 LLM 任务；填 `0` 表示不限制。

插件还提供可选的每日 Token 软限额：`enable_daily_token_soft_limit` 和 `daily_token_soft_limit`（默认 `800,000`）。它是“达到限额就停止插件/停止后台链路”的替代方案：达到软限额后，插件会优先保留用户当下触发的回复、图片转述和合并转发处理，暂缓新闻整理、网页探索、创作、群聊片段/黑话整理、回复自检、关系分析、夹层视觉和主动生图等低优先级后台任务。

## 可选联动

下面这些插件或服务不是必需项。没有安装时，本插件会自动跳过对应能力或回退成普通文字。若存在 `menglimi` 维护版，建议优先使用 `menglimi` 版本，和本插件的联动适配通常更完整。

### 屏幕陪伴

- 用途：支持主动 `screen_peek` 轻窥屏、主动后沉默时额外窥屏、屏幕状态上下文、天气能力回退。
- 首选仓库：<https://github.com/menglimi/astrbot_plugin_screen_companion>
- 对应配置：`enable_screen_glance_action`、`screen_peek_max_daily`、`screen_peek_cooldown_minutes`、`enable_unanswered_screen_peek_followup`

### TTS 语音

- 用途：支持主动 `voice` 短语音，并兼容 `<tts>...</tts>`、日语、双语或特殊 TTS 人格规则。
- 首选仓库：<https://github.com/menglimi/astrbot_plugin_tts_modify-fishaudio->
- 原始仓库：<https://github.com/L1ke40oz/astrbot_plugin_tts_modify>
- 对应配置：`enable_voice_action`、`voice_action_max_chars`

### ComfyUI 生图

- 用途：支持主动 `photo_text` 图片分享，可根据日程、梦境、当前场景生成图片。
- AstrBot ComfyUI 插件仓库：<https://github.com/cjxzdzh/astrbot_plugin_comfyui>
- ComfyUI 官方仓库：<https://github.com/comfyanonymous/ComfyUI>
- 对应配置：`enable_photo_text_action`、`photo_generation_backend`、`COMFYUI_TEXT2IMG_WORKFLOW_NAME`、`COMFYUI_SELFIE_WORKFLOW_NAME`、`enable_local_photo_load_guard`
- 电脑高负荷时可延后本地 ComfyUI 生图；`auto` 模式下若在线图片 API 可用，会跳过本地后端改走在线后端。

如果不使用 ComfyUI，也可以配置外部图片 API：

- `EXTERNAL_IMAGE_API_BASE_URL`
- `EXTERNAL_IMAGE_API_KEY`
- `EXTERNAL_IMAGE_API_MODEL`
- `external_image_api_size`

### 戳一戳

- 用途：支持主动 `poke`，或在部分主动消息前先轻轻戳一下。
- 可用仓库：<https://github.com/Zhalslar/astrbot_plugin_pokepro>
- 对应配置：`enable_poke_action`、`poke_action_max_times`

### LivingMemory 长期记忆

- 用途：提供大规模长期记忆、向量检索、图谱记忆和 `recall_long_term_memory` 工具。
- 可用仓库：<https://github.com/lxfight-s-Astrbot-Plugins/astrbot_plugin_livingmemory>
- 对应配置：`enable_livingmemory_integration`、`livingmemory_tool_name`

本插件不会重复实现 LivingMemory 的向量库能力。检测到 LivingMemory 后，本插件会把“何时需要召回长期记忆”的判断注入给模型，同时继续负责生活状态、主动行为、关系站位和群聊隐私边界。

### B 站 Bot

- 用途：让 Bot 在日程空档、休息或无聊时低频触发 B 站 Bot 自己刷 1 个视频，并可把观看日志里评分较高、内容适合的视频私聊分享给用户。
- 可用仓库：<https://github.com/chenluQwQ/astrbot_plugin_bilibili_ai_bot>
- 本地插件名：`astrbot_plugin_bilibili_bot`
- 对应配置：`enable_bilibili_integration`、`enable_bilibili_boredom_watch`、`bilibili_boredom_min_interval_hours`、`bilibili_share_probability`、`bilibili_share_min_score`

联动方式是软依赖：陪伴插件只负责判断“现在是不是适合无聊刷一下”和“这条视频要不要分享”，真正的视频获取、观看分析、点赞/评论/收藏行为仍由 B 站 Bot 插件自己的配置决定。

## 已整合能力

下面这些能力已经内置到本插件中，通常不需要再安装对应旧插件。插件启动时会自动检查插件目录：如果发现对应旧插件仍然存在，会自动关闭本插件里可能重复的内置功能，避免双重注入、重复工具或额外 Token 消耗。

### 环境感知

- 参考插件：`astrbot_plugin_LLMPerception`
- 仓库：<https://github.com/miaoxutao123/astrbot_plugin_LLMPerception>
- 内置配置：`enable_environment_perception`、`environment_perception_timezone`、`enable_holiday_perception`、`enable_platform_perception`、`enable_lunar_perception`、`enable_solar_term_perception`、`enable_almanac_perception`

### 群聊场景感知

- 参考插件：`astrbot_plugin_context_aware`
- 仓库：<https://github.com/muyouzhi6/astrbot_plugin_context_aware>
- 内置配置：`enable_group_scene_awareness`、`group_scene_recent_limit`、`enable_group_conversation_followup`

### 跨群转述与 @ 群友

- 参考插件：`astrbot_plugin_atrelay`
- 仓库：<https://github.com/Alien-Star/astrbot_plugin_atrelay>
- 内置配置：`enable_atrelay_tools`、`atrelay_require_worldbook_first`、`atrelay_member_cache_minutes`、`atrelay_sensitive_confirm`、`atrelay_default_relay_style`

### QQ 空间动态

- 参考插件：`astrbot_plugin_qzone`
- 仓库：<https://github.com/Zhalslar/astrbot_plugin_qzone>
- 内置配置：`enable_qzone_integration`、`enable_qzone_life_publish`、`qzone_life_publish_min_interval_hours`、`qzone_life_publish_probability`

### 合并消息阅读

- 参考插件：`astrbot_plugin_forward_reader`
- 能力范围：读取合并转发节点，支持注入或转述模式，可处理图片视觉摘要和嵌套合并消息。
- 内置配置：`enable_forward_message_adaptation`、`forward_message_mode`、`forward_message_max_messages`、`forward_message_max_chars`、`forward_message_parse_nested`、`forward_message_image_vision`、`forward_message_image_limit`
- 安装说明：这是本插件的内置能力，不需要额外安装 `astrbot_plugin_forward_reader`。

## 扩展页介绍

本插件提供 AstrBot 官方 Pages 扩展页：

```text
pages/陪伴面板/
```

如果当前 AstrBot 版本支持 `context.register_web_api()`，插件会注册后端接口：

```text
/astrbot_plugin_private_companion/page/*
```

扩展页用于把“看不见的陪伴状态”可视化。它主要包含：

- 首页总览：私聊对象、群聊观察、名单模式、运行诊断、Token 消耗、今日新闻见闻、主动搜索记录和最近活跃热力。
- 私聊对象：查看启用状态、称呼、语气、关系分数、今日主动次数、最近消息和下次主动线索。
- 群聊观察：查看群状态、话题线、黑话、片段、插话反馈和群聊关系。
- QQ 关系网：管理 QQ 身份节点、别名、曾见群名片、资料正文、身份说明、互动边界和重要记忆。
- 书柜：以书本形式查看创作、日记本和私密文本；日记和夹层内容需要通过 Bot 自己设定的密码打开，本子详情会展示 Bot 的读后感、评分和页边批注。
- 状态与梦境：观察当天状态、睡眠、梦境、健康、饥饿、周期、能量和状态走向。
- 技能成长：查看和管理 Bot 的技能等级、经验、训练来源和对日程的影响。
- 主动候选：查看待触发主动行为、来源、重复次数、冷却和失败原因。
- Token 统计：查看累计与每日消耗、任务分类、Provider 分布和失败记录。
- 功能开关：按模块管理能力开关，并在二级页面调整相关参数。
- 模型配置：为不同任务指定 Provider，按能力分组查看用途、适合模型、回退链路、当前使用项，并测试可用性。
- 模块配置：集中配置名单、群聊、新闻、主动搜索、书柜、关系网、转述、QQ 空间等参数。

扩展页适合排查：

- 为什么某个用户今天没有收到主动消息。
- 群聊上下文是否被学习和注入。
- 关系网有没有正确识别 QQ、别名和被提及用户。
- 图片、语音、识屏或主动额度是否用完。
- 某个模型任务是否消耗过高。
- Bot 当前日程、状态、梦境、技能或书柜内容为什么影响了回复。

## 实现原理

插件由几层状态和决策链组成。

### 1. 生活状态层

每天会生成或维护：

- 拟人状态。
- 今日日程。
- 当前时间段细化。
- 梦境和梦境碎片。
- 日记。
- 书柜创作项目。
- 技能成长状态。
- 重要日期。
- 昨日完整对话摘要。

这些信息不是回复正文，而是供私聊、群聊和主动行为共同参考的生活底座。

### 2. 环境与世界观层

每次模型请求前会注入轻量环境边界：当前时间、时段、工作日/休息日、平台、群聊/私聊和消息媒介类型。可选依赖可提供农历、节气和节假日信息。

`worldview_adaptation_mode` 会把现实插件能力映射成当前人设能理解的说法。比如奇幻人设可以把群聊理解为公会闲谈，把书柜理解为行囊书匣，把识屏理解为水晶映像；科幻人设可以把群聊理解为频道通信，把书柜理解为私人资料柜。

这层只影响表达和上下文理解，不改变真实插件能力。

### 3. 私聊用户层

每个目标用户都有独立状态：

- 是否启用陪伴。
- 昵称和语气偏好。
- 今日主动次数和最近主动时间。
- 最近用户消息和最近陪伴消息。
- 关系分数、关系状态和忽略次数。
- 记忆、表达学习、对话片段和未完成话头。
- 图片、识屏、语音等主动能力的每日额度。

这些状态会持久化保存，重启后继续延续。

### 4. 主动判定层

私聊主动消息发送前会经过多重限制：

- 插件和用户是否启用。
- 是否达到候选主动时间。
- 是否超过每日主动上限。
- 是否处于免打扰时间。
- 用户是否刚刚活跃。
- 距离上次主动是否过近。
- 当前日程是否适合开口。
- 关系状态是否需要后退。
- 目标能力是否可用。

只有条件满足时，才会进入主动内容生成。主动消息只是本插件的一种输出，不是全部功能。

### 5. 主动内容与行为层

主动内容生成时会明确告诉模型：这是 Bot 主动开口，不是用户刚刚发来消息。历史对话只作为关系和话题背景，不能误当作当前用户输入。

模型会先判断这次更适合文字、图片、语音、戳一戳、轻窥屏、群聊转述、新闻分享、主动搜索、B 站分享、QQ 空间动作或创作节点提及。执行层会再次检查能力可用性和额度，避免模型想用但实际不能用。

### 6. 被动回复增强层

用户主动来聊时，插件会在 AstrBot 原人格之外补充上下文：

- 当前生活状态。
- 当前真实时段。
- 今日细化场景。
- 用户关系站位。
- 用户记忆和未完成话头。
- 表达节奏参考。
- 情绪意图判断。
- 最近主动消息承接。
- 用户询问近况时可选提起的私下创作或生活近况。
- LivingMemory 召回提示。

回复后还会做自检，减少助手腔、长篇结构化、内部状态泄露和重复关心。

### 7. 群聊观察层

群聊层默认按白名单或黑名单工作。它会学习目标群内公开信息，包括常见词、黑话、群友轻画像、当前气氛、话题线、群聊片段、复读链、插话反馈和群友关系网。

群聊上下文与私聊记忆隔离。插件不会把私聊关系、私下称呼或私人记忆带进群聊。群聊主动插话默认关闭，需要明确开启。

### 8. QQ 关系网层

关系网以 QQ 号作为唯一稳定身份锚点，群昵称、群名片和别名只作为称呼或被提及线索。

群聊回复前会按顺序注入：

- 当前发言者 QQ 精确命中的节点。
- 当前消息明确提到的已保存名称、别名或曾见群名片。
- 最近发言者 QQ 精确命中的节点。

每个关系节点可以保存资料正文、身份说明、互动边界和重要记忆。自登记会拒绝明显整活、冒领、亲属身份冒领、权限身份冒领、谐音冒领和过长称呼。被拦截时只回复：

```text
你是小猪
```

### 9. 公开动态与外部动作层

QQ 空间动态被视为公开生活札记，不等同于私聊记忆。用户明确要求“看说说、赞说说、评论说说、发说说”时，模型可以调用本插件提供的 QQ 空间工具完成动作。

如果开启生活说说能力，Bot 可以把当天状态、日程片段、天气或日记余味低频整理成公开生活说说。该能力默认关闭；开启后也会遵守最小间隔和概率，不公开私聊隐私、关系网内部备注或状态数值。

## 开发者信息

- 开发者：`menglimi`
- 插件仓库：<https://github.com/menglimi/astrbot_plugin_private_companion>
- 插件版本：`3.2.2`
- 主要文件：
  - `main.py`：插件主体、主动判定、回复注入、群聊观察、能力执行。
  - `planning.py`：日程与规划相关逻辑。
  - `dreaming.py`：梦境生成与梦境碎片。
  - `page_api.py`：扩展页后端 API。
  - `pages/陪伴面板/`：扩展页前端。
  - `_conf_schema.json`：AstrBot 配置项。
  - `metadata.yaml`：插件元数据。

### 外部插件接入

其他插件可以把自己的能力注册成本插件的“外部主动能力”。注册后会出现在拓展页的“模块配置 / 外部主动能力”中，默认不启用；用户可以在那里设置是否加入主动候选、触发权重、冷却时间和自定义配置。

```python
from data.plugins.astrbot_plugin_private_companion.main import get_private_companion_api

async def my_executor(ctx):
    # ctx 包含 user、display_name、reason、bot_name、state、current_plan_item、config、plugin
    return {
        "ok": True,
        "context": "外部插件刚完成了一次适合分享的动作。",
        "summary": "外部动作",
        "memory": "这次外部能力留下的内部印象。",
    }

api = get_private_companion_api()
if api:
    api.register_proactive_ability({
        "name": "example_ability",
        "module": "示例插件",
        "label": "示例主动能力",
        "description": "让 Bot 在合适时机使用示例插件做一件事。",
        "when": "Bot 空闲、当前日程或心情适合这个动作时",
        "use_for": "形成可分享的生活素材或内部印象",
        "avoid": "不要暴露插件名、接口名或执行过程",
        "share_probability": 0.12,
        "min_interval_hours": 12,
        "default_enabled": False,
        "default_config": {"keyword": ""},
        "config_schema": {
            "keyword": {"label": "默认关键词", "description": "外部插件执行时可读取的自定义关键词"}
        },
        "executor": my_executor,
    })
```

执行器可以返回字符串，也可以返回字典。字典支持 `ok/success`、`context`、`summary`、`text`、`image_path`、`extra_components`、`memory`、`status`。本插件只负责把外部能力纳入主动决策和页面管理，具体外部动作仍由注册方插件自己完成。

本插件面向长期陪伴体验。建议先以较低主动频率运行，确认文字、日程、状态、记忆和群聊边界符合预期后，再逐步开启图片、语音、识屏、戳一戳、B 站联动、QQ 空间生活说说等真实外部动作。

## 致谢

本插件在设计和实现过程中参考了以下项目。这里列出的“已整合能力参考”不代表需要重复安装对应插件。

已整合能力参考：

- `astrbot_plugin_LLMPerception`：<https://github.com/miaoxutao123/astrbot_plugin_LLMPerception>，参考了时间、节假日、农历节气、平台和消息媒介的环境感知思路。
- `astrbot_plugin_context_aware`：<https://github.com/muyouzhi6/astrbot_plugin_context_aware>，参考了群聊中“谁在和谁说话”、当前消息是否面向 Bot 的场景判断思路。
- `astrbot_plugin_atrelay`：<https://github.com/Alien-Star/astrbot_plugin_atrelay>，参考了查询群成员、跨群发送消息和 @ 群友的工具化交互思路。
- `astrbot_plugin_qzone`：<https://github.com/Zhalslar/astrbot_plugin_qzone>，参考了 QQ 空间说说查看、点赞、评论、发布、AI 写说说和页面管理的实现思路。
- `astrbot_plugin_forward_reader`：参考了合并消息识别、读取和转述的实现思路。
- `yupi-hot-monitor`：<https://github.com/liyupi/yupi-hot-monitor>，参考了热点候选获取和聚合的思路。

产品方向参考：

- `MaiBot`：<https://github.com/MaiM-with-u/MaiBot>，参考了群聊自然接话、长期人格连续性、表达学习和数字生命感的产品方向。
