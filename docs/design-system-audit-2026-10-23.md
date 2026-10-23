# 设计系统审计（Codex gpt-6.1-sol，2026-10-23，只读静态分析）

# 1. 当前视觉语言盘点

**建议：建立一套共享品牌与状态语义、分别适配竖屏应用和横屏牌桌密度的设计系统。** 先统一颜色、字体、边框与交互状态，再整理组件；牌桌几何布局单独迁移。

本次为源码静态审计，覆盖指定样式、组件、页面、布局、构建配置及截图脚本；未修改文件、未运行构建或生成截图、未执行 git 命令。以下视觉判断需在后续迁移中通过实际渲染验收。

`docs/PRD.md` 仍描述早期单页 EV 工具，与当前账号、好友邀请、三模式产品存在差距；当前界面范围应以源码和 `README.md` 为准。

### 颜色：两套金色、多套绿色并存

`frontend/src` 的 Vue/CSS 文件中扫描到 **223 个不同十六进制字面量**；展开短写并剥离 alpha 后为 **193 个基础 RGB**，另有 Tailwind 色阶和 `rgba()`。

下表按用途归组；带透明度的颜色展示基础 RGB，不能据此直接丢弃原 alpha。部分颜色跨多个角色复用。

| 色族／角色 | 当前十六进制值 | 主要位置 |
|---|---|---|
| 应用墨绿、输入、选中背景 | `#06221D #06221E #082A23 #092C25 #092C27 #092D28 #0A3028 #102E25 #10382F #112C22 #12392F #123E32 #123E35 #164537 #173F30 #174D3B #1A4939 #225445 #245747` | `style.css`、`App.vue`、`HomeModeSelect.vue`、`UpdateBanner.vue` |
| 牌桌、HUD、弹层深绿 | `#042C28 #043A32 #052E2B #052E2C #062B29 #06372D #063A34 #063B32 #063B34 #07201F #075044 #082E2A #082F2B #0B3933 #0B4035 #0B433D #103F35 #115643 #174E40 #17604C #18362C #183B39 #25594A #28695B #357A65 #368A75 #3D806D #41786D` | `PvEBoard.vue`、`PvEDiscardHud.vue`、结算／牌谱组件 |
| 绿色边框、牌背、浅绿辅助色 | `#153F34 #185D4C #438D72 #5EEAD4 #63BB9A #7AB5A6 #7BD4B3 #87B39B #8BBDA7 #8EB5A5 #90B2A0 #9EBCAC #A0C6AD #A3B5A6 #A6CDB5 #A7CFC5 #A8C8BF #ADD0BD #AEC7B7 #B1C8B3 #B1D0BC #B2CBB5` | 牌背、边界、计时器、次要文字 |
| 品牌金、铜金、金色边框 | `#B48B25 #B7862C #BCA572 #BEA779 #C6B378 #C7A555 #C9B26C #CBB571 #CE9C67 #CFB477 #D4AF58 #D5B16A #D5B36B #D5B875 #D5B980 #D6B955 #D7B16A #D7BD86 #D7C794 #D7C795 #D9B65C #E1C88D #E5BD42 #E5C986 #E8C972 #E9CC89 #EDCC78` | 大厅主按钮、品牌印章、HUD、弹层描边 |
| 亮金、暖金文字与高亮 | `#DFD0A1 #F3D6A3 #F4D88E #F4DFAC #F4E1B0 #F5D68B #F6CE66 #FBBF24 #FCD34D #FDE68A #FFE2A0` | 财神、推荐、行动提示、当前玩家、结算 |
| 金棕底、金色深文字 | `#422006 #49350D #57411C #63512F #695018 #6B501C #785510` | 亮色按钮文字、金色卡片／徽标底 |
| 温润牌面、暖白、米色 | `#CABFA3 #D4CBB8 #D6C9AC #D8D4BB #E3D5AE #ECE9D8 #F4F0E5 #F5EDD8 #F8EBD0 #FEF3C7 #FFF2D4 #FFF6D5 #FFF7D6 #FFF7E1 #FFFBEB #FFFDF0 #FFFDF1 #FFFEF6` | `MahjongTile.vue`、`TileArtwork.vue`、牌面预览及结算 |
| 红色状态、危险、印章及牌面红 | `#542C32 #743A37 #7F1D1D #8C3C2B #B4232D #B52C35 #BE123C #FB7185 #FDA4AF #FFB6AF #FFD1D8 #FFD4D4 #FFE2DF #FFE4E6` | 错误、危险、负分、自摸／操作强调、万子与鸟雀 |
| 成功／正收益绿、牌面绿 | `#145F42 #146B46 #177247 #86EFAC #BBF7D0 #D1FAE5` | 正分、收益、条子、發字 |
| 蓝色提示、时间池、牌面蓝 | `#0C4A6E #123E48 #185A91 #214E87 #225C91 #5CC8ED #B8EDFF #BAE6FD` | 加时、牌注记、筒子与白板 |
| 紫色／中性分类 | `#C4B5FD #475569 #94A3B8 #E2E8F0 #E5E7EB` | 结算分类、次要数据、禁用／中性状态 |
| 正文、辅助文字及牌面深墨 | `#173D42 #18352D #B0C7B8 #B1C9BF #B4C8BF #B7CBBF #B7D8CC #B8C6B3 #B8CBBF #BACBBF #BDE1D5 #C3D3C9 #C4CAAA #C9DDD3 #CBD5D1 #D5E8DE #E1F7EF #EDF3E8 #EEF3E9 #F3F6EF #F4F5E8 #FFFFFF` | 全局文字、说明、浅色表面文字 |
| 阴影与遮罩 | `#000000 #001911 #001A16 #001B17 #001C19 #020F0D` | 阴影、结算／牌谱遮罩、房间解散弹层 |

