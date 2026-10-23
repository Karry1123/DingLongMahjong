# 顶龙麻将设计系统 v1 · 墨绿 · 温玉 · 鎏金

> 这是前端所有界面改动必须遵守的标准。新功能、改版、修 bug 时涉及样式，先读本文，再看 `frontend/src/styles/` 下的令牌与组件类。方案页（含效果图）：https://claude.ai/artifact/3UivvUgsxhuUkEgJy1p9GM ；审计报告：`docs/design-system-audit-2026-10-23.md`。

## 0. 原则

1. **颜色只来自令牌。** 组件里禁止出现 `#xxxxxx` 字面量、`rgb()/rgba()` 字面量，以及 Tailwind 自带色名（amber / yellow / teal / emerald / rose / red / sky / violet / fuchsia / lime / slate / gray 等）。只能用 `var(--*)` 或 `tailwind.config.js` 里映射的 ink / felt / gilt / highlight / ivory / jade / cinnabar / indigo / bamboo / fog 色名。
2. **三层令牌。** 原子色（primitive）只在 `tokens.css` 出现；页面与组件用语义令牌；只有跨多处复用、需要局部覆盖的组件才设组件令牌。
3. **单一深色主题。** `:root { color-scheme: dark }`，不跟随系统亮暗。牌面、结算卡等浅色表面显式写背景与文字色。
4. **两套金分工。** 哑金 `gilt`（#C7A555 系）做品牌、主按钮、回纹、弹窗描边、标题；亮金 `highlight`（#FBBF24）**只**用于牌桌焦点：财神标记、推荐出牌、轮到你。亮金不得出现在竖屏壳。
5. **牌面艺术色与 UI 状态色分离。** 万朱砂 / 筒靛青 / 条竹绿 / 中發白用 `--tile-*` 令牌；危险、成功、信息用 `--danger / --ok / --info`。两组不互相引用。
6. **纹样是结构不是贴纸。** 每种纹样只出现在固定位置（见第 4 节），透明度上限 12%，牌桌中央区域、计时器、危险提示、toast、表格、可见牌面永远不加底纹。装饰元素 `pointer-events:none` + `aria-hidden="true"`。
7. **舞台几何不归整。** 1280×720 舞台内的绝对坐标、`.pve-game-main` 的 83.33% × scale(1.2)、手牌 44×59px、牌河 31.74px 等尺寸不因设计系统取整；改牌桌样式不新增包装节点，不给祖先加 transform。

## 1. 令牌

文件：`frontend/src/styles/tokens.css`。颜色令牌以**空格分隔的 RGB 通道**存储，便于 Tailwind `<alpha-value>` 与 CSS `rgb(var(--x) / .5)`。

### 1.1 原子色 primitive

| 色族 | 令牌 | 值 |
|---|---|---|
| 墨绿 ink | `--ink-950 / 900 / 800 / 700 / 600 / 500 / 400` | #041A16 / #06221D / #0B2F28 / #10382F / #164537 / #1E5443 / #2E6B55 |
| 呢绒 felt | `--felt-600 / 500 / 400` | #185D4C / #1F6E5A / #2B8068 |
| 鎏金 gilt | `--gilt-700 / 600 / 500 / 400 / 300 / 200` | #8F6B2A / #B08A3D / #C7A555 / #D9BC74 / #EAD39B / #F5E7C2 |
| 亮金 highlight | `--highlight-500 / 400 / 300` | #FBBF24 / #FCD34D / #FDE68A |
| 玉白 ivory | `--ivory-50 / 100 / 200 / 300 / 400` | #FFFEF6 / #F6F1E1 / #ECE6D2 / #D8CFB4 / #B9AE8F |
| 青玉 jade | `--jade-400 / 300 / 200` | #5EC8A3 / #86E0BF / #BFEFD9 |
| 朱砂 cinnabar | `--cinnabar-600 / 500 / 400 / 200` | #A4232A / #C0392F / #E05A4E / #F5B5AC |
| 靛青 indigo | `--indigo-600 / 500 / 300` | #174F85 / #1F6BA6 / #7FB6E8 |
| 竹绿 bamboo | `--bamboo-600 / 500` | #166B43 / #1F8A57 |
| 雾灰 fog | `--fog-100 / 300 / 400 / 500 / 600` | #EEF3E9 / #C8D6CC / #A9BDB1 / #86A092 / #5F7A6C |
| 金棕 bronze（金底上的深字） | `--bronze-900` | #1A2A12 |

### 1.2 语义色 semantic

