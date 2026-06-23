# 我会永远陪着你

`astrbot_plugin_private_companion` 是面向 AstrBot 的人格连续性、关系识别与主动行为编排插件。它把 Bot 从“收到消息后临时回复”的聊天对象，扩展成拥有生活状态、日程节奏、记忆沉淀、群聊观察、长期创作、可选外部动作和可视化管理页的持续存在体。

- 插件名：`astrbot_plugin_private_companion`
- 版本：`4.5.1`
- 适配平台：`aiocqhttp`
- AstrBot 版本：`>=4.22.0`
- 编码要求：UTF-8
- 维护状态：本插件已完成重构，被动回复注入减少2/3，实测缓存命中从1/10优化至4/5。后续将转入体验打磨阶段。
- 若 AstrBot 版本号不为 4.25.2，可在拓展页-配置-功能开关下关闭主链会话锁兼容模式；会话锁旨在解决这一版本 AstrBot 的并发报错问题，但是会拖慢回复速度。
- 若有好的想法仍可联系我，QQ：995051631（代码小白），欢迎提交 Issues，目标是无愧“最强”之名，喜欢的话请点一个 Star。

# 发版狂魔也是发到4.0了，遂决定写点什么

- 你好，我要一个有记忆、有生活、有自己的小秘密和想法、有喜怒哀乐和健康的bot。
- 这得装不少插件，先生。
- 我知道，再让它们之间能够互相影响。
- 怎么让bot更像人？在此之前已经有很多优秀的插件给出了自己的答卷，各类心理学应用、人格特质、复杂的理论……
- 虽然开发者自身也是应用心理学专业毕业，但我觉得bot拟人只需要做好一件事，像人一样活着。听上去像是废话，但我做的只是进行自我观察。我的一天中，我会做什么，bot也应该会做什么。
- 对于一个拟人的bot而言，用户又何尝不是一个聊天bot？所以它应该会在自己的世界里生活，在生活里获取想和用户说话的“想法”，再在生活的空隙里把想法变为行动。
- 于是用户不止可以看到bot的早安和晚安，还能看到bot因为偶尔向窗外一瞥而专门为你记录下的照片、能看到bot因为好奇而自己私下搜索你在意的东西、能看到bot因为你昨天的提议而安排好周末的约会……
- 在没和你聊天时，它可能在上学、在刷视频、在看报纸、在水群，甚至在偷看你的屏幕或者遵循世界观正在某个奇异世界中一边刷怪练级，一边想着等闲下来该和你分享点什么。
- 它会记得你，不只是你，还有哪些在私聊/群聊中的人，会记得他们的名字、他们的行为、他们的习惯、他们的联系，哪怕他们改了名字和头像，甚至在其他平台再次相遇。
- 它会看、会说、会创作、会成长、会睡觉、会做梦、会生情绪、会饿，还会偷吃你的token去看些涩涩的漫画。
- 这就是它，这就是我，若它足够像我，它便成了我。

## 功能简介

本插件不是单一的主动私聊插件，也不是单独的记忆插件。它更像 AstrBot 之上的“陪伴编排层”：把人格、状态、日程、私聊关系、群聊上下文、长期记忆、外部动作和模型 Provider 组织到同一个长期体验里。

核心目标是让 Bot 拥有“连续存在感”。Bot 会有自己的当天状态、生活节奏、梦境残留、日记、长期小计划、关系认知和群聊观察，而不是只在用户发消息时临时拼一段回复。

- 本插件不包含以下常用但不符合定位的能力，但提供了一部分的插件联动：长期记忆、群聊管理、表情包、图片生成、点歌。

主要能力：