透明度使用较碎：如 `#FBBF24` 有 `1F/30/3B/40/55/66/70/77/80/88/A0/AA` 等变体，另与 `rgba(251,191,36,…)` 并存。`rgba()` 还引入 `#FFD700` 金、`#10201C` 深绿等值，应纳入后续映射表。

**Tailwind 色族完整范围：**

| 色族 | 当前使用色阶 | 典型值／含义 |
|---|---|---|
| amber | 50、100、200、300、400、500、600、800、900、950 | `#FBBF24` 主按钮／高亮；`#FDE68A` 标题；`#422006` 深文字 |
| yellow | 300、400 | `#FDE047 #FACC15`，金色渐变与光晕 |
| teal | 50、100、200、300、400、500、600、700、800、900、950 | `#134E4A #042F2E`，背景、边框和辅助文字 |
| emerald | 50、100、200、300、400、500、700、800、900、950 | `#022C22 #10B981`，背景、成功和当前行动 |
| rose | 50、100、200、300、400、500、600、700、800、900、950 | `#FB7185 #E11D48`，危险、负分及强操作 |
| red | 700 | `#B91C1C`，红中字 |
| sky | 50、100、200、300、400、500、900、950 | `#38BDF8 #0EA5E9`，操作分类、摸牌标记 |
| violet | 50、100、200、300、400、500、700、800、900、950 | `#A78BFA #4C1D95`，副露／计分类别 |
| fuchsia | 50、100、200、300、400、500、600、700、800、900、950 | `#D946EF #86198F`，财神标记、插位操作 |
| lime | 300 | `#BEF264`，拖放目标 |
| slate | 100、200、400、500、600、700、800、900、950 | `#94A3B8 #0F172A`，中性数据、背景、禁用态 |

### 字体、形状、阴影与间距