| 令牌 | 指向 | 用途 |
|---|---|---|
| `--bg` | ink-900 | 页面、壳子底 |
| `--bg-sunken` | ink-950 | 输入框、代码块、下沉区 |
| `--bg-raised` | ink-700 | 卡片、面板 |
| `--bg-interactive` | ink-600 | 次级按钮、可点击行 |
| `--bg-selected` | ink-500 | 选中态底 |
| `--bg-overlay` | ink-950 @ 78% | 弹窗遮罩 |
| `--table-felt` / `--table-felt-deep` / `--table-felt-glow` | felt-500 / ink-800 / felt-400 | 牌桌渐变三点 |
| `--fg` / `--fg-muted` / `--fg-faint` | fog-100 / fog-400 / fog-600 | 正文 / 次要 / 禁用 |
| `--fg-on-accent` | bronze-900 | 金底上的文字 |
| `--fg-on-paper` | #173D42（`--paper-ink`） | 玉白底上的文字 |
| `--accent` / `--accent-hover` / `--accent-soft` / `--accent-line` | gilt-500 / gilt-400 / gilt-500 @ 14% / gilt-500 @ 45% | 品牌强调 |
| `--highlight` | highlight-500 | 牌桌焦点，仅舞台内 |
| `--line` / `--line-strong` | fog-400 @ 16% / @ 34% | 分隔线、描边 |
| `--ok` / `--warn` / `--danger` / `--info` | jade-400 / gilt-400 / cinnabar-400 / indigo-300 | 状态 |
| `--ok-soft` / `--danger-soft` / `--info-soft` | 对应色 @ 16% | 状态底 |
| `--paper` / `--paper-2` / `--paper-edge` | ivory-50 / ivory-200 / ivory-300 | 结算卡、横幅纸面 |

### 1.3 组件令牌 component

| 令牌 | 指向 |
|---|---|
| `--tile-face` / `--tile-face-2` / `--tile-edge` / `--tile-shadow` / `--tile-ink` | ivory-50 / ivory-200 / #CABFA3 / #B2CBB5 / #173D42 |
| `--tile-wan` / `--tile-tong` / `--tile-tiao` | #B4232D / #185A91 / #177247 |
| `--tile-zhong` / `--tile-fa` / `--tile-bai` | #B4232D / #177247 / #225C91 |
| `--tile-back` / `--tile-back-2` / `--tile-back-edge` | #438D72 / #185D4C / #8BBDA7 |
| `--btn-primary-bg` / `--btn-primary-fg` | accent / fg-on-accent |
| `--btn-action-bg` / `--btn-action-fg` / `--btn-action-edge` | paper / cinnabar-600 / gilt-500 |
| `--clock-track` / `--clock-run` / `--clock-urgent` / `--clock-bank` | fog-100 @ 8% / gilt-400 / cinnabar-400 / indigo-300 |
| `--seal-bg` / `--seal-edge` / `--seal-fg` | #8C3C2B / #CE9C67 / gilt-200 |

### 1.4 非颜色令牌

- 字体：`--font-display: 'Noto Serif SC','Songti SC','STSong',SimSun,serif`；`--font-body: 'Noto Sans SC','PingFang SC','Microsoft YaHei',system-ui,sans-serif`；`--font-num` 同 body 并加 `font-variant-numeric: tabular-nums`。字体通过 Google Fonts `<link>` 加载，离线或 App 内回退系统字体；牌面汉字固定 `--font-display`。
- 字号（竖屏 / 舞台）：display 44/40、h1 28/26、h2 22/20、body 16/14、caption 13/12、eyebrow 11（字距 .28em）、action 20（字距 .2em）。
- 圆角：`--r-xs 4 / --r-sm 8 / --r-md 12 / --r-lg 16 / --r-xl 24 / --r-pill 999`。牌面与微型徽标按尺寸计算，保留特例。
- 间距：4 / 8 / 12 / 16 / 24 / 32 / 48；竖屏页边 20px，舞台边距 24px；竖屏按钮最小 44px、输入 48px。
- 阴影：`--sh-1`（普通抬升）`--sh-2`（弹窗）`--sh-tile`（牌砖厚度）`--sh-glow`（金色微光）。
- 动效：`--motion-fast 150ms / --motion-normal 220ms / --motion-ceremony 1200ms`；`prefers-reduced-motion` 只减表现不改时序。
- 层级（`z-index.css`）：舞台内 `--z-stage-hud 20 / --z-stage-prompt 50 / --z-stage-ceremony 80`；视口覆盖 `--z-tabs 10 / --z-fixed-action 11 / --z-banner 30 / --z-modal 100 / --z-fullscreen 9999`。