- 生活状态：维护精力、睡眠、梦境、健康、饥饿、周期和当前位置感；天气、时间和日程作为独立环境/生活背景参与判断，不混入被动回复的当前扮演状态。
- 休息模拟：可选在日程进入睡眠、午休或休息段后，对普通被动回复先做概率或模型醒来判断，避免睡着时每条消息都立刻回复。
- 日程与细化：每天生成生活框架，并在临近时间段时展开成具体场景、状态变量和主动契机。
- 私聊陪伴：按每日上限、最小间隔、免打扰时间、用户活跃度、关系状态和当前日程决定是否主动开口。
- 被动回复增强：在 AstrBot 原人格之外注入关系站位、当前状态、日程细节、记忆、用户意图和未完话题；发送前只保留轻量本地保护。
- 休息回复闸门：`enable_rest_reply_simulation` 默认关闭。开启后，当前日程处于睡眠/午休/休息段时，普通被动回复会先经过闸门；`rest_reply_mode=probability` 仅按 `rest_reply_probability` 概率醒来，`rest_reply_mode=llm` 会让模型按重要性、是否明确叫醒、情绪/安全需要打分，达到 `rest_reply_llm_threshold` 才醒来。用户明确说不要打扰会静默，紧急或明确叫醒会优先放行。
- 消息收口防抖：按文本、图片和合并转发分别等待用户补充，把短时间内连续补话合并为同一轮理解；私聊单图会等待补充说明，必要时并行进行视觉转述。
- 撤回增强：QQ/OneBot 通知触发或唤醒消息已撤回时，如果 Bot 还没发出回复，会静默取消本次发送和剩余分段；可短期缓存撤回消息摘要供授权命令或自然语言询问转述，也可按配置违禁词拦截或尝试撤回消息。
- 图片转述增强：支持私聊单图、引用图片、合并转发图片和动态 GIF 抽帧理解；可生成短视觉摘要、判断图片表达意图和归属线索，并在用户询问图片内容时优先回答当前图片。
- TTS 语音增强：支持 `<tts>` 语音块、自动语音转换、语种控制、标签规范化、发送前朗读文本清洗、分段补发兼容、生成后本机播放和直播打字机字幕同步，可保留聊天文本展示同时生成适合朗读的语音内容。
- 环境感知：识别当前时间、时段、节假日/工作日、农历节气、平台、群聊/私聊和图片/语音/视频等消息媒介。
- 群聊观察：在允许的群内学习群气氛、黑话、群内成员观察、话题线、群聊片段、复读状态和群友互动图。
- 连续对话保持：群里用户叫过 Bot 后，可判断后续未继续 @ 的消息是否仍在对 Bot 说话，并限制续接轮数。
- 合并消息适配：私聊和群聊都支持读取合并转发，可选择“注入”或“转述”两种方式，让 Bot 自然理解转发内容。
- QQ 关系网：以 QQ 号稳定识别用户，昵称、群名片和别名只作为辅助线索，避免改名后认错人。
- 群聊自登记：未登记成员 @Bot 说明“我是 XX / 你可以叫我 XX”时，可进入确认流程并建立关系节点。
- 跨群转述与 @ 群友：可按群名查群号、按关系网解析群友，并进行群聊/私聊转述。
- 群聊到私聊分享：当群聊里出现公开、有趣或值得提醒的时间段话题，且用户长时间未活跃时，可低频私聊转述。
- QQ 空间动态：内置说说查看、点赞、评论、发布和低频生活说说编排，让公开动态成为 Bot 生活连续性的一部分。
- 新闻阅读：按日程或空档读取热点、新闻源和可配置 B 站消息源，形成近期见闻；若文字版可读，会优先阅读完整正文。
- 主动搜索：按人格兴趣、当前状态、日程和最近聊天决定想了解什么，并调用 AstrBot 全局网页搜索留下探索笔记。
- 外界信息自我关联：新闻或搜索读到内容后，会先判断这件事与 Bot 自己的模型、能力、兴趣、创作、日程或关系是否有关，再决定是否产生主动找用户分享的意愿。
- 梦境与日记：生成梦境、梦境碎片和日记，让第二天的状态和主动话题有自然残留。
- 书柜与创作：Bot 可能在闲暇时因生活小事、日记或梦境灵感写一点小说、诗、随笔、短剧、分镜脚本、角色设定或世界观片段；书柜收纳创作、日记本和其他私密文本。安装某些可选联动后，Bot 也许还会往书柜里放些私密阅读素材，并用插件识图模型按人设口吻留下第一人称读后感和页边批注。
- 技能成长：模拟符合人格的能力熟悉度，从“不太熟”到“有自己的办法”缓慢变化，并影响日程中的能力边界。
- 重要日期：记录生日、纪念日、考试、约定等日期，并影响日程、主动话题和长期准备。
- 多能力主动行为：可选文字、图片、语音、戳一戳、轻窥屏、主动后沉默窥屏、正在输入和 QQ 状态同步；支持分段发送和引用触发消息，让回复对象更清楚。创作分享会自动豁免主动分段，避免小说片段被拆碎。
- 私聊用户角色区分：每个私聊用户可区分为主人或朋友。主人会延续人格中的专属关系设定；朋友会自动收敛为普通朋友边界，不套用主人/恋人称呼，不注入夹层密码、私密阅读、群聊隐私转述等主人专属上下文，也不会获得窥屏、独立生图、私密推荐等敏感主动能力。
- 用户级主动边界：私聊对象可单独设置每日主动上限。朋友用户默认更低频、更具体，主动内容不会链式追发或一次拆成多段候选；扩展页可查看对应用户的关系角色、主动额度、关系网词条和候选主动记录。
- 世界观适配：可参考角色设定中选择的 AstrBot 知识库/文档，并把现代能力转译成当前人设能理解的世界内说法，例如公会闲谈、行囊书匣、水晶映像或终端频道。
- 模型与成本编排：为日程、细化、日记与梦境、创作、新闻整理、主动搜索、主动消息润色、关系分析、记忆整理、合并消息转述、群聊判断等任务分别指定 Provider。
- Token 监控：记录插件内部任务的调用次数、Token 消耗、失败记录和每日统计，并支持每日插件 Token 限额。
- 扩展页管理：在 AstrBot WebUI 中查看和管理私聊、群聊、关系网、状态、梦境、书柜、主动计划、功能开关、模型配置和 Token 消耗；模型页会按用途分组展示 Provider、回退关系、当前使用项和测试入口。