| 维度 | 当前实现 | 问题与建议 |
|---|---|---|
| 正文 | 主要继承 Tailwind Preflight 默认 sans 栈；大厅 16px／1.6 | 未显式统一中文系统字体；建议固定正文栈 |
| 品牌 | `HomeModeSelect.vue`：`'Noto Serif SC','Songti SC',SimSun,serif`；大厅标题只写 `serif` | 未发现配套字体加载；跨 Windows、Android、iOS 字形差异明显 |
| 牌字 | `MahjongTile.vue` 使用 serif；筒条为原创 SVG | 保留独立牌字角色；不要把 SVG 填色误映射为 UI 状态色 |
| 字号 | 大厅 14／16／20／28；模式标题 44；牌桌大量 8–13px | 牌桌字号还会经过缩放，需按最终屏幕像素验收 |
| 数字 | `SeatClock.vue` 等已有 `tabular-nums` | 推广到积分、余牌、倒计时 |
| 圆角 | Tailwind 4／6／8／12／16／24／full；自定义 3／5／7／9／10／11／13／14／18／20 等 | 统一通用圆角；牌面、微型徽标保留专用尺寸 |
| 阴影 | Tailwind shadow 系列；`0 24px 70px #000A` 弹层；牌砖 `2px 3px 0 #B2CBB5` | 普通抬升、弹层、牌砖厚度、状态光晕应分四类 |
| 间距 | 大厅 20px 页边、18px 内容 gap、14px stack、12px row、7px label | 尚无统一尺度；可收敛至 4px 基础，保留少量 2px 微间距 |
| 牌桌间距 | 手牌 gap 5px、摸牌分隔 16px；牌河 3px；大量绝对坐标 | 属于游戏几何，不能机械归整到大厅间距尺度 |

### 组件模式与主要不一致

- **按钮**：大厅 `.primary` 为 `#C7A555`，牌桌常用 amber-400／500 渐变；危险、自摸、推荐的颜色含义交叉。
- **卡片**：大厅是 16px 圆角实色卡；模式入口用渐变；牌桌有透明区域、紧凑 HUD、亮金推荐卡。
- **弹层**：存在 body Teleport、舞台内覆盖、1080×560 缩放弹层、内联确认卡以及 `window.confirm()`。
- **牌**：共用 `MahjongTile.vue`，但 HUD／结算仍有局部牌面绘制；对手暗手使用简化 `.tile-back`。
- **状态**：财神既用金也用 fuchsia；当前行动既用金也用 emerald；蓝色同时承载摸牌、操作分类和加时。
- **交互**：大厅已有焦点环及 44px 按钮，牌桌存在小型文字按钮；disabled opacity 分布在 `.3–.55`。
- **动效**：已有局部 reduced-motion 支持，但尚无跨组件统一策略。
- **层叠**：标签、HUD、弹层、开局仪式分别使用多组 z-index，最高可见 2000／全屏容器 9999；需按 stacking context 整理。

# 2. 设计系统必须覆盖的 UI 表面与组件类型

以下组件路径均相对于 `frontend/src/`。

| 类型 | 必须覆盖的现有页面／组件 |
|---|---|
| 应用与游戏容器 | `layouts/AppShell.vue`、`layouts/TableShell.vue`、`App.vue`；安全区、滚动锁、旋转、全屏 |
| 页面与品牌入口 | `views/HomeView.vue`、`components/HomeModeSelect.vue`、`TileDesignPreview.vue` |
| 身份与设置 | `AuthForm.vue`、Login／Register／Settings 页面；账号、注册码、密码、昵称、版本与更新 |
| 社交与邀请 | Friends／FriendRequests／InviteMatch 页面；好友行、搜索结果、邀请卡、固定底部操作 |
| 候场 | `MatchWaitingView.vue`、`PvpLobby.vue`；席位、AI／房主标记、准备、连接状态、开局倒数 |
| 导航 | 底部四标签、返回链接、模式选择、分段选择／标签、页内展开与返回 |
| 按钮 | 主／次／幽灵／危险／图标／链接／牌局动作；默认、hover、pressed、focus、busy、disabled |
| 表单 | 文本／密码／数字输入、select、checkbox、switch、range、单选组、校验与帮助文字 |
| 卡片与列表 | 普通／品牌／可点击／选中卡、好友行、牌谱行、排名行、空态和加载态 |
| 弹层与抽屉 | `PveStartDialog.vue`、`GameHistoryModal.vue`、`GameOverModal.vue`、`PvECircleSummary.vue`；确认、详情、EV drawer |
| 牌与牌组 | `MahjongTile.vue`、`TileArtwork.vue`、`MeldTiles.vue`、`MeldBar.vue`、`TilePicker.vue`；横置、暗牌、财神、替身、摸牌、选中、禁用 |
| 手牌与输入 | `HandBar.vue`、`GodViewHandStrip.vue`、`DiscardPool.vue`；槽位、拖放、插位、理牌、数量约束 |
| 牌桌与席位 | `PvEBoard.vue`、`OpponentPanel.vue`、`GodViewTable.vue`、`DiscardRiver.vue`；四方向、暗手、副露、牌河 |
| HUD 与状态 | 中央罗盘、财神槽、余牌、玩家身份、积分条、轮次条、局势提示、网络重连 |
| 时钟 | `SeatClock.vue`、`PvpResponseWait.vue`；运行、暂停、加时、紧急、中立等待、隐私隐藏 |
| 决策与数据 | `ActionPrompt.vue`、`PvEDiscardHud.vue`、`ResultCard.vue`、`PlayerWorkbench.vue`；推荐、候选、指标、表格 |
| 胜负与仪式 | `SelfWinBanner.vue`、`SelfWinSettlement.vue`、`GameOverModal.vue`、`PvECircleSummary.vue`、`GodOpeningCeremony.vue` |
| 通知反馈 | `UpdateBanner.vue`、inline alert、banner、status、toast／复制成功；目前未发现统一 toast 组件 |