## 2. Tailwind 接法

`tailwind.config.js` 的 `theme.extend.colors` 把每个色族映射为 `rgb(var(--x) / <alpha-value>)`，例如 `ink: { 900: 'rgb(var(--ink-900) / <alpha-value>)' }`，语义色同理（`accent`、`highlight`、`line`、`ok`、`danger`…）。于是 `bg-ink-900/95`、`border-accent/45`、`text-gilt-300` 都可用。`fontFamily.display/body`、`borderRadius`、`boxShadow` 也指向令牌。**不要**重定义 Tailwind 自带 amber / teal 等名字，旧色承载多种含义，必须逐处判断语义再替换。

## 3. 组件

基础类在 `frontend/src/styles/components.css`（`@layer components`），Vue 封装在 `frontend/src/components/ui/`。

| 组件 | 规则 |
|---|---|
| 按钮 `.ui-btn` | 四级：`--primary`（金底深字，一屏一个）、`--secondary`（ink-600 底）、`--ghost`（透明金线）、`--danger`（朱砂，只用于离开 / 解散 / 删除等不可逆）。最小高 44px，圆角 `--r-md`，focus-visible 用 accent 描边。 |
| 牌桌动作 `.ui-btn--action` | 玉白底、朱砂宋体大字、金边、底部 3px gilt-700 厚边。`胡` 反色（朱砂底玉白字），`过` 用 ink-600 底 fog 字无厚边。 |
| 卡片 `.ui-card` | ink-700 底、`--line` 描边、`--r-lg`，**无阴影**。强调卡 `.ui-card--gilt` 加 accent-soft 渐变与金色角线 `.ui-corner`。 |
| 弹窗 `.ui-modal` | `--r-xl`、accent-line 描边、`--sh-2 + --sh-glow`，标题栏下一条回纹 `.ui-huiwen`。遮罩 `--bg-overlay` + blur 8px。 |
| 横幅（自摸 / 流局 / 开局财神） | 玉白纸底、朱砂大字、两侧云纹，入场 `--motion-ceremony`。 |
| Toast / 更新横幅 | ink-800 底，左侧 3px gilt 竖线，无图标。 |
| 胶囊 `.ui-pill` | 999 圆角、`--line` 描边、ink-950 @ 60% 底；`--ok / --warn / --danger` 变体改描边与文字色。 |
| 时钟 | conic-gradient，`--clock-run` 正常、`--clock-urgent` 剩 3 秒内、`--clock-bank` 用 time bank；数字 tabular。 |
| 风位 `.ui-wind` | 34px 方块，宋体，金线；庄家朱砂底金边。 |
| 牌面 | 只有三种附加状态：财神（highlight 描边 + 如意徽）、推荐（牌下 jade 圆点）、选中（上浮 8px）。徽章用 highlight，是全桌唯一亮金。暗牌一种纹样一种明暗，不带身份线索。 |
| 印章 `.ui-seal` | 42px，`--seal-*` 令牌，只用于品牌区、启动页、结算卡落款。 |

## 4. 纹样落点

文件：`frontend/src/styles/patterns.css`，SVG 在 `frontend/src/assets/patterns/`。

| 纹样 | 类 | 允许位置 | 禁止 |
|---|---|---|---|
| 回纹 | `.ui-huiwen`（横条）`.ui-huiwen-frame`（边框） | 弹窗标题下沿、结算卡上下边、竖屏 section 分隔线、牌桌外圈细边。高 8–14px，gilt-500 @ 45–60% | 列表行、表格、输入区 |
| 云纹 | `.ui-yunwen` | 牌桌舞台左上、右下角；大厅品牌区背后；开局财神光环外圈。@ 25–30% | 牌河、手牌、副露、计时器附近 |
| 龟甲纹 | `.ui-guijia` | 竖屏壳页面底纹、弹窗遮罩底纹。@ 6–9% | 牌桌面 |
| 角线 | `.ui-corner` | 强调卡：当前模式、候场席位卡、房主座位、胡牌结算。16px L 形金线 | 席位卡的房主 / 准备 / 离线状态仍用纯色 |
| 印章 | `.ui-seal` | 品牌区、启动页、结算卡落款 | 其它 |
| 如意纹 | `.ui-ruyi` | 财神标记、开局财神光环 | 其它；财神牌本身保持纯色高对比 |
| 牌背 | `MahjongTile .tile-back-face` | 保留绿色斜纹，加金色内框与细回纹 | 小尺寸允许退化为纯色避免摩尔纹 |

## 5. 两套壳子