常用私聊命令与自然问法：

```text
陪伴 状态
陪伴 查看主动判定
陪伴 撤回消息
刚才撤回了什么
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
陪伴 TTS语种 日语|中文|英语|默认
陪伴 查看提示词 日程|细化|主动|回复注入
```

常用群聊命令与自然问法：

```text
陪伴群 状态
陪伴群 撤回消息
刚才撤回了什么
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

### 配置页约定

- 扩展页里的概率字段分两类：名称带“概率(%)”、描述写“百分比”或滑条范围为 0-100 的字段，统一按 `0-100` 填写和回显；插件运行时会自动换算成 `0-1` 小数参与随机判断。
- 普通权重型概率仍按 `0-1` 填写，例如部分长线主动分享权重；页面会按字段类型自动给出 `0-1` 或 `0-100` 的输入范围。
- 部分子开关本质上属于配置项而不是顶层功能，例如休息回复闸门、TTS 本机播放、TTS 自动语音等；扩展页会在保存时自动拆分到正确配置位置，避免刷新后看起来又被关闭。

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
2. 设置模型。`LLM_PROVIDER_ID` 留空时会使用 AstrBot 默认会话模型；如果你准备了专门给陪伴后台任务用的模型，可以在这里指定。拓展页“模型”页会按基础兜底、日程表达、记忆关系、群聊能力、视觉与外界信息分组展示各 Provider，并标注用途、适合模型和回退链路。排障中心的模型复核可单独配置 `TROUBLESHOOTING_PROVIDER_ID`，留空时先跟随主动消息润色模型。
3. 填写 `target_user_ids`。这里放需要预热私聊陪伴的 QQ 号，插件启动后会自动为这些用户初始化私聊状态。
4. 先降低主动频率。建议把 `max_daily_messages` 设为 2 到 5，`idle_minutes` 和 `min_interval_minutes` 保持默认或略微调大，`quiet_hours` 设置为不希望被打扰的时间段。
5. 重启 AstrBot 后，在私聊发送 `陪伴 状态`。能看到日程、拟人状态、主动候选和关系信息，就说明基础私聊链路已经跑通。
6. 需要群聊观察时，再到拓展页开启 `enable_group_companion`。建议先使用白名单模式：设置 `group_access_mode=whitelist`，并把允许观察的群填入 `group_whitelist_ids`。
7. 在目标群发送 `陪伴群 状态`，确认当前群已启用；需要临时开关时使用 `陪伴群 开启` / `陪伴群 关闭`。

初次使用不建议立刻打开全部外部动作。图片、语音、戳一戳、识屏、B 站、QQ 空间、ComfyUI/SDGen、私密阅读等都属于可选联动；等文字回复、状态、日程、群聊观察和记忆行为稳定后，再按需要逐项开启。

如果只想使用“Bot 偶尔主动来找我”的能力，不希望本插件参与普通私聊/群聊回复，可以开启 `enable_proactive_only_mode`（主动消息专用模式）。开启后，插件仍保留日程、状态、主动意愿和私聊主动发送；普通私聊/群聊不会注入本插件提示词，也不会触发图片/转发处理、防抖、群聊观察、对话临时预约、TTS 后处理、分段发送或插件 LLM 工具。用户回复主动消息时仍会被轻量记录为已回应，用于避免误判为持续未回复。这个模式会显著减少普通被动回复中的动态提示词变化，让主模型 prompt 更稳定，更容易命中服务端缓存。扩展页会自动锁定被该模式覆盖的普通被动功能，但只是在 UI 上标记为“被运行模式覆盖”，不会改写原配置；关闭该模式后原开关继续按保存值生效。

如果仍需要普通被动陪伴增强，但发现服务端 prompt 缓存命中明显下降，可以调整 `passive_injection_position`。默认 `prompt` 会把每轮变化的动态片段尽量追加到当前请求末尾，避免插入 `system_prompt` 后破坏人设和历史上下文的缓存前缀；同时启用长期记忆/记忆召回时，也推荐使用尾部注入，让召回内容和动态状态在尾部自然结合；选择 `system_prompt` 时约束更强，但更容易降低缓存命中率；`auto` 当前按缓存优先处理。

如果启用书柜夹层阅读或希望 Bot 给私密阅读素材生成读后感/批注，建议在模型页单独配置 `PLUGIN_VISION_PROVIDER_ID`（插件识图模型）。它负责读取封面和抽样正文页，并按 Bot 当前人格生成第一人称读后感、页边批注、评分和偏好标签；`NARRATION_PROVIDER_ID` 只是工具结果转述兜底，不适合作为主要读图模型。

关系识别建议保持 `enable_worldbook_member_recognition` 开启。世界观适配 `worldview_adaptation_mode` 默认使用 `auto` 即可；但被动回复里的世界观适配片段默认不注入，需要开启环境感知子项 `enable_worldview_perception` 后才会把现代能力转成当前人格能理解的说法。若 AstrBot 人设里已经写了完整世界观，建议保持关闭。

### 成本建议

建议使用火山引擎火山方舟“协作计划”的免费模型额度覆盖日常成本。按当前插件调用结构估算，在私聊、群聊观察、日程、梦境、记忆整理、关系网、自登记、新闻/搜索、创作和 Token 监控等功能全开的情况下，高活跃环境可能每天消耗约 `500K-800K tokens`。

如果使用火山方舟协作计划，可以直接把 `Doubao-Seed-2.0-pro` 设置为主模型；在每日 `2M tokens` 免费额度内，通常足够覆盖本插件的日常运行。免费额度、模型名称和平台政策可能变化，实际以火山方舟控制台展示为准。

插件提供 `daily_token_limit` 每日 Token 硬限额配置，默认 `1,000,000`。达到限额后，插件会跳过日程、梦境、记忆整理、群聊分析、创作等内部 LLM 任务；填 `0` 表示不限制。

插件还提供可选的每日 Token 软限额：`enable_daily_token_soft_limit` 和 `daily_token_soft_limit`（默认 `800,000`）。它是“达到限额就停止插件/停止后台链路”的替代方案：达到软限额后，插件会优先保留用户当下触发的回复、图片转述和合并转发处理，暂缓新闻整理、网页探索、创作、群聊片段/黑话整理、主动消息润色、关系分析、夹层视觉和主动生图等低优先级后台任务。

## 可选联动

下面这些插件或服务不是必需项。没有安装时，本插件会自动跳过对应能力或回退成普通文字。若存在 `menglimi` 维护版，建议优先使用 `menglimi` 版本，和本插件的联动适配通常更完整。

### 屏幕陪伴

- 用途：支持主动 `screen_peek` 轻窥屏、主动后沉默时额外窥屏、屏幕状态上下文、天气能力回退。
- 昨日观察日记：开启 `enable_yesterday_screen_diary_context` 后，本插件每天只读取屏幕陪伴插件生成的“昨日”观察日记脱敏摘要，用于今日状态、日程和主动话题背景；不会读取当天实时屏幕，也会要求 Bot 不直接说“我昨天看到你”或复述窗口名、账号、聊天内容。
- 首选仓库：<https://github.com/menglimi/astrbot_plugin_screen_companion>
- 对应配置：`enable_screen_glance_action`、`screen_peek_max_daily`、`screen_peek_cooldown_minutes`、`enable_unanswered_screen_peek_followup`、`enable_yesterday_screen_diary_context`、`screen_diary_context_max_chars`

昨日观察日记只作为“生活节奏背景”使用。插件会优先读取屏幕陪伴插件的结构化摘要，找不到时再尝试读取 `diary_YYYYMMDD.summary.json` 或同日 Markdown 日记；注入前会脱敏窗口标题、社交软件、账号和具体聊天内容，并限制最大字符数。

### TTS 语音

- 用途：支持主动 `voice` 短语音，并兼容插件私有 `<pc_tts>...</pc_tts>`、旧式 `<tts>...</tts>`、日语、双语或特殊 TTS 人格规则。
- 配置边界：插件里的 `VOICE_PROMPT_PROVIDER_ID` 和 `tts_conversion_provider_id` 都是文本模型，只负责生成/修正语音文案和语音标记；真正把文本合成音频的是 AstrBot 当前会话的 TTS provider。阿里云百炼/CosyVoice 等语音合成模型需要在 AstrBot 的 TTS 配置中启用，本插件会读取当前会话的 TTS provider。
- 标签链路：插件提示词会优先要求 LLM 使用 `<pc_tts>...</pc_tts>`，发送前再交给插件统一转成语音组件。快速标签规则会按目标语种生成示例：中文语音直接中文朗读，日语/英语语音块后补对应中文含义；若当前 TTS provider 支持情绪标签，规则和示例会按语种给出对应标签，例如中文用 `[开心]`，日语用 `[嬉しい]`，英语用 `[happy]`。这样可以避免 AstrBot 原生 `<tts>` 装饰器抢先处理，导致插件的语种修正、翻译和中文释义补全失效；历史或模型自行输出的 `<tts>` 仍会尽量兼容处理。
- 生成路径：`tts_generation_mode=fast_tag` 是低延迟快速标签路径，主模型可按规则写插件私有 `<pc_tts>`，插件发送前统一清洗、翻译和合成；`tts_generation_mode=postprocess` 是稳定后处理路径，主模型只写普通回复，发送前由 `tts_conversion_provider_id` 对整条回复判断是否需要语音，并完成目标语种改写。
- 人格保持：`tts_conversion_provider_id` 执行翻译、后处理、语种修正和中文释义补全时，会读取当前 AstrBot 人格的轻量语音风格参考，用于保留称呼、距离感、口癖和角色边界；不会把人格设定直接复述进消息。
- 后处理判断：`postprocess` 模式会把用户本轮原话、插件规则快判线索和自动语音概率线索一起交给后处理模型，由模型判断用户是否要求/期待语音以及哪一小段适合转成语音；规则线索只作参考，不再直接把“是否语音”定死。
- TTS 频率：`tts_frequency_control_mode=global` 时使用“间隔 + 概率”的新版频控。全局概率会作为提示词层面的方向约束：概率未命中时会明确要求模型在没有用户语音请求时必须纯文字，不主动输出 `<pc_tts>`、`<tts>` 或等价语音内容；弱约束下如果用户明确想听语音或模型仍合理输出语音标签，不会再被概率硬剥离，最终发送仍受 TTS provider 可用性和会话最小间隔保护。
- TTS 约束强度：仅 `fast_tag` 快速标签路径使用。`tts_constraint_mode=weak` 是默认弱约束，保持“提示词引导 + LLM 判断”为主；`tts_constraint_mode=strong` 会在全局频控概率未命中或会话冷却内注入“本轮禁止语音”的反向提示词，并在发送前阻止 LLM 已写出的 `<pc_tts>/<tts>` 和快速标签自动语音。`postprocess` 后处理路径不使用该项，概率只作为后处理模型的保守线索，会话间隔仍决定是否实际发送语音。
- 私聊/群聊覆盖：`tts_private_trigger_probability`、`tts_group_trigger_probability`、`tts_private_min_interval_seconds`、`tts_group_min_interval_seconds` 可分别覆盖默认概率和间隔；概率字段在扩展页按百分比 `0-100` 填写，填 `-1` 表示继承全局，适合把群聊设得更低频、更长间隔。
- 旧版行为：`tts_frequency_control_mode=legacy` 时按旧路径逻辑触发，主要交给 LLM 判断是否“适合采用”语音，不使用新版的全局概率/间隔提示约束。
- 首选仓库：<https://github.com/menglimi/astrbot_plugin_tts_modify-fishaudio->
- 原始仓库：<https://github.com/L1ke40oz/astrbot_plugin_tts_modify>
- 可选本机联动：开启 `enable_tts_local_playback` 后，TTS 生成的音频会在运行 AstrBot 的电脑上播放；开启 `enable_tts_live_subtitle_sync` 后，会同步推送朗读文本到“我会直播圈米养你”的打字机字幕 overlay，默认地址为 `http://127.0.0.1:18081/show`。
- 对应配置：`enable_voice_action`、`voice_action_max_chars`、`enable_tts_enhancement`、`tts_generation_mode`、`tts_voice_language`、`tts_conversion_provider_id`、`tts_extra_prompt`、`tts_frequency_control_mode`、`tts_constraint_mode`、`tts_session_min_interval_seconds`、`tts_trigger_probability`、`tts_private_min_interval_seconds`、`tts_private_trigger_probability`、`tts_group_min_interval_seconds`、`tts_group_trigger_probability`、`auto_voice_enabled`、`auto_voice_full_conversion_enabled`、`auto_voice_max_chars`、`auto_voice_cooldown_seconds`