所有组件需明确：加载、空、错误、断线、不可操作、长文本、键盘焦点及减少动效状态。PvP 另需定义“信息不可见”状态，不能仅用颜色遮蔽敏感内容。

# 3. Token 架构与 Tailwind 接入

### 三层命名与推荐色板

采用 `--dl-p-*` 原始值 → `--dl-s-*` 语义 → `--dl-c-*` 组件变量。业务模板使用语义，组件内部使用组件变量；原始色仅在 token 文件引用。

| 语义 | 推荐值 | 用途 |
|---|---|---|
| `surface-canvas / panel / input` | `#06221D / #10382F / #082A23` | 统一大厅与游戏周边基础表面 |
| `surface-table / table-glow` | `#052E2C / #17604C` | 保留牌桌专属材质与渐变 |
| `surface-raised / interactive / selected` | `#123E32 / #164537 / #1A4939` | 弹层、普通按钮、选中背景 |
| `accent / accent-hover / accent-soft` | `#C7A555 / #D5B875 / #FDE68A` | 品牌主操作与标题 |
| `game-highlight` | `#FBBF24` | 财神、当前动作、推荐的受控强调 |
| `text-primary / muted / on-accent` | `#EEF3E9 / #B0C7B8 / #102E25` | 正文、说明、金底文字 |
| `border-subtle / strong` | `#A0C6AD` 的约 19%／33% | 卡片边界、输入边界 |
| `danger / success / info` | `#FDA4AF / #86EFAC / #BAE6FD` | 深色表面状态文字；各配专用深背景 |
| `tile-face / shade / edge / ink` | `#FFFEF6 / #ECE9D8 / #CABFA3 / #173D42` | 牌面材质 |
| `tile-art-red / green / blue` | `#B52C35 / #146B46 / #214E87` | 原创 SVG 牌面色，独立于状态色 |

**取舍：** 哑金用于品牌和常规 CTA，亮金保留给牌局焦点，能维持现有辨识度；全部改成哑金会削弱小尺寸提示，全部使用亮金则会放大视觉噪声。推荐高亮还需结合“荐／得／轮到你”等文字和形状。

### Tailwind 3 接入示意

以下仅为建议代码，未写入工作区。颜色通道采用空格分隔 RGB，兼容 `bg-accent/20`：

```css
/* src/styles/tokens.css */
:root {
  color-scheme: dark;
  --dl-p-gold-500: 199 165 85; /* #C7A555 */
  --dl-p-green-950: 6 34 29;   /* #06221D */
  --dl-p-green-900: 16 56 47;  /* #10382F */
  --dl-s-accent: var(--dl-p-gold-500);
  --dl-s-surface-canvas: var(--dl-p-green-950);
  --dl-s-surface-panel: var(--dl-p-green-900);
  --dl-c-button-primary-bg: var(--dl-s-accent);
}
```