- 竖屏壳（`shell-portrait.css`，原 `style.css` 大部分）：大厅、登录、好友、设置、候场。页边 20px，卡片 `.ui-card`，底部四标签 `.bottom-tabs`，龟甲底纹，section 间回纹分隔。
- 横屏舞台（`shell-stage.css`）：1280×720 逻辑舞台。桌面 `radial-gradient(ellipse 70% 60% at 50% 45%, felt-500, felt-600 45%, ink-800)`，外圈 1.5px accent-line 圆角 14 边框加细回纹，左上 / 右下云纹，中央罗盘圆环 accent-line。所有 HUD 面板 ink-950 @ 55% 底 + `--line` 描边 + `--r-md`。

## 6. UI 贡献清单（每个 PR 必过）

1. 颜色只用 `var(--*)` 或映射色名；`npm run lint:colors` 通过（无新增字面量）。
2. 新界面先从 `components/ui` 组装，缺的组件先补进 ui 目录再用。
3. 字体只用 display / body / num 三个令牌。
4. 纹样只用 patterns.css 里的类，不新画；牌桌中央不放纹样。
5. 一屏一个 primary；danger 只用于不可逆操作；亮金只在舞台内。
6. 最小点击区 44px；focus-visible 用 accent 描边；长文本可换行或滚动，不裁切。
7. 牌桌改动必须跑 `pve-stage-smoke / pve-worst-case / pve-landscape` 并附前后截图；不新增包装节点、不给祖先加 transform。
8. 弹窗验证焦点进出、Esc / Android 返回、滚动锁、Teleport 后令牌可取（令牌挂 `:root`）。
9. PvP 隐私信息不能只靠颜色遮蔽。
10. 原生同步值：`index.html` theme-color、`capacitor.config.ts`、`src/platform/native.js` 的背景色必须等于 `--ink-900`（#06221D）。

## 7. 迁移状态

| 阶段 | 内容 | 状态 |
|---|---|---|
| P1 地基 | tokens / patterns / base / components / z-index CSS，Tailwind 映射，字体，本文档，颜色扫描脚本 | 完成 |
| P2 竖屏壳 | 大厅、登录、好友、设置、候场、更新横幅迁移到令牌与 ui 组件 | 完成 |
| P3 牌桌 | 牌面 → 状态 → 弹窗三小步 | 完成 |
| P4 守则 | lint 接 CI（deploy.yml、android-release.yml）、CLAUDE.md UI 规则、`?preview=design` 预览页 | 完成 |

P2 notes:
- `PveStartDialog` renders inside `TableShell` and remains for P3; `HomeModeSelect` is unused but its listed styles are migrated.
- Repeated invitation/friend actions and update-banner actions use secondary emphasis, preserving existing class names and the home hero's single primary action.
- `PvpLobby`'s shared error style now uses semantic tokens; stage layout is unchanged. No tokens were added.


### P3 mapping

| Existing use | P3 token mapping |
|---|---|
| Emerald/teal dark stage and panels | ink-900/800/700; table surface `radial-gradient(ellipse 70% 60% at 50% 45%, rgb(var(--table-felt)), rgb(var(--felt-600)) 45%, rgb(var(--table-felt-deep)))` |
| HUD panels | ink-950 / .55 background, line / .16 border, r-md; preserve measured geometry |
| Amber/yellow chrome, CTA, titles, borders; old brand gold hexes | gilt-500/400/300/200; accent / accent-line; dark text fg-on-accent |
| ??, recommended discard, current actor, ? badge only | highlight; other gold remains gilt |
| Red/rose danger, negative scores, destructive actions | danger text and danger / .16 background; cinnabar-600 solid |
| Green success, safe and positive scores | ok text and ok / .16 background |
| Sky/blue information, drawn tile, drag insertion; lime drop target | info and info / .16; drop target ok |
| Slate/neutral data and disabled | fog-300/400/600 and ink-800; white fg/ivory, black ink-950 |
| Light settlement/banner/result surfaces | paper / paper-2 / paper-edge; fg-on-paper, cinnabar-600 large characters |
| Tile face, edge, shadow, ink | tile-face / tile-face-2 / tile-edge / tile-shadow / tile-ink |
| Tile suits and honors | tile-wan / tile-tong / tile-tiao; tile-zhong / tile-fa / tile-bai |
| Concealed tile backs | tile-back / tile-back-2 / tile-back-edge; retain stripes, gilt-300 / .35 inner frame |
| Action buttons | ui-btn--action colors/font/borders; is-hu inverted, is-pass muted; preserve sizes and hooks |
| Clocks | clock-run / clock-bank / clock-urgent; paused dashed line |
| Modals | ink-800, accent-line / .45; r-xl only for existing radius >=20px; title huiwen only with >=12px spare height |
| Stage decoration | inset 14px, 1.5px accent-line / .35 rounded 14px frame; 140px corner ui-yunwen at .25, below HUD, no pointer events |