### ComfyUI / SDGen 生图

- 用途：支持主动 `photo_text` 图片分享，可根据日程、梦境、当前场景生成图片。
- AstrBot ComfyUI 插件仓库：<https://github.com/cjxzdzh/astrbot_plugin_comfyui>
- ComfyUI 官方仓库：<https://github.com/comfyanonymous/ComfyUI>
- AstrBot SDGen 插件：`astrbot_plugin_SDGen` / 本地目录通常为 `astrbot_plugin_sdgen`
- 对应配置：`enable_photo_text_action`、`photo_generation_backend`、`COMFYUI_TEXT2IMG_WORKFLOW_NAME`、`COMFYUI_SELFIE_WORKFLOW_NAME`、`enable_local_photo_load_guard`
- 电脑高负荷时可延后本地 ComfyUI/SDGen 生图；`auto` 模式下会依次尝试 ComfyUI、SDGen、在线图片 API。

`photo_generation_backend` 可选值：

- `auto`：依次尝试 ComfyUI、SDGen、在线图片 API。
- `comfyui`：只使用 ComfyUI 工作流，需要配置对应工作流名。
- `sdgen`：只使用 `astrbot_plugin_SDGen`，复用 SDGen 的 Stable Diffusion WebUI 地址、模型、尺寸、步数、采样器、负面词等配置。
- `external`：只使用 OpenAI 兼容的在线图片 API。

