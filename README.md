# 我会永远陪着你

`astrbot_plugin_private_companion` 是一个面向 AstrBot 的拟人陪伴与生活状态插件。它不再只服务于私聊主动消息，而是为 Bot 建立连续的生活状态、日程、梦境、日记、长期创作、重要日期、私聊关系记忆和群聊观察层，让 Bot 在私聊、群聊和后台生活里都更像一个持续存在的人。

- 插件名：`astrbot_plugin_private_companion`
- 当前版本：`2.2.0`
- 适配平台：`aiocqhttp`
- AstrBot 版本：`>=4.22.0`
- 编码要求：UTF-8

## 功能简介

本插件的核心目标是“连续存在感”。它会让 Bot 有自己的当天状态、生活节奏、长期小计划和群聊观察，而不是只在用户发消息时临时拼一段回复。

主要能力：

- 生活状态核心：维护睡眠、梦境、体力、心情、饥饿、身体小状态、天气和当前位置感。
- 今日日程与细化：每天生成生活框架，并在临近时间段时展开成具体场景、状态变量和主动契机。
- 私聊主动陪伴：按每日上限、最小间隔、免打扰时间、用户活跃度和关系状态决定是否主动开口。
- 被动回复增强：在 AstrBot 原人格之外注入关系站位、状态、记忆、当前细化、用户意图和回复自检。
- 群聊陪伴观察：在允许的群内学习群气氛、黑话、群友轻画像、话题线、群聊片段和关系网。
- QQ 关系网识别：以 QQ 号稳定识别群成员；消息里提到已保存名称、别名或曾见群名片时，会自动注入对应关系节点。
- 群聊自登记：未登记成员 @Bot 说“我是 XX / 你可以叫我 XX”时，可自动建立关系节点并生成简短人物印象。
- 群聊到私聊分享：当群聊里出现有趣或值得提醒的公开片段，且用户长时间未活跃时，可低频私聊转述。
- 梦境与日记：生成完整梦境、梦境碎片和日记，让第二天有自然残留。
- 私下创作：可能因生活小事、日记或梦境灵感开小说坑，并按人格速度慢慢写；默认只在阶段节点、想听读后感觉，或用户主动询问近况时自然提起，故事主导权始终在 Bot 自己手里。
- 重要日期：记录生日、纪念日、考试、约定等日期，并影响日程、主动话题和长期准备。
- 多能力主动行为：可选使用文字、图片、语音、戳一戳、轻窥屏、主动后沉默窥屏、正在输入和 QQ 状态同步。
- Token 监控与扩展页：在 AstrBot WebUI 中查看私聊、群聊、记忆、额度、主动计划和模型消耗。

常用私聊命令：