P3 notes:
- Migrated 30 stage source files plus shared `src/constants/tiles.js`, the color allowlist, and this spec (33 files). `DiscardRiver.vue` and `PlayerWorkbench.vue` needed no color changes. `worstCase.js` contains UI classes and was migrated. Existing unrelated workspace edits were preserved.
- The P3 mapping above is the implementation table. No tokens were added and no token values changed. Tailwind opacity values outside its five-point scale use arbitrary syntax, e.g. `bg-danger/[.16]` and `border-line/[.16]`.
- Tile art uses tile tokens; concealed backs retain diagonal stripes and gain an inset gilt frame. Action buttons adopt the action recipe, including its 3px bottom border, with existing label sizes retained. Running/bank/urgent clocks use clock tokens, and paused SeatClock borders remain dashed.
- The existing stage receives a pure inset-frame pseudo-element and two appended aria-hidden corner overlays; no children were wrapped. Absolute huiwen strips use existing title gaps in GameConfig, PveStartDialog, and PvECircleSummary. GameHistoryModal and GameOverModal title strips were omitted where a free 12px gap could not be established.
- Lead reviewed `git diff -w` per scoped file and compared existing geometry declarations with the captured starting files: sizes, coordinates, padding, font sizes, transforms, tile dimensions and the 1080x560 overlays are unchanged. Only authorized radii, action borders/fonts, and added decoration rules differ. All original data/aria hooks and Chinese text were checked against the baseline; UTF-8 is valid. `git diff --check` passed.
- Defects found and corrected: temporary Windows-code-page writes (restored original text and reapplied UTF-8-safe edits), unsupported generated color shades, missing semantic alpha, invalid nonstandard Tailwind opacity suffixes, overbroad highlight usage, and an unused/mispositioned title-strip rule. No geometry defects remain.
- `npm.cmd run lint:colors`: exit 0; `Color lint: 1 violations in 1 files; 1 allowlisted; 0 unallowlisted.` All migrated files were removed from the allowlist. The single remaining entry is the out-of-scope native platform synchronization literal in `src/platform/native.js`.
- `$env:VITE_API_BASE_URL='https://example.com'; npm.cmd run build`: exit 0; 151 modules transformed, built in 2.20s (final run).
- `node scripts/pve-stage-smoke.mjs`: exit 1; `Warning: Detected unsettled top-level await at file:///F:/mahjong/frontend/scripts/pve-stage-smoke.mjs:57`, at `await command('Runtime.enable')`. The same failure was observed before the lead styling edits and after integration.
- `node scripts/pve-worst-case.mjs`: exit 1; `Warning: Detected unsettled top-level await at file:///F:/mahjong/frontend/scripts/pve-worst-case.mjs:55`, at `await command('Runtime.enable')`.
- `node scripts/pve-landscape.mjs`: exit 1; `Error: Landscape browser test timed out`, at `until (file:///F:/mahjong/frontend/scripts/pve-landscape.mjs:24:9)`, called at `75:3`; Node.js v24.14.0. The existing 5173 server was used; no new dev server was started and no smoke scripts were modified.
- Deferred verification: browser smoke assertions and before/after screenshots, because the supplied headless scripts failed before reaching capture/assertion completion. P3 implementation, lint, build and static geometry review are complete; browser verification remains unproven.
- Sub-agents: tiles, modals, hud; each used `gpt-6-luna`, reasoning effort `high`, with disjoint file ownership and lead integration review.

P4 notes:
- 颜色扫描 `npm run lint:colors` 已接入 `.github/workflows/deploy.yml` 与 `android-release.yml`，在构建之前执行；允许名单只剩 `src/platform/native.js`（原生状态栏颜色必须是字面量，值镜像 `--ink-900`）。
- 仓库根目录 `CLAUDE.md` 记录了 UI 硬规则，AI 协作改动也会遵守。
- 设计系统活文档：`http://localhost:5173/?preview=design`（`DesignSystemPreview.vue`）。
- 已知：`frontend/scripts/pve-stage-smoke.mjs` 等脚本在根路径等待「人机对战」按钮，但当前路由会把未登录访问重定向到 `/login`，脚本在样式迁移前就已失效，需要单独修复（给脚本注入登录态或改走 `?preview` 入口）。P3 的牌桌验证改为人工在浏览器中核对 PvE 桌面。