```js
// frontend/tailwind.config.js：保留现有 content、gridTemplateColumns
theme: {
  extend: {
    colors: {
      accent: 'rgb(var(--dl-s-accent) / <alpha-value>)',
      surface: {
        canvas: 'rgb(var(--dl-s-surface-canvas) / <alpha-value>)',
        panel: 'rgb(var(--dl-s-surface-panel) / <alpha-value>)',
      },
    },
  },
}
```

普通 CSS 使用 `background:rgb(var(--dl-c-button-primary-bg));`。不要用 `var(--hex-color)` 配合 `<alpha-value>`，也不要全局重定义 Tailwind `amber`／`teal`：同一旧色已承载多个含义。

### 非颜色 token 与文件布局

- **字体**：正文建议 `system-ui,-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif`；品牌与牌字分别定义 serif 栈。首轮保留现有度量，字体统一单独验收。
- **圆角**：通用 4／8／12／16／20／pill；牌面仍按尺寸计算，保留小徽标特例。
- **间距**：2／4／8／12／16／20／24／32；竖屏按钮 ≥44px、输入 ≥48px。舞台组件另设 compact 尺寸。
- **效果**：`shadow-panel / modal / tile / emphasis`；`motion-fast / normal / ceremony`；reduced-motion 只减少表现，不改变开局或行动时序。
- **层级**：按“舞台内部”和“视口覆盖”分别命名；在盘点 stacking context 后映射现有 z-index。
- **深色策略**：`:root` 固定深色，不跟随系统亮暗切换；浅色牌面显式指定背景、文字和必要的 `color-scheme:light`。

```text
frontend/src/styles/tokens.css       # primitive + semantic
frontend/src/styles/components.css   # @layer components，通用组件皮肤
frontend/src/styles/app-shell.css    # 竖屏布局与密度
frontend/src/styles/table-stage.css  # 舞台几何、缩放相关规则
frontend/src/styles/patterns.css     # 装饰规则与变量
frontend/src/assets/patterns/*.svg   # 本地矢量纹样
frontend/src/components/ui/*.vue     # 按需抽取 Button/Card/Dialog/Field/Toast
frontend/src/style.css               # 统一入口，保留 Tailwind 指令
docs/design-system.md                # token、状态、模式及例外规范
```

公共颜色放根节点，避免 Teleport 到 `body` 后丢失变量；密度修饰类需同时传给弹层根节点。不要让全局 `button`／`input` 规则覆盖牌桌控件。

# 4. 国风纹样的具体落点

| 组件／位置 | 建议纹样 | 可读性约束 |
|---|---|---|
| `HomeView.vue` `.hero` 右上、右下留白 | 云纹 | 约 3–5% 不透明度，避开标题、说明和邀请按钮 |
| `HomeModeSelect.vue` `.brand-seal` 内框、卡片端部 | 回纹、印章角饰 | 装饰集中在编号侧或箭头侧 |
| `AppShell.vue` 品牌栏底部 | 细回纹分隔带 | 不进入账号状态文字和底部导航触控区 |
| `AuthForm.vue` 介绍区外围 | 窗棂角饰 | 不铺在输入框、错误信息、密码可见按钮下 |
| `MatchWaitingView.vue` 席位卡四角 | 简化窗棂 | 房主、准备、离线状态仍使用纯色清晰底 |
| `PvEBoard.vue` 外围空白、中央 HUD 外缘 | 稀疏云纹、回纹框 | 牌河、手牌、副露、计时器下方保持干净 |
| `MahjongTile.vue` `.tile-back-face` | 连续牌背纹／万字纹 | 所有隐藏牌保持同一纹样、方向规则和明暗，不携带身份线索 |
| `PvEBoard.vue` 简化 `.tile-back` | 同源牌背纹的低细节版本 | 小尺寸下避免密纹摩尔纹；允许退化成纯色 |
| `GameOverModal.vue` 标题两侧、`PvECircleSummary.vue` 排名区外框 | 云纹、回纹 | 分数、支付明细、横置牌后方留纯色 |
| `GameHistoryModal.vue` 标题栏边缘 | 回纹细线 | 列表行和复盘步进区不铺纹 |
| `GodOpeningCeremony.vue` halo 外圈 | 云纹圆环 | 保留财神牌和说明的独立高对比区域；支持静态版本 |