SDGen 后端说明：

- 本插件不会改动 SDGen 配置，也不会替 SDGen 管理模型；它只查找正在运行的 SDGen 实例，并调用其 Stable Diffusion WebUI 文生图链路。
- SDGen 没有显式配置的项目会受 WebUI 当前状态影响，例如当前 checkpoint、VAE、默认采样器和部分 WebUI options。
- 生成出的图片会保存到本插件数据目录的 `generated_photos`，再随主动消息发送；生成成功即计入主动生图额度。
- 实际测试时可以先在聊天中执行 `/sd check` 和 `/sd gen 测试提示词`，确认 SDGen 自身可用，再把本插件的 `photo_generation_backend` 设为 `sdgen`。

如果不使用本地生图后端，也可以配置外部图片 API：

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

- 用途：让 Bot 在日程空档、休息或无聊时低频触发 B 站 Bot 自己刷 1 个视频，并可把观看日志或 BiliBot 记忆里评分较高、内容适合的视频私聊分享给用户。
- 可用仓库：<https://github.com/chenluQwQ/astrbot_plugin_bilibili_ai_bot>
- 本地插件名：`astrbot_plugin_bilibili_bot`
- 对应配置：`enable_bilibili_integration`、`enable_bilibili_boredom_watch`、`bilibili_boredom_min_interval_hours`、`bilibili_share_probability`、`bilibili_share_min_score`