```text
陪伴 状态
陪伴 查看主动判定
陪伴 生成状态
陪伴 查看今日日程
陪伴 重置日程
陪伴 当前细化
陪伴 梦境
陪伴 梦境碎片
陪伴 日记
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

### 最小配置

首次使用建议至少配置：

- `LLM_PROVIDER_ID`：主模型 Provider。
- `target_user_ids`：需要预热私聊陪伴的 QQ 号。
- `target_platform`：目标平台，通常为 QQ/aiocqhttp 对应平台。
- `max_daily_messages`：每个用户每日主动消息上限。
- `idle_minutes`：用户空闲多久后才允许主动。
- `min_interval_minutes`：两次主动之间的最小间隔。
- `quiet_hours`：免打扰时间。
- `enable_group_companion`：是否启用群聊观察。
- `group_access_mode`、`group_whitelist_ids`、`group_blacklist_ids`：群聊启用范围。
- `enable_worldbook_member_recognition`：启用群聊关系网。
- `worldbook_self_registration`：允许群聊自登记关系节点。

`target_user_ids` 中的用户会在插件启动时自动初始化私聊陪伴。群聊默认建议使用白名单，避免误观察不该启用的群。

### 成本建议

建议使用火山引擎火山方舟“协作计划”的免费模型额度覆盖日常成本。按当前插件调用结构估算，在私聊、群聊观察、日程、梦境、记忆整理、关系网、自登记和 Token 监控等功能全开的情况下，通常每天消耗约 `1M tokens` 左右。

如果使用火山方舟协作计划，可以直接把 `Doubao-Seed-2.0-pro` 设置为主模型；在每日 `2M tokens` 免费额度内，通常足够覆盖本插件的日常运行。免费额度、模型名称和平台政策可能变化，实际以火山方舟控制台展示为准。

## 可选联动

下面这些插件或服务不是必需项。没有安装时，本插件会自动跳过对应能力或回退成普通文字。若存在 `menglimi` 维护版，建议优先使用 `menglimi` 版本，和本插件的联动适配通常更完整。

### 屏幕陪伴

- 用途：支持主动 `screen_peek` 轻窥屏、主动后沉默时额外窥屏、屏幕状态上下文、天气能力回退。
- 首选仓库：<https://github.com/menglimi/astrbot_plugin_screen_companion>
- 对应配置：`enable_screen_glance_action`、`screen_peek_max_daily`、`screen_peek_cooldown_minutes`、`enable_unanswered_screen_peek_followup`、`unanswered_screen_peek_after_minutes`、`unanswered_screen_peek_cooldown_minutes`

### TTS 语音

- 用途：支持主动 `voice` 短语音，并兼容 `<tts>...</tts>`、日语、双语或特殊 TTS 人格规则。
- 首选仓库：<https://github.com/menglimi/astrbot_plugin_tts_modify-fishaudio->
- 原始仓库：<https://github.com/L1ke40oz/astrbot_plugin_tts_modify>
- 对应配置：`enable_voice_action`、`voice_action_max_chars`

### ComfyUI 生图

- 用途：支持主动 `photo_text` 图片分享，可根据日程、梦境、当前场景生成图片。
- AstrBot ComfyUI 插件仓库：<https://github.com/cjxzdzh/astrbot_plugin_comfyui>
- ComfyUI 官方仓库：<https://github.com/comfyanonymous/ComfyUI>
- 对应配置：`enable_photo_text_action`、`photo_generation_backend`、`COMFYUI_TEXT2IMG_WORKFLOW_NAME`、`COMFYUI_SELFIE_WORKFLOW_NAME`

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

联动方式是软依赖：陪伴插件只负责判断“现在是不是适合无聊刷一下”和“这条视频要不要分享”，真正的视频获取、观看分析、点赞/评论/收藏行为仍由 B 站 Bot 插件自己的配置决定。未安装或未启动 B 站 Bot 时，陪伴插件会自动跳过该能力。

## 扩展页介绍

本插件提供 AstrBot 官方 Pages 扩展页：

```text
pages/陪伴面板/
```

如果当前 AstrBot 版本支持 `context.register_web_api()`，插件会注册后端接口：

```text
/astrbot_plugin_private_companion/page/*
```

扩展页主要用于把“看不见的陪伴状态”可视化：

- 总览私聊对象、群聊观察、名单模式、LivingMemory 状态和 Token 消耗。
- 查看单个私聊用户的启用状态、称呼、语气、关系状态、今日主动计数和下次主动候选。
- 查看用户记忆、对话片段、未完成话头、主动计划和能力额度。
- 查看群气氛、黑话、话题线、群聊片段、插话反馈和关系网摘要。
- 管理群聊关系网：QQ 身份节点、别名、曾见群名片、资料正文、身份说明、互动边界和重要记忆。
- 查看关系网识别结果：群详情会显示已识别成员数量；关系节点命中时日志会显示注入了哪些用户资料。
- 启停单个私聊或群聊对象。
- 保存用户称呼、语气、名单配置和关键功能开关。
- 重置今日额度、清空主动计划或清空学习记忆。
- 查看各类 LLM 任务的 Token 用量、调用次数、失败记录和近期待优化点。
- 配置分项模型 Provider，例如回复自检、关系分析、记忆整理、群聊黑话释义和生图提示词模型。

扩展页适合排查：

- 为什么某个用户今天没有收到主动消息。
- 群聊上下文有没有学习到。
- 图片、语音、识屏额度是否用完。
- 某个模型任务是否消耗过高。
- Bot 当前日程、梦境、创作或状态为什么影响了回复。

## 实现原理

插件由几层状态和决策链组成。

### 1. 全局生活状态层

每天会生成或维护：

- 拟人状态。
- 今日日程。
- 当前时间段细化。
- 梦境和梦境碎片。
- 日记。
- 私下创作项目。
- 重要日期。
- 昨日完整对话摘要。

这些信息不是回复正文，而是供私聊、群聊和主动行为共同参考的“生活底座”。

### 2. 私聊用户层

每个目标用户都有独立状态，包括：

- 是否启用陪伴。
- 昵称和语气偏好。
- 今日主动次数和最近主动时间。
- 最近用户消息和最近陪伴消息。
- 关系分数、关系状态和忽略次数。
- 记忆、表达学习、对话片段和未完成话头。
- 图片、识屏、语音等主动能力的每日额度。

这些状态会持久化保存，重启后继续延续。

### 3. 主动判定层

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

### 4. 主动内容与行为层

主动内容生成时会明确告诉模型：这是 Bot 主动开口，不是用户刚刚发来消息。历史对话只作为关系和话题背景，不能误当作当前用户输入。

模型会先判断这次更适合：

- 普通文字。
- 图片加一句话。
- 轻窥屏后再说。
- 短语音。
- 戳一戳。
- 从群聊公开片段私聊转述。
- 从 B 站观看日志私聊分享。
- 从私下创作节点轻轻提起。

执行层会再次检查能力可用性和额度，避免模型想用但实际不能用。

### 5. 被动回复增强层

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

### 6. 群聊观察层

群聊层默认按白名单或黑名单工作。它会静默学习目标群内公开信息，包括：

- 常见词和黑话。
- 群友轻画像。
- 当前气氛。
- 话题线。
- 群聊片段。
- 插话反馈。
- 群友关系网。
- QQ 关系节点。

群聊上下文与私聊记忆隔离。插件不会把私聊关系、私下称呼或私人记忆带进群聊。群聊主动插话默认关闭，需要明确开启。

### 7. QQ 关系网识别层

关系网以 QQ 号作为唯一稳定身份锚点，群昵称、群名片和别名只作为称呼或“被提及”线索。

群聊回复前会按顺序注入：

- 当前发言者 QQ 精确命中的节点。
- 当前消息明确提到的已保存名称、别名或曾见群名片。
- 最近发言者 QQ 精确命中的节点。

每个关系节点可以保存资料正文、身份说明、互动边界和重要记忆。重要记忆主要由 Bot 后续生成或沉淀，扩展页负责查看、停用和删除。

未登记成员在群里 @Bot 或明确叫到 Bot，并说“我是 XX / 我叫 XX / 你可以叫我 XX”时，插件可以自动建立节点，并用模型生成一段简短人物印象填入资料正文。

自登记会拒绝明显整活和冒领，例如超过六个字的称呼、亲属/亲密关系冒领、权限身份冒领、谐音变体、辱骂词，以及冒领已有关系节点名称或别名。被拦截时只回复：

```text
你是小猪
```

## 常见问题

### 为什么没有主动发消息？

先发送：

```text
陪伴 查看主动判定
```

重点检查：

- `target_user_ids` 是否包含当前用户。
- `max_daily_messages` 是否已经用完。
- 当前时间是否处于 `quiet_hours`。
- 用户是否刚刚发过消息，还没有达到 `idle_minutes`。
- 距离上次主动是否小于 `min_interval_minutes`。
- 用户状态是否被暂停，或关系状态处于回退。
- 主动计划是否被清空后还没重新安排。

### 为什么群聊没有学习上下文？

检查：

- `enable_group_companion` 是否开启。
- 当前群是否在 `group_whitelist_ids` 中，或是否被 `group_blacklist_ids` 排除。
- `group_access_mode` 是否符合预期。
- `enable_group_context_injection` 是否开启。
- 群内消息是否足够多。

### Bot 怎么知道群里提到的是谁？

关系网会优先按 QQ 号确认当前发言者。若触发回复的消息里明确出现已保存的名称、别名或曾见群名片，会自动注入对应关系节点，并标记为“被提及”。这只表示消息提到了这个人，不会把被提到的人误判为当前发言者。

命中用户资料时日志会显示类似：

```text
群聊关系网注入用户信息: group=群号 sender=触发者QQ users=QQ:名称[confirmed/当前发言者 QQ 精确匹配]
```

没命中时不会写这条日志。

### 自登记为什么没生效？

检查：

- `enable_worldbook_member_recognition` 是否开启。
- `worldbook_self_registration` 是否开启。
- 用户是否已经有关系节点；已有节点不会被覆盖。
- 消息是否明确 @Bot 或叫到 Bot。
- 是否使用了“我是 XX / 我叫 XX / 你可以叫我 XX”这类表达。
- 名称是否超过六个字，或命中防整活/防冒领规则。

### 会不会泄露私聊记忆到群里？

设计上会尽量避免。私聊记忆和群聊观察分层处理，群聊只使用当前群公开上下文。启用 LivingMemory 协同时，群聊也只提示召回当前群相关记忆。

### 会不会刷屏？

正常配置下不会。插件有每日主动上限、最小间隔、免打扰时间、用户活跃检测、关系状态回退、群聊插话间隔和能力额度。建议一开始把 `max_daily_messages` 设为 2 到 5，稳定后再调整。

### 为什么图片没有发出来？

检查：

- `enable_photo_text_action` 是否开启。
- `photo_generation_backend` 是否设置正确。
- ComfyUI 插件或外部图片 API 是否可用。
- 工作流名称是否填写。
- `photo_action_max_daily` 是否达到上限。
- 当前平台是否支持发送本地图片。

注意：`photo_action_max_daily = 0` 表示不限制，不是禁用。

### 为什么识屏、语音或戳一戳没有触发？

检查：

- 对应能力开关是否开启。
- 对应联动插件是否安装并启用。
- 当前平台是否支持目标动作。
- 每日额度或冷却时间是否已经触发。

### 小说创作会不会变成用户指定剧情？

不会。创作者是 Bot。用户反馈只能作为读后观感或灵感参考，插件提示词会避免让用户决定故事走向。

### 可以只用文字，不开图片语音识屏吗？

可以。图片、语音、识屏、戳一戳、QQ 状态同步都是可选能力。不开启时，插件仍能完成日程、状态、记忆、群聊观察、被动回复增强和普通文字主动陪伴。

## 开发者信息

- 开发者：`menglimi`
- 插件仓库：<https://github.com/menglimi/astrbot_plugin_private_companion>
- 插件版本：`2.2.0`
- 主要文件：
  - `main.py`：插件主体、主动判定、回复注入、群聊观察、能力执行。
  - `planning.py`：日程与规划相关逻辑。
  - `dreaming.py`：梦境生成与梦境碎片。
  - `page_api.py`：扩展页后端 API。
  - `pages/陪伴面板/`：扩展页前端。
  - `_conf_schema.json`：AstrBot 配置项。
  - `metadata.yaml`：插件元数据。

本插件面向长期陪伴体验。建议在测试新能力时先降低主动频率，并优先确认文字、日程、状态、记忆和群聊边界稳定后，再逐步开启图片、语音、识屏、戳一戳、B 站联动等真实外部动作。