纹样使用本地 SVG／CSS 背景或伪元素，`pointer-events:none`；装饰元素标记 `aria-hidden`。建议线宽从舞台逻辑 1–2px 试起，以缩小后的结果验收。计时器、危险提示、toast、表格及可见牌面不增加底纹。

# 5. 分步迁移计划与贡献清单

| 顺序 | 文件范围 | 具体工作／完成条件 |
|---|---|---|
| 1. 固化基线 | `docs/design-system.md`；核对 `frontend/scripts/*.mjs`、`frontend/tests/*` | 建立颜色→角色映射；记录三模式、候场、结算、复盘和错误状态截图矩阵；区分既有失败与迁移回归 |
| 2. 引入 token | 新建 `styles/tokens.css`；修改 `style.css`、`tailwind.config.js` | 先用等值变量替换，保留旧色、透明度与几何；确认 opacity utility 正常生成 |
| 3. 迁移竖屏 | `style.css`、`layouts/AppShell.vue`、`AuthForm.vue`、`UpdateBanner.vue`、`views/*.vue` | 统一按钮、卡片、表单、导航、反馈；验证安全区、键盘、长昵称和固定底部按钮 |
| 4. 迁移牌与公共皮肤 | `MahjongTile.vue`、`TileArtwork.vue`、`MeldTiles.vue`、`MeldBar.vue`、`TilePicker.vue`、`DiscardRiver.vue`、`DiscardPool.vue`、`TileDesignPreview.vue` | 先迁移材质与颜色；保留 SVG、横置、厚度和所有尺寸覆盖 |
| 5. 迁移牌桌状态 | `App.vue`、`PvEBoard.vue`、`PvpGameTable.vue`、`SeatClock.vue`、`PvpResponseWait.vue`、`HandBar.vue`、`OpponentPanel.vue`、`GodView*.vue` | 统一行动、财神、危险、拖放及隐私状态；核对四座位视角和三模式信息边界 |
| 6. 迁移决策与弹层 | `ActionPrompt.vue`、`PvEDiscardHud.vue`、`ResultCard.vue`、`SelfWin*.vue`、`GameOverModal.vue`、`GameHistoryModal.vue`、`PvECircleSummary.vue`、`PveStartDialog.vue`、`PvpLobby.vue`、`GameConfig.vue` | 建立 banner／drawer／dialog 变体；保留 Teleport、返回键和确认语义；逐步统一原生 confirm |
| 7. 整理布局与装饰 | `App.vue`、`layouts/TableShell.vue`、新建 shell／stage／patterns 样式及 SVG | 等值搬迁布局后再加纹样；每次只改变一个视觉维度；独立验收字体和尺寸调整 |
| 8. 清理与验收 | 上述文件、`README.md`、`docs/design-system.md`；必要时更新脚本 | 移除旧硬编码；记录允许例外、组件用法及截图基线；完成 Web、移动构建和真机检查 |

### 1280×720 舞台的重点风险

- `App.vue` 强制舞台 1280×720；内部 `.pve-game-main` 又采用 **83.333333% 尺寸 × `scale(1.2)`**。新增 padding、边框、字号都会放大影响。
- 固定布局包括 **36px 顶栏、94px 手牌区、697px 手牌锚点、44×59px 手牌**，以及 31.74px 牌河、34.385px 副露宽度等精细尺寸；首轮不得取整。
- `GameHistoryModal.vue`、`PvECircleSummary.vue` 是独立 **1080×560** overlay，边距 16、最大缩放 1；不能套用普通舞台样式。
- `useOrientation.js` 在物理视口中先处理安全区再旋转缩放。避免再次给内部容器叠加物理安全区补偿。
- 新增包装节点会影响 `> :first-child`、`> div:last-child`、`:has()`、`display:contents` 规则；优先替换变量，之后再抽组件。
- 财神飞行动画读取舞台矩阵与目标槽位；祖先新增 transform、改变定位上下文或重排目标会导致落点偏移。
- 缩放后的真实触控尺寸需单独评估；舞台内逻辑 44px 不保证最终屏幕达到 44px。