联动方式是软依赖：陪伴插件只负责判断“现在是不是适合无聊刷一下”和“这条视频要不要分享”，真正的视频获取、观看分析、点赞/评论/收藏行为仍由 B 站 Bot 插件自己的配置决定。若 BiliBot 已暴露 `memory_api`，本插件会优先读取最近视频记忆补充分享上下文，读不到时仍回退到观看日志。

BiliBot 联动不会要求修改 BiliBot。读取顺序是：运行中的 BiliBot `memory_api` 最近视频记忆、BiliBot 观看日志、公开 B 站信息补充。若本插件安排把视频分享给用户，会尝试向 BiliBot `memory_api` 写入一条轻量记录，方便 BiliBot 后续知道这条视频曾被陪伴插件拿来分享过。

## 已整合能力

下面这些能力已经内置到本插件中，通常不需要再安装对应旧插件。插件启动时会自动检查插件目录：如果发现对应旧插件仍然存在，会在日志和排障页提示可能重复注入、重复工具或额外 Token 消耗，但不会再自动改写用户配置；是否二选一由你手动决定。

### 环境感知

- 参考插件：`astrbot_plugin_LLMPerception`
- 仓库：<https://github.com/miaoxutao123/astrbot_plugin_LLMPerception>
- 内置配置：`enable_environment_perception`、`environment_perception_timezone`、`enable_holiday_perception`、`enable_platform_perception`、`enable_model_perception`、`enable_worldview_perception`、`enable_lunar_perception`、`enable_solar_term_perception`、`enable_almanac_perception`