### UI contribution checklist

- [ ] 使用语义／组件 token；新原始色说明角色与必要性。
- [ ] 指定 app／stage 密度；覆盖加载、禁用、错误、焦点和长文本。
- [ ] 状态同时有文字或图形提示；检查实际背景上的文字与控件对比度。
- [ ] 牌面艺术色与 UI 状态色分离；隐藏牌不产生额外视觉线索。
- [ ] 保留三模式、四座位、横竖屏、安全区及 PvP 隐私约束。
- [ ] 弹层验证焦点进入／返回、Esc／Android 返回、滚动锁和 Teleport 样式。
- [ ] 装饰不遮挡点击或数据；减少动效不改变业务时序。
- [ ] 运行适用检查并附前后截图；将既有失败与本次变化分别记录。

# 6. Capacitor 与视觉回归兼容性

### Capacitor／资源构建

- 当前链路为 `mobile.js → main.js → style.css`。样式入口应保持共享，避免只在 Web 入口引入 token。
- `vite.config.js`：Web 生产 base 为 `/DingLongMahjong/`，mobile 为 `./`，输出为 `dist-mobile`；`capacitor.config.ts` 的 `webDir` 同为 `dist-mobile`。
- 纹样、字体应通过源码 import 或相对 `url()` 交给 Vite 打包；新增 `/assets/...` 根路径可能导致子路径部署或 App 资源加载失败。
- 不改动 HTML 中供 mobile 插件替换的 `/src/main.js` 入口字符串；不改变 viewport 的 `viewport-fit=cover`。
- `index.html`、`capacitor.config.ts`、`src/platform/native.js` 均有 `#06221D` 背景配置。原生配置和 meta 不能直接读取 CSS token；应记录同步值或以后增加一致性校验。
- CSS 变量方案本身无需新增原生能力；字体／纹样应本地可用，避免离线首屏变化。不要把 CSS 搬成浏览器无法处理的 JS import。
- `build` 的 prebuild 和 `build:mobile` 会生成语音数据，`cap:sync` 还会写入原生工程；本次只读审计没有运行这些命令。
- 后续构建需配置合适的 `VITE_API_BASE_URL`；生产缺失值、mobile API 地址不合约束的失败应与样式问题分开判断。

### `frontend/scripts` 回归风险

- 这些脚本主要是 **Chrome CDP 几何／交互断言加截图产物**；抽查未见统一的像素差异基线机制，不能把“生成截图”视为视觉验收通过。
- 需保留或有计划地迁移 `.game-stage`、`.pve-hand-anchor`、`.mahjong-tile`、`.action-prompt-panel`、`data-action`、`data-position`、`aria-label` 等选择器契约。
- `pve-stage-smoke.mjs`、`table-mobile-smoke.mjs` 检查舞台尺寸、横竖屏一致性、内容边界和 `elementFromPoint()` 命中；纹样覆盖层必须不拦截点击。
- `status-hint-smoke.mjs` 检查单行文字、无裁切、与手牌不重叠；换字体、字号或 padding 都可能触发真实布局回归。
- `pve-worst-case.mjs`、`pve-landscape.mjs`、`pve-zoom-review.mjs` 应覆盖满手、副露、长牌河、操作面板及结算；保留原有尺寸矩阵。
- **先核对旧脚本可执行性**：`pvp-unified-smoke.mjs` 等仍查找 `#pvp-nickname`／房间号入口；当前路由已是账号好友邀请制。`pve-visual-check.mjs` 仍断言筒条 `.characters` 文本，而当前为 `TileArtwork` SVG。这些可能在迁移前已失效。
- 多个脚本读取 Vue 根实例的 `setupState`，部分直接从开发服务器导入组件；抽组件、重构根状态或改为预览服务器可能使测试夹具失效。
- `README.md` 记录过结算横置牌测试失败；该记录不能替代当前实测。迁移前先确认现状，再判断是否需要调整断言。
- 脚本会创建浏览器 profile、截图及 artifacts，因此本次未运行。后续还需补竖屏登录／好友／设置与 Capacitor 真机验收。