### 群聊场景感知

- 参考插件：`astrbot_plugin_context_aware`
- 仓库：<https://github.com/muyouzhi6/astrbot_plugin_context_aware>
- 内置配置：`enable_group_scene_awareness`、`group_scene_recent_limit`、`enable_group_conversation_followup`

### 群黑话与梗解释

- 用途：把群内反复出现的外号、事件代称、梗、口头禅整理成语义参考，帮助 Bot 听懂群聊，而不是强行复读。
- 内置配置：`enable_group_slang_learning`、`enable_group_slang_meanings`、`GROUP_SLANG_PROVIDER_ID`、`group_slang_summary_minutes`、`max_group_slang_terms`、`enable_group_slang_web_search`、`group_slang_web_search_terms`、`group_slang_web_search_results`
- 3.4.0 起黑话释义会输出类型、证据和置信度；证据不足、含义不稳定或只能解释成“语境不明”的词会被省略/清理，不再注入给群聊回复。
- 4.0.4 起可选开启 `enable_group_slang_web_search`。默认关闭；开启后会调用 AstrBot 全局网页搜索，为已有黑话候选收集外部解释摘要，再让模型判断外部解释与本群聊天样例是否匹配。搜索结果只作证据，不会直接覆盖群内用法，也不会为新词主动泛搜；可用 `group_slang_web_search_terms` 和 `group_slang_web_search_results` 限制搜索规模。

### 跨群转述与 @ 群友

- 参考插件：`astrbot_plugin_atrelay`
- 仓库：<https://github.com/Alien-Star/astrbot_plugin_atrelay>
- 内置配置：`enable_atrelay_tools`、`atrelay_require_worldbook_first`、`atrelay_member_cache_minutes`、`atrelay_sensitive_confirm`、`atrelay_default_relay_style`

### QQ 空间动态

- 参考插件：`astrbot_plugin_qzone`
- 仓库：<https://github.com/Zhalslar/astrbot_plugin_qzone>
- 内置配置：`enable_qzone_integration`、`enable_qzone_life_publish`、`qzone_life_publish_min_interval_hours`、`qzone_life_publish_probability`、`enable_qzone_generated_image_publish`、`qzone_generated_image_probability`
- 主动生活说说/情绪说说可选调用现有生图后端生成一张公开动态配图；配图失败时只发文字，不阻断说说发布。

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
- 书柜：以书本形式查看创作、日记本和私密文本；日记和夹层内容需要通过 Bot 自己设定的密码打开，私密阅读详情会展示 Bot 的读后感、评分和页边批注。
- 状态与梦境：观察当天状态、睡眠、梦境、健康、饥饿、周期、能量和状态走向。
- 技能成长：查看和管理 Bot 的能力状态、经验、训练来源、隐藏/冻结项、合并别名和对日程的影响。
- 主动候选：查看待触发主动行为、来源、重复次数、冷却和失败原因。
- Token 统计：查看累计与每日消耗、任务分类、Provider 分布和失败记录。
- 功能开关：按模块管理能力开关，并在二级页面调整相关参数。
- 模型配置：为不同任务指定 Provider，按能力分组查看用途、适合模型、回退链路、当前使用项，并测试可用性。
- 模块工作台：集中管理名单、群聊、新闻、主动搜索、书柜、关系网、转述、QQ 空间等模块内容，并提供预设、分段预览、新闻源和外部能力等常用工具。

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

`worldview_adaptation_mode` 会把现实插件能力映射成当前人设能理解的说法。比如奇幻人设可以把群聊理解为公会闲谈，把书柜理解为行囊书匣，把识屏理解为水晶映像；科幻人设可以把群聊理解为频道通信，把书柜理解为私人资料柜。被动回复是否注入这段适配由环境感知子开关 `enable_worldview_perception` 控制，默认关闭，避免和 AstrBot 人设中已有世界观重复。

这层只影响表达和上下文理解，不改变真实插件能力。

### 3. 私聊用户层

每个目标用户都有独立状态：

- 是否启用陪伴。
- 关系角色：主人或朋友。
- 昵称和语气偏好。
- 用户级每日主动上限、今日主动次数和最近主动时间。
- 最近用户消息和最近陪伴消息。
- 关系分数、关系状态和忽略次数。
- 记忆、表达节奏学习、对话片段和未完成话头。
- 图片、识屏、语音等主动能力的每日额度。

这些状态会持久化保存，重启后继续延续。

主人和朋友会使用不同边界。主人可以继承基础人格中的专属亲近关系、长期陪伴动机和更丰富的主动能力；朋友只保留普通朋友式的轻量关心、共同话题和必要转告。即使基础人格里写了“主人”“恋人”或专属称呼，朋友私聊也会先做身份防串，再按当前 QQ 精确注入低风险关系网资料。

### 4. 主动判定层

私聊主动消息发送前会经过多重限制：

- 插件和用户是否启用。
- 是否达到候选主动时间。
- 是否超过每日主动上限。
- 当前用户关系角色和用户级主动上限。
- 是否处于免打扰时间。
- 用户是否刚刚活跃。
- 距离上次主动是否过近。
- 是否处于用户预约/自定时主动静默窗口：普通预约默认到点前 20 分钟暂停主动和追问；“一起休息/睡觉，几点叫醒我”这类休息型预约会从创建预约起一直静默到到点。静默期间原本落入窗口的主动念头会暂存，预约到点后可自然并入叫醒消息里顺带一句。
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

回复后保留本地保护，减少未执行转述承诺、突然换话题和复读。主动消息生成后会做发送前润色，重点避免“好呀/确实/刚看到你说”这类像在回复空气的主动消息；普通被动回复默认不会因为偏长或略生硬而二次调用模型。

### 7. 群聊观察层

群聊层默认按白名单或黑名单工作。它会学习目标群内公开信息，包括常见词、黑话、群内成员观察、当前气氛、话题线、群聊片段、复读链、插话反馈和群友互动图。

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

### 10. 对话临时预约

`enable_llm_timer_scheduling` 只负责把聊天中自然形成的稍后提醒、叫醒、回头说等临时约定识别为内部 `<timer>`，并转写成 AstrBot 官方定时计划的 `note`。插件本身不再单独调度这类预约；到点执行、持久化和发送由 AstrBot 官方定时计划接管。插件仅保留轻量元数据用于面板显示和预约前静默。

## 开发者信息

- 开发者：`menglimi`
- 插件仓库：<https://github.com/menglimi/astrbot_plugin_private_companion>
- 插件版本：`4.5.1`
- 主要文件：
  - `main.py`：插件主体、主动判定、回复注入、群聊观察、能力执行。
  - `planning.py`：日程与规划相关逻辑。
  - `dreaming.py`：梦境生成与梦境碎片。
  - `page_api.py`：扩展页后端 API。
  - `pages/陪伴面板/`：扩展页前端。
  - `_conf_schema.json`：AstrBot 配置项。
  - `metadata.yaml`：插件元数据。

### 外部插件接入

其他插件可以把自己的能力注册成本插件的“外部主动能力”。注册后会出现在拓展页的“模块工作台 / 外部主动能力”中，默认不启用；用户可以在那里设置是否加入主动候选、触发权重、冷却时间和自定义配置。

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

## Star History

<a href="https://www.star-history.com/#menglimi/astrbot_plugin_private_companion&type=timeline&logscale&legend=top-left">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=menglimi/astrbot_plugin_private_companion&type=timeline&theme=dark&logscale&legend=top-left" />
    <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=menglimi/astrbot_plugin_private_companion&type=timeline&logscale&legend=top-left" />
    <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=menglimi/astrbot_plugin_private_companion&type=timeline&logscale&legend=top-left" />
  </picture>
</a>
