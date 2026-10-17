# EV 启发式权重自动调优方案（V3—V5）

核对日期：2026-10-16；范围为本工作区当前文件，不推断运行中服务或线上版本。本文只做盘点和设计，所有新参数接口、门槛和预算均为建议，未执行仿真或改变配置。

## 1. 参数全景与现状

### 1.1 计数口径与代码事实

本表共 **241 项**审计条目：旧配置165项（danger 13、tenpai 21、ev 85、call 38、screen 8），另有71项源码固定系数/阈值/规则项与5项V2实验权重。按模块：danger_model 13、tenpai_model 28、ev_engine 96、call_decision 46、screen 8、scoring 23、evaluator 2、settlement 4、claim_v2 8、threat_assessment 13。这不是可同时搜索的维数。

165 项配置键全部逐项核对 `weights_schema.json` 的 AST 位置、冻结源码与当前源码字面值；表内行号是**当前文件**行号。旧键名中的 L/C 是冻结源码标识，不是当前行号。当前值指正常启动成功加载 optimized 后的值：12 项取配置，其余取源码；不是只 import 模块时的默认值。所有旧键的源码默认值与 V0 配置一致，12 项覆盖后的值与 v1 inventory 主表一致，没有发现数值冲突。

`ai_weights.py:19–47` 校验精确的165键集合，12项必须满足 `ai_core_bounds.json`，其余153项必须等于V0。V1开放搜索12项、实际改值10项（深向听单位25、Sigmoid陡度0.42未改）；V2冻结全部165项，包括8项仅fast代理权重，再另搜5项claim权重。`tools/weights.py:38–43` 还硬性拒绝 V2 修改任一V1基础值。因此后续解冻不仅是改JSON，需要独立版本schema、加载白名单和私有运行时支持。

与旧inventory的区别：旧文档已附列13项未参数化常量和5项V2参数，并非完全遗漏；本表进一步定位到当前行，补充散落的强制排序余量、庄闲结算尺度、染手触发阈值及scoring/threat参数。旧主表157项中也含说明文案阈值、平均数分母和规则倍率，不能把157视作157个独立可学习自由度。例如 `_discard_candidate_note` 只影响说明；`_base_danger` 的2是生熟均值分母；杠估值3/2涉及庄闲尺度。固定规则及提示单列状态，不参与自动解冻。

`ev_engine.py` 开头“无辣子封顶”描述的是启发式进攻估值，真实 `settlement.py:201–223` 已按100封顶线及辣子全付结算；不能调整支付规则来让代理EV看起来更准。`evaluator.py`负责合法和牌/向听及计分适配，无独立学习权重（其3/2尺度见表）；`action_generator.py`只生成合法动作和检测冗余吃牌，无策略权重；`ai_weights.py`只有校验/加载职责，没有额外评分系数。每牌4张、4面子1雀头、序数范围、索引、0/1恒等项、浮点容差、显示小数位、缓存容量不按权重计数；影响策略的非恒等排序余量则收录。

历史实验与当前生产必须分开：生产V1已补冗余吃牌硬过滤，旧V0/V1离线冻结源码仍保留历史行为。原4000局证据不能直接代表补丁后V1。新实验应同时保存“历史V1”和“当前V1+guard”的实现指纹，以后者作晋升参照，不能只用配置指纹判为同一策略。

### 1.2 全景表

列中“表达式”直接来自当前代码，配合作用列确定条件分支；同名不同位置的匿名系数按位置单独列出，未来命名/合并后应迁移键而非同时自由搜索。表中代码路径以仓库根目录为基准。


#### danger_model（13项）

| 名称 | 当前文件:行 | 当前值 | 作用 | 耦合关系 | 状态 | 当前源码表达式 |
|---|---|---:|---|---|---|---|
| `danger_model.BASE_HONOR_LIVE` | `backend/app/core/danger_model.py:28` | 0.16 | 字牌生张 | 与听牌概率相乘，再经 DEFENSE_RISK_REFERENCE 放大；壁/染手折扣连乘 | V0固定；V2冻结 | `BASE_HONOR_LIVE = 0.16  # 字牌生张` |
| `danger_model.BASE_HONOR_DEAD` | `backend/app/core/danger_model.py:29` | 0.02 | 字牌已见 ≥2（熟张上限） | 与听牌概率相乘，再经 DEFENSE_RISK_REFERENCE 放大；壁/染手折扣连乘 | V0固定；V2冻结 | `BASE_HONOR_DEAD = 0.02  # 字牌已见 ≥2（熟张上限）` |
| `danger_model.BASE_MID_456` | `backend/app/core/danger_model.py:30` | 0.18 | 序数 4/5/6 | 与听牌概率相乘，再经 DEFENSE_RISK_REFERENCE 放大；壁/染手折扣连乘 | V0固定；V2冻结 | `BASE_MID_456 = 0.18  # 序数 4/5/6` |
| `danger_model.BASE_TERMINAL` | `backend/app/core/danger_model.py:31` | 0.08 | 序数 1/9 | 与听牌概率相乘，再经 DEFENSE_RISK_REFERENCE 放大；壁/染手折扣连乘 | V0固定；V2冻结 | `BASE_TERMINAL = 0.08  # 序数 1/9` |
| `danger_model.BASE_NEAR_MID` | `backend/app/core/danger_model.py:32` | 0.12 | 序数 2/3/7/8（介于幺九与深中张之间） | 与听牌概率相乘，再经 DEFENSE_RISK_REFERENCE 放大；壁/染手折扣连乘 | V0固定；V2冻结 | `BASE_NEAR_MID = 0.12  # 序数 2/3/7/8（介于幺九与深中张之间）` |
| `danger_model.WALL_BOTH_SIDES_FACTOR` | `backend/app/core/danger_model.py:35` | 0.45 | WALL_BOTH_SIDES_FACTOR | 与听牌概率相乘，再经 DEFENSE_RISK_REFERENCE 放大；壁/染手折扣连乘 | V0固定；V2冻结 | `WALL_BOTH_SIDES_FACTOR = 0.45` |
| `danger_model.WALL_ONE_SIDE_EDGE_FACTOR` | `backend/app/core/danger_model.py:36` | 0.7 | 边张仅一侧可连且已断 | 与听牌概率相乘，再经 DEFENSE_RISK_REFERENCE 放大；壁/染手折扣连乘 | V0固定；V2冻结 | `WALL_ONE_SIDE_EDGE_FACTOR = 0.70  # 边张仅一侧可连且已断` |
| `danger_model.DYE_OWN_SUIT_MID_FACTOR` | `backend/app/core/danger_model.py:39` | 2.2 | 染手花色 3~7 | 与听牌概率相乘，再经 DEFENSE_RISK_REFERENCE 放大；壁/染手折扣连乘 | V0固定；V2冻结 | `DYE_OWN_SUIT_MID_FACTOR = 2.2  # 染手花色 3~7` |
| `danger_model.DYE_OTHER_SUIT_FACTOR` | `backend/app/core/danger_model.py:40` | 0.25 | 其余两门序数 | 与听牌概率相乘，再经 DEFENSE_RISK_REFERENCE 放大；壁/染手折扣连乘 | V0固定；V2冻结 | `DYE_OTHER_SUIT_FACTOR = 0.25  # 其余两门序数` |
| `danger_model.estimate_tile_danger.L80C18` | `backend/app/core/danger_model.py:80` | 0.75 | 估算 ``tile`` 对 ``opponent`` 的放铳概率 P(DealIn &#124; Tenpai)。；见表达式 | 与听牌概率相乘，再经 DEFENSE_RISK_REFERENCE 放大；壁/染手折扣连乘 | V0固定；V2冻结 | `danger *= 0.75` |
| `danger_model._base_danger.L115C16` | `backend/app/core/danger_model.py:115` | 0.5 | _base_danger；见表达式 | 与听牌概率相乘，再经 DEFENSE_RISK_REFERENCE 放大；壁/染手折扣连乘 | V0固定；V2冻结 | `base *= 0.5` |
| `danger_model._base_danger.L117C16` | `backend/app/core/danger_model.py:117` | 0.75 | _base_danger；见表达式 | 与听牌概率相乘，再经 DEFENSE_RISK_REFERENCE 放大；壁/染手折扣连乘 | V0固定；V2冻结 | `base *= 0.75` |
| `danger_model._base_danger.L99C57` | `backend/app/core/danger_model.py:99` | 2.0 | _base_danger；见表达式 | 与听牌概率相乘，再经 DEFENSE_RISK_REFERENCE 放大；壁/染手折扣连乘 | V0固定；V2冻结 | `return (BASE_HONOR_LIVE + BASE_HONOR_DEAD) / 2.0` |

#### tenpai_model（28项）

| 名称 | 当前文件:行 | 当前值 | 作用 | 耦合关系 | 状态 | 当前源码表达式 |
|---|---|---:|---|---|---|---|
| `tenpai_model._P_FLOOR` | `backend/app/core/tenpai_model.py:27` | 0.028 | 门清听牌先验下沿 | 与 danger_model 条件危险及胡数损失相乘；先验、加成、封顶相互抵消 | V0固定；V2冻结 | `_P_FLOOR = 0.028` |
| `tenpai_model._P_SPAN` | `backend/app/core/tenpai_model.py:28` | 0.52 | 门清先验振幅 | 与 danger_model 条件危险及胡数损失相乘；先验、加成、封顶相互抵消 | V0固定；V2冻结 | `_P_SPAN = 0.52` |
| `tenpai_model._SIGMOID_CENTER` | `backend/app/core/tenpai_model.py:29` | 10.101047681722928 | 听牌曲线巡目中心 | 与 danger_model 条件危险及胡数损失相乘；先验、加成、封顶相互抵消 | V1已搜索/允许覆盖；V2冻结 | `_SIGMOID_CENTER = 11.0` |
| `tenpai_model._SIGMOID_STEEPNESS` | `backend/app/core/tenpai_model.py:30` | 0.42 | 听牌曲线陡度 | 与 danger_model 条件危险及胡数损失相乘；先验、加成、封顶相互抵消 | V1已搜索/允许覆盖；V2冻结 | `_SIGMOID_STEEPNESS = 0.42` |
| `tenpai_model._MELD3_FLOOR` | `backend/app/core/tenpai_model.py:35` | 0.9 | 三组副露仅余一搭与雀头，至少列为高听牌风险 | 与 danger_model 条件危险及胡数损失相乘；先验、加成、封顶相互抵消 | V0固定；V2冻结 | `_MELD3_FLOOR = 0.90  # 三组副露仅余一搭与雀头，至少列为高听牌风险` |
| `tenpai_model._DEALER_BOOST` | `backend/app/core/tenpai_model.py:38` | 1.12 | 庄家听牌概率倍率 | 与 danger_model 条件危险及胡数损失相乘；先验、加成、封顶相互抵消 | V0固定；V2冻结 | `_DEALER_BOOST = 1.12` |
| `tenpai_model._CENTRAL_MULT` | `backend/app/core/tenpai_model.py:43` | 1.28 | 每次主动中张 | 与 danger_model 条件危险及胡数损失相乘；先验、加成、封顶相互抵消 | V0固定；V2冻结 | `_CENTRAL_MULT = 1.28  # 每次主动中张` |
| `tenpai_model._CENTRAL_ADD` | `backend/app/core/tenpai_model.py:44` | 0.055 | 主动切中张听牌概率增量 | 与 danger_model 条件危险及胡数损失相乘；先验、加成、封顶相互抵消 | V0固定；V2冻结 | `_CENTRAL_ADD = 0.055` |
| `tenpai_model._PROGRESSION_MULT` | `backend/app/core/tenpai_model.py:48` | 1.18 | 弃牌递进听牌概率倍率 | 与 danger_model 条件危险及胡数损失相乘；先验、加成、封顶相互抵消 | V0固定；V2冻结 | `_PROGRESSION_MULT = 1.18` |
| `tenpai_model._PROGRESSION_ADD` | `backend/app/core/tenpai_model.py:49` | 0.04 | 弃牌递进听牌概率增量 | 与 danger_model 条件危险及胡数损失相乘；先验、加成、封顶相互抵消 | V0固定；V2冻结 | `_PROGRESSION_ADD = 0.04` |
| `tenpai_model._SAFE_STREAK_MULT` | `backend/app/core/tenpai_model.py:55` | 1.15 | 连续安牌听牌概率倍率 | 与 danger_model 条件危险及胡数损失相乘；先验、加成、封顶相互抵消 | V0固定；V2冻结 | `_SAFE_STREAK_MULT = 1.15` |
| `tenpai_model._SAFE_STREAK_ADD` | `backend/app/core/tenpai_model.py:56` | 0.035 | 连续安牌听牌概率增量 | 与 danger_model 条件危险及胡数损失相乘；先验、加成、封顶相互抵消 | V0固定；V2冻结 | `_SAFE_STREAK_ADD = 0.035` |
| `tenpai_model._MELD_ADD.1` | `backend/app/core/tenpai_model.py:33` | 0.14 | 按副露组数叠加听牌概率 | 与 danger_model 条件危险及胡数损失相乘；先验、加成、封顶相互抵消 | V0固定；V2冻结 | `_MELD_ADD = {1: 0.14, 2: 0.30, 3: 0.48, 4: 0.55}` |
| `tenpai_model._MELD_ADD.2` | `backend/app/core/tenpai_model.py:33` | 0.3 | 按副露组数叠加听牌概率 | 与 danger_model 条件危险及胡数损失相乘；先验、加成、封顶相互抵消 | V0固定；V2冻结 | `_MELD_ADD = {1: 0.14, 2: 0.30, 3: 0.48, 4: 0.55}` |
| `tenpai_model._MELD_ADD.3` | `backend/app/core/tenpai_model.py:33` | 0.48 | 按副露组数叠加听牌概率 | 与 danger_model 条件危险及胡数损失相乘；先验、加成、封顶相互抵消 | V0固定；V2冻结 | `_MELD_ADD = {1: 0.14, 2: 0.30, 3: 0.48, 4: 0.55}` |
| `tenpai_model._MELD_ADD.4` | `backend/app/core/tenpai_model.py:33` | 0.55 | 按副露组数叠加听牌概率 | 与 danger_model 条件危险及胡数损失相乘；先验、加成、封顶相互抵消 | V0固定；V2冻结 | `_MELD_ADD = {1: 0.14, 2: 0.30, 3: 0.48, 4: 0.55}` |
| `tenpai_model._MELD_CAP.1` | `backend/app/core/tenpai_model.py:34` | 0.82 | 按副露组数封顶听牌概率 | 与 danger_model 条件危险及胡数损失相乘；先验、加成、封顶相互抵消 | V0固定；V2冻结 | `_MELD_CAP = {1: 0.82, 2: 0.90, 3: 0.93, 4: 0.95}` |
| `tenpai_model._MELD_CAP.2` | `backend/app/core/tenpai_model.py:34` | 0.9 | 按副露组数封顶听牌概率 | 与 danger_model 条件危险及胡数损失相乘；先验、加成、封顶相互抵消 | V0固定；V2冻结 | `_MELD_CAP = {1: 0.82, 2: 0.90, 3: 0.93, 4: 0.95}` |
| `tenpai_model._MELD_CAP.3` | `backend/app/core/tenpai_model.py:34` | 0.93 | 按副露组数封顶听牌概率 | 与 danger_model 条件危险及胡数损失相乘；先验、加成、封顶相互抵消 | V0固定；V2冻结 | `_MELD_CAP = {1: 0.82, 2: 0.90, 3: 0.93, 4: 0.95}` |
| `tenpai_model._MELD_CAP.4` | `backend/app/core/tenpai_model.py:34` | 0.95 | 按副露组数封顶听牌概率 | 与 danger_model 条件危险及胡数损失相乘；先验、加成、封顶相互抵消 | V0固定；V2冻结 | `_MELD_CAP = {1: 0.82, 2: 0.90, 3: 0.93, 4: 0.95}` |
| `tenpai_model._apply_progression_boost.L209C52` | `backend/app/core/tenpai_model.py:209` | 0.35 | 字牌/幺九先切、其后出现中张 → 「面子趋满」增益。；见表达式 | 与 danger_model 条件危险及胡数损失相乘；先验、加成、封顶相互抵消 | V0固定；V2冻结 | `if early_ok and late_mid and early_mid_ratio <= 0.35:` |
| `tenpai_model._CENTRAL_LOOKBACK` | `backend/app/core/tenpai_model.py:42` | 2 | 主动切中张回看巡数 | 与 danger_model 条件危险及胡数损失相乘；先验、加成、封顶相互抵消 | 源码固定；未进入165项 | `_CENTRAL_LOOKBACK = 2` |
| `tenpai_model._CENTRAL_EARLY_TURN` | `backend/app/core/tenpai_model.py:45` | 4 | ≥此巡才计中张增益（避免开局误伤） | 与 danger_model 条件危险及胡数损失相乘；先验、加成、封顶相互抵消 | 源码固定；未进入165项 | `_CENTRAL_EARLY_TURN = 4  # ≥此巡才计中张增益（避免开局误伤）` |
| `tenpai_model._SAFE_STREAK_MIN_TURN` | `backend/app/core/tenpai_model.py:52` | 5 | 安牌信号起始巡目 | 与 danger_model 条件危险及胡数损失相乘；先验、加成、封顶相互抵消 | 源码固定；未进入165项 | `_SAFE_STREAK_MIN_TURN = 5` |
| `tenpai_model._SAFE_STREAK_LOOKBACK` | `backend/app/core/tenpai_model.py:53` | 3 | 连续安牌回看巡数 | 与 danger_model 条件危险及胡数损失相乘；先验、加成、封顶相互抵消 | 源码固定；未进入165项 | `_SAFE_STREAK_LOOKBACK = 3` |
| `tenpai_model._SAFE_STREAK_NEED` | `backend/app/core/tenpai_model.py:54` | 2 | 安牌触发最少次数 | 与 danger_model 条件危险及胡数损失相乘；先验、加成、封顶相互抵消 | 源码固定；未进入165项 | `_SAFE_STREAK_NEED = 2` |
| `tenpai_model._P_MIN` | `backend/app/core/tenpai_model.py:59` | 0.02 | 听牌概率最终下限 | 与 danger_model 条件危险及胡数损失相乘；先验、加成、封顶相互抵消 | 源码固定；未进入165项 | `_P_MIN = 0.02` |
| `tenpai_model._P_MAX` | `backend/app/core/tenpai_model.py:60` | 0.95 | 听牌概率最终上限 | 与 danger_model 条件危险及胡数损失相乘；先验、加成、封顶相互抵消 | 源码固定；未进入165项 | `_P_MAX = 0.95` |

#### ev_engine（96项）

| 名称 | 当前文件:行 | 当前值 | 作用 | 耦合关系 | 状态 | 当前源码表达式 |
|---|---|---:|---|---|---|---|
| `ev_engine.SHANTEN_PENALTY` | `backend/app/core/ev_engine.py:56` | 131 | 每向听净分惩罚 | SHANTEN_PENALTY 与 DEEP_SHANTEN_UNIT 在深向听近似中叠加，勿同时放大 | V1已搜索/允许覆盖；V2冻结 | `SHANTEN_PENALTY = 120` |
| `ev_engine._ZIMO_THREAT_PRIOR` | `backend/app/core/ev_engine.py:58` | 0.28 | _ZIMO_THREAT_PRIOR | 听牌概率 × 条件危险 × 胡数损失；与防守折让和风险倍率互相补偿 | V0固定；V2冻结 | `_ZIMO_THREAT_PRIOR = 0.28` |
| `ev_engine._IISHANTEN_TURN_DISCOUNT` | `backend/app/core/ev_engine.py:62` | 2 | _IISHANTEN_TURN_DISCOUNT | SHANTEN_PENALTY 与 DEEP_SHANTEN_UNIT 在深向听近似中叠加，勿同时放大 | V0固定；V2冻结 | `_IISHANTEN_TURN_DISCOUNT = 2` |
| `ev_engine._UKEIRE_QUALITY_WEIGHT` | `backend/app/core/ev_engine.py:65` | 0.8905197287388378 | 有效进张枚数质量权重 | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | V1已搜索/允许覆盖；V2冻结 | `_UKEIRE_QUALITY_WEIGHT = 1.25  # 有效进张枚数质量权重` |
| `ev_engine._DEEP_SHANTEN_UNIT` | `backend/app/core/ev_engine.py:67` | 25 | 多向听内向听档位代价（与 SHANTEN_PENALTY 分工） | SHANTEN_PENALTY 与 DEEP_SHANTEN_UNIT 在深向听近似中叠加，勿同时放大 | V1已搜索/允许覆盖；V2冻结 | `_DEEP_SHANTEN_UNIT = 25  # 多向听内向听档位代价（与 SHANTEN_PENALTY 分工）` |
| `ev_engine._YAKUHAI_SINGLE_POTENTIAL` | `backend/app/core/ev_engine.py:68` | 12.61312012835429 | 役牌孤张保留分（中发白 / 自风） | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V1已搜索/允许覆盖；V2冻结 | `_YAKUHAI_SINGLE_POTENTIAL = 10.0  # 役牌孤张保留分（中发白 / 自风）` |
| `ev_engine._YAKUHAI_PAIR_POTENTIAL` | `backend/app/core/ev_engine.py:69` | 15.253399288810538 | 役牌对子（接近刻） | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V1已搜索/允许覆盖；V2冻结 | `_YAKUHAI_PAIR_POTENTIAL = 16.0  # 役牌对子（接近刻）` |
| `ev_engine._YAKUHAI_PUNG_POTENTIAL` | `backend/app/core/ev_engine.py:70` | 22.0 | 已成役牌刻 | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V0固定；V2冻结 | `_YAKUHAI_PUNG_POTENTIAL = 22.0  # 已成役牌刻` |
| `ev_engine._SHAPE_PAIR` | `backend/app/core/ev_engine.py:71` | 8.0 | 对子结构分 | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V0固定；V2冻结 | `_SHAPE_PAIR = 8.0` |
| `ev_engine._SHAPE_PUNG` | `backend/app/core/ev_engine.py:72` | 20.0 | 刻子结构分 | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V0固定；V2冻结 | `_SHAPE_PUNG = 20.0` |
| `ev_engine._SHAPE_RYANMEN` | `backend/app/core/ev_engine.py:73` | 10.0 | 两面搭子结构分 | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V0固定；V2冻结 | `_SHAPE_RYANMEN = 10.0` |
| `ev_engine._SHAPE_KANCHAN` | `backend/app/core/ev_engine.py:74` | 5.0 | 嵌张搭子结构分 | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V0固定；V2冻结 | `_SHAPE_KANCHAN = 5.0` |
| `ev_engine._SHAPE_PENCHAN` | `backend/app/core/ev_engine.py:75` | 3.0 | 边张搭子结构分 | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V0固定；V2冻结 | `_SHAPE_PENCHAN = 3.0` |
| `ev_engine._COMPOSITE_KANCHAN_UPGRADE_BONUS` | `backend/app/core/ev_engine.py:76` | 7.0 | 留 2-4 并摸 5 可形成 4-5 两面 | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | V0固定；V2冻结 | `_COMPOSITE_KANCHAN_UPGRADE_BONUS = 7.0  # 留 2-4 并摸 5 可形成 4-5 两面` |
| `ev_engine._ANTI_PONG_TERMINAL_BONUS` | `backend/app/core/ev_engine.py:77` | 3.0 | 场见至少两张幺九，外部最多余一张，无法成碰 | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | V0固定；V2冻结 | `_ANTI_PONG_TERMINAL_BONUS = 3.0  # 场见至少两张幺九，外部最多余一张，无法成碰` |
| `ev_engine._SHAPE_ISOLATED_MID` | `backend/app/core/ev_engine.py:78` | 1.5 | 中张孤张结构分 | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V0固定；V2冻结 | `_SHAPE_ISOLATED_MID = 1.5` |
| `ev_engine._SHAPE_ISOLATED_TERM` | `backend/app/core/ev_engine.py:79` | 0.5 | 幺九孤张结构分 | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V0固定；V2冻结 | `_SHAPE_ISOLATED_TERM = 0.5` |
| `ev_engine._SHAPE_JOKER` | `backend/app/core/ev_engine.py:80` | 12.06978306750579 | 手内「得」百搭 | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V1已搜索/允许覆盖；V2冻结 | `_SHAPE_JOKER = 12.0  # 手内「得」百搭` |
| `ev_engine._GUEST_WIND_SINGLE_PENALTY` | `backend/app/core/ev_engine.py:81` | 12.0 | 无役客风孤张占位价值低，优先切出 | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V0固定；V2冻结 | `_GUEST_WIND_SINGLE_PENALTY = 12.0  # 无役客风孤张占位价值低，优先切出` |
| `ev_engine._GUEST_WIND_PAIR_PENALTY` | `backend/app/core/ev_engine.py:82` | 1.5 | 客风对子略扣（不如役牌对） | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V0固定；V2冻结 | `_GUEST_WIND_PAIR_PENALTY = 1.5  # 客风对子略扣（不如役牌对）` |
| `ev_engine._GUEST_SUBSTITUTE_HOLD_SCALE` | `backend/app/core/ev_engine.py:83` | 0.2 | 白板替身客风：有雀头潜力，占位惩罚压到 20% | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V0固定；V2冻结 | `_GUEST_SUBSTITUTE_HOLD_SCALE = 0.2  # 白板替身客风：有雀头潜力，占位惩罚压到 20%` |
| `ev_engine._SUBSTITUTE_HONOR_KEEP_BONUS` | `backend/app/core/ev_engine.py:84` | 8.0 | 保留健康白板替身字牌的雀头潜力加分 | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V0固定；V2冻结 | `_SUBSTITUTE_HONOR_KEEP_BONUS = 8.0  # 保留健康白板替身字牌的雀头潜力加分` |
| `ev_engine._ORPHAN_TERMINAL_UKEIRE_SCALE` | `backend/app/core/ev_engine.py:85` | 0.22 | 纯 1/9 两步靠搭进张泡沫折现 | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V0固定；V2冻结 | `_ORPHAN_TERMINAL_UKEIRE_SCALE = 0.22  # 纯 1/9 两步靠搭进张泡沫折现` |
| `ev_engine._GUEST_SINGLE_PAIR_UKEIRE_SCALE` | `backend/app/core/ev_engine.py:86` | 0.35 | 无役客风孤张配对：只有刻/雀头路线，无顺子扩展 | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V0固定；V2冻结 | `_GUEST_SINGLE_PAIR_UKEIRE_SCALE = 0.35  # 无役客风孤张配对：只有刻/雀头路线，无顺子扩展` |
| `ev_engine._ORPHAN_TERMINAL_KEEP_PENALTY` | `backend/app/core/ev_engine.py:87` | 9.0 | 切后仍持无邻张 1/9 的加重占位惩罚 | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V0固定；V2冻结 | `_ORPHAN_TERMINAL_KEEP_PENALTY = 9.0  # 切后仍持无邻张 1/9 的加重占位惩罚` |
| `ev_engine._JANTOU_BREAK_PENALTY` | `backend/app/core/ev_engine.py:90` | 21.06869661708672 | 拆唯一法定雀头 | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V1已搜索/允许覆盖；V2冻结 | `_JANTOU_BREAK_PENALTY = 20.0  # 拆唯一法定雀头` |
| `ev_engine._ISOLATED_CUT_BONUS` | `backend/app/core/ev_engine.py:91` | 6.0 | 切出纯孤张（与核心搭子无关） | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V0固定；V2冻结 | `_ISOLATED_CUT_BONUS = 6.0  # 切出纯孤张（与核心搭子无关）` |
| `ev_engine._TERMINAL_ISO_CUT_BONUS` | `backend/app/core/ev_engine.py:92` | 7.5 | 切幺九孤张（优先于中张，次于死字牌） | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | V0固定；V2冻结 | `_TERMINAL_ISO_CUT_BONUS = 7.5  # 切幺九孤张（优先于中张，次于死字牌）` |
| `ev_engine._ORPHAN_TERMINAL_CUT_BONUS` | `backend/app/core/ev_engine.py:93` | 16.0 | 无任何同花色邻/嵌的 1/9：最优先切除 | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V0固定；V2冻结 | `_ORPHAN_TERMINAL_CUT_BONUS = 16.0  # 无任何同花色邻/嵌的 1/9：最优先切除` |
| `ev_engine._DEAD_HONOR_CUT_BONUS` | `backend/app/core/ev_engine.py:94` | 14.0 | 切绝张/残缺字牌（Rem≤1） | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | V0固定；V2冻结 | `_DEAD_HONOR_CUT_BONUS = 14.0  # 切绝张/残缺字牌（Rem≤1）` |
| `ev_engine._ISOLATED_KEEP_PENALTY` | `backend/app/core/ev_engine.py:95` | 4.0 | 切后仍持有序数/字牌孤张 | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V0固定；V2冻结 | `_ISOLATED_KEEP_PENALTY = 4.0  # 切后仍持有序数/字牌孤张` |
| `ev_engine._DEAD_HONOR_KEEP_PENALTY` | `backend/app/core/ev_engine.py:96` | 8.0 | 切后仍持绝张字牌（加重） | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | V0固定；V2冻结 | `_DEAD_HONOR_KEEP_PENALTY = 8.0  # 切后仍持绝张字牌（加重）` |
| `ev_engine._GOOD_SHAPE_PUSH_BONUS` | `backend/app/core/ev_engine.py:97` | 10.0 | 好形（刻+两面×2+雀头）推进奖励 | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V0固定；V2冻结 | `_GOOD_SHAPE_PUSH_BONUS = 10.0  # 好形（刻+两面×2+雀头）推进奖励` |
| `ev_engine._GOOD_SHAPE_DEFENSE_SCALE` | `backend/app/core/ev_engine.py:98` | 0.41239674604167603 | 好形时压缩防守过度反应 | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V1已搜索/允许覆盖；V2冻结 | `_GOOD_SHAPE_DEFENSE_SCALE = 0.45  # 好形时压缩防守过度反应` |
| `ev_engine._SEEN_GUEST_WIND_CUT_BONUS` | `backend/app/core/ev_engine.py:100` | 5.5 | Rem≤2 场见客风：优先切除 | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V0固定；V2冻结 | `_SEEN_GUEST_WIND_CUT_BONUS = 5.5  # Rem≤2 场见客风：优先切除` |
| `ev_engine._SUBSTITUTE_YAKUHAI_CUT_PENALTY` | `backend/app/core/ev_engine.py:101` | 9.0 | 切健康白板替身役牌（得≠白）惩罚 | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V0固定；V2冻结 | `_SUBSTITUTE_YAKUHAI_CUT_PENALTY = 9.0  # 切健康白板替身役牌（得≠白）惩罚` |
| `ev_engine._SUBSTITUTE_HONOR_CUT_PENALTY` | `backend/app/core/ev_engine.py:102` | 12.0 | 切健康白板替身字牌（含客风）惩罚 | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V0固定；V2冻结 | `_SUBSTITUTE_HONOR_CUT_PENALTY = 12.0  # 切健康白板替身字牌（含客风）惩罚` |
| `ev_engine._HEALTHY_YAKUHAI_CUT_FACTOR` | `backend/app/core/ev_engine.py:103` | 0.25 | 供给充足的役牌孤张：切除奖励压到 25% | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V0固定；V2冻结 | `_HEALTHY_YAKUHAI_CUT_FACTOR = 0.25  # 供给充足的役牌孤张：切除奖励压到 25%` |
| `ev_engine._NEIGHBOR_OF_GOD_KEEP_BONUS` | `backend/app/core/ev_engine.py:104` | 15.0 | 财神同门 ±1/±2 的孤张顺子连接保留价值 | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | V0固定；V2冻结 | `_NEIGHBOR_OF_GOD_KEEP_BONUS = 15.0  # 财神同门 ±1/±2 的孤张顺子连接保留价值` |
| `ev_engine._CENTRALITY_CUT_REF` | `backend/app/core/ev_engine.py:119` | 12.0 | 与 5 序数保留分对齐 | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V0固定；V2冻结 | `_CENTRALITY_CUT_REF = 12.0  # 与 5 序数保留分对齐` |
| `ev_engine._CENTRALITY_CUT_SCALE_TENPAI` | `backend/app/core/ev_engine.py:120` | 0.4 | 听牌：微差纠偏（切 8 ≈ +4.2） | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V0固定；V2冻结 | `_CENTRALITY_CUT_SCALE_TENPAI = 0.40  # 听牌：微差纠偏（切 8 ≈ +4.2）` |
| `ev_engine._CENTRALITY_CUT_SCALE_DEEP` | `backend/app/core/ev_engine.py:121` | 0.55 | 一向听+：加强偏张优先 | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V0固定；V2冻结 | `_CENTRALITY_CUT_SCALE_DEEP = 0.55  # 一向听+：加强偏张优先` |
| `ev_engine._JOKER_MID_CUT_PENALTY` | `backend/app/core/ev_engine.py:122` | 4.407889513401241 | 持百搭时切 4/5/6 且另有偏张/字牌孤张 | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | V1已搜索/允许覆盖；V2冻结 | `_JOKER_MID_CUT_PENALTY = 4.5  # 持百搭时切 4/5/6 且另有偏张/字牌孤张` |
| `ev_engine._EV_NEAR_TIE_EPS` | `backend/app/core/ev_engine.py:124` | 3.0 | &#124;ΔNetEV&#124;≤3 时按进张数 / 保留中张裁决 | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | V0固定；V2冻结 | `_EV_NEAR_TIE_EPS = 3.0  # &#124;ΔNetEV&#124;≤3 时按进张数 / 保留中张裁决` |
| `ev_engine._GUEST_WITH_HEAD_CUT_BONUS` | `backend/app/core/ev_engine.py:125` | 24.0 | 已有雀头：无役客风先于幺九清理 | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V0固定；V2冻结 | `_GUEST_WITH_HEAD_CUT_BONUS = 24.0  # 已有雀头：无役客风先于幺九清理` |
| `ev_engine._GUEST_WITH_HEAD_HOLD_PENALTY` | `backend/app/core/ev_engine.py:126` | 18.0 | 已有雀头时保留客风罚分 | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V0固定；V2冻结 | `_GUEST_WITH_HEAD_HOLD_PENALTY = 18.0` |
| `ev_engine._TERMINAL_EXTENSION_KEEP_BONUS` | `backend/app/core/ev_engine.py:127` | 6.0 | 幺九可扩展搭子保留奖励 | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | V0固定；V2冻结 | `_TERMINAL_EXTENSION_KEEP_BONUS = 6.0` |
| `ev_engine._CENTRAL_SYNERGY_KEEP_BONUS` | `backend/app/core/ev_engine.py:128` | 12.0 | 中张组合协同保留奖励 | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | V0固定；V2冻结 | `_CENTRAL_SYNERGY_KEEP_BONUS = 12.0` |
| `ev_engine._DEFENSE_RISK_REFERENCE` | `backend/app/core/ev_engine.py:129` | 0.1199965341591117 | 高危切牌的风险厌恶尺度，非概率修正 | 听牌概率 × 条件危险 × 胡数损失；与防守折让和风险倍率互相补偿 | V1已搜索/允许覆盖；V2冻结 | `_DEFENSE_RISK_REFERENCE = 0.12  # 高危切牌的风险厌恶尺度，非概率修正` |
| `ev_engine._CENTRALITY_KEEP_BY_DIGIT.1` | `backend/app/core/ev_engine.py:109` | 0.0 | 对应序数的孤张靠张保留分 | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V0固定；V2冻结 | `1: 0.0,` |
| `ev_engine._CENTRALITY_KEEP_BY_DIGIT.2` | `backend/app/core/ev_engine.py:110` | 1.5 | 对应序数的孤张靠张保留分 | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V0固定；V2冻结 | `2: 1.5,` |
| `ev_engine._CENTRALITY_KEEP_BY_DIGIT.3` | `backend/app/core/ev_engine.py:111` | 5.0 | 对应序数的孤张靠张保留分 | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V0固定；V2冻结 | `3: 5.0,` |
| `ev_engine._CENTRALITY_KEEP_BY_DIGIT.4` | `backend/app/core/ev_engine.py:112` | 10.0 | 对应序数的孤张靠张保留分 | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V0固定；V2冻结 | `4: 10.0,` |
| `ev_engine._CENTRALITY_KEEP_BY_DIGIT.5` | `backend/app/core/ev_engine.py:113` | 12.0 | 对应序数的孤张靠张保留分 | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V0固定；V2冻结 | `5: 12.0,` |
| `ev_engine._CENTRALITY_KEEP_BY_DIGIT.6` | `backend/app/core/ev_engine.py:114` | 10.0 | 对应序数的孤张靠张保留分 | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V0固定；V2冻结 | `6: 10.0,` |
| `ev_engine._CENTRALITY_KEEP_BY_DIGIT.7` | `backend/app/core/ev_engine.py:115` | 5.0 | 对应序数的孤张靠张保留分 | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V0固定；V2冻结 | `7: 5.0,` |
| `ev_engine._CENTRALITY_KEEP_BY_DIGIT.8` | `backend/app/core/ev_engine.py:116` | 1.5 | 对应序数的孤张靠张保留分 | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V0固定；V2冻结 | `8: 1.5,` |
| `ev_engine._CENTRALITY_KEEP_BY_DIGIT.9` | `backend/app/core/ev_engine.py:117` | 0.0 | 对应序数的孤张靠张保留分 | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V0固定；V2冻结 | `9: 0.0,` |
| `ev_engine._honor_rem_factor.L1345C15` | `backend/app/core/ev_engine.py:1348` | 0.4 | 字牌孤张保留潜力对 Rem 的折现权重。；见表达式 | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | V0固定；V2冻结 | `return 0.4` |
| `ev_engine._evaluate_self_gang_candidates.L613C17` | `backend/app/core/ev_engine.py:613` | 3.0 | 评估暗杠/补杠：锁入高额杠分 + 岭上补张后再切的期望。；见表达式 | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | V0固定；V2冻结 | `settle = 3.0 if is_dealer else 2.0` |
| `ev_engine._evaluate_self_gang_candidates.L613C39` | `backend/app/core/ev_engine.py:613` | 2.0 | 评估暗杠/补杠：锁入高额杠分 + 岭上补张后再切的期望。；见表达式 | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | V0固定；V2冻结 | `settle = 3.0 if is_dealer else 2.0` |
| `ev_engine._evaluate_self_gang_candidates.L614C46` | `backend/app/core/ev_engine.py:614` | 0.35 | 评估暗杠/补杠：锁入高额杠分 + 岭上补张后再切的期望。；见表达式 | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | V0固定；V2冻结 | `bonus_ev = float(hu_bonus) * settle * 0.35` |
| `ev_engine._apply_close_ukeire_safety_dominance.L2144C18` | `backend/app/core/ev_engine.py:2147` | 0.1 | Account for a large danger gap when same-shanten ukeire is close.；见表达式 | 听牌概率 × 条件危险 × 胡数损失；与防守折让和风险倍率互相补偿 | V0固定；V2冻结 | `if risk < 0.10:` |
| `ev_engine.calculate_best_discards.L314C59` | `backend/app/core/ev_engine.py:314` | 2.0 | 枚举暗手切牌，按 Net_EV = 进攻 − 防守净损失 − 向听惩罚 排序。；见表达式 | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | V0固定；V2冻结 | `attack_ev += float(structure["delta"]) * (settle / 2.0)` |
| `ev_engine._guest_wind_hold_penalty.L1403C20` | `backend/app/core/ev_engine.py:1406` | 1.5 | 持有无役客风的占位惩罚（保留价值≈0，应优先切出）。；见表达式 | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | V0固定；V2冻结 | `scale = 1.5 if rem_n <= 1 else (1.2 if rem_n == 2 else 1.0)` |
| `ev_engine._guest_wind_hold_penalty.L1416C41` | `backend/app/core/ev_engine.py:1419` | 15.0 | 持有无役客风的占位惩罚（保留价值≈0，应优先切出）。；见表达式 | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | V0固定；V2冻结 | `penalty += min(base * scale, 15.0)` |
| `ev_engine._apply_close_ukeire_safety_dominance.L2161C71` | `backend/app/core/ev_engine.py:2164` | 0.1 | Account for a large danger gap when same-shanten ukeire is close.；见表达式 | 听牌概率 × 条件危险 × 胡数损失；与防守折让和风险倍率互相补偿 | V0固定；V2冻结 | `adjustment = max(0.0, risky["ev_score"] - leader["ev_score"] + 0.1)` |
| `ev_engine._discard_candidate_note.L2385C67` | `backend/app/core/ev_engine.py:2388` | 0.4 | 生成切牌候选说明（多向听突出客风/役牌/搭子取舍）。；见表达式 | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | V0固定；V2冻结；仅说明文案 | `has_yakuhai = yakuhai_score >= _YAKUHAI_SINGLE_POTENTIAL * 0.4` |
| `ev_engine.calculate_best_discards.L332C48` | `backend/app/core/ev_engine.py:332` | 0.5 | 枚举暗手切牌，按 Net_EV = 进攻 − 防守净损失 − 向听惩罚 排序。；见表达式 | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | V0固定；V2冻结 | `net_unit = max(threat["loss_ron"] * 0.5, threat["loss_ron"] - rebate)` |
| `ev_engine.calculate_best_discards.L333C72` | `backend/app/core/ev_engine.py:333` | 2.0 | 枚举暗手切牌，按 Net_EV = 进攻 − 防守净损失 − 向听惩罚 排序。；见表达式 | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | V0固定；V2冻结 | `risk_weight = 1.0 + min(p_dealin / _DEFENSE_RISK_REFERENCE, 2.0)` |
| `ev_engine.calculate_best_discards.L482C44` | `backend/app/core/ev_engine.py:482` | 12.0 | 枚举暗手切牌，按 Net_EV = 进攻 − 防守净损失 − 向听惩罚 排序。；见表达式 | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | V0固定；V2冻结 | `float(best_gang["ev_score"]) + (12.0 if best_gang["action_type"] == "bu_gang" else 0.0),` |
| `ev_engine._guest_wind_hold_penalty.L1403C44` | `backend/app/core/ev_engine.py:1406` | 1.2 | 持有无役客风的占位惩罚（保留价值≈0，应优先切出）。；见表达式 | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | V0固定；V2冻结 | `scale = 1.5 if rem_n <= 1 else (1.2 if rem_n == 2 else 1.0)` |
| `ev_engine._central_synergy_keep_score.L1688C60` | `backend/app/core/ev_engine.py:1691` | 8.0 | 中张单张配合同色既有搭子的改良价值，按两面靠张物理供给衰减。；见表达式 | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | V0固定；V2冻结 | `total += _CENTRAL_SYNERGY_KEEP_BONUS * min(supply / 8.0, 1.0)` |
| `ev_engine._discard_candidate_note.L2384C69` | `backend/app/core/ev_engine.py:2387` | 0.5 | 生成切牌候选说明（多向听突出客风/役牌/搭子取舍）。；见表达式 | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | V0固定；V2冻结；仅说明文案 | `has_complex = shape_score >= (_SHAPE_PAIR + _SHAPE_RYANMEN * 0.5)` |
| `ev_engine._discard_candidate_note.L2270C58` | `backend/app/core/ev_engine.py:2273` | 8.0 | 生成切牌候选说明（多向听突出客风/役牌/搭子取舍）。；见表达式 | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | V0固定；V2冻结；仅说明文案 | `_centrality_keep_score(t, dealer_tile) >= 8.0` |
| `ev_engine._apply_isolated_tile_shape_dominance.L2122C76` | `backend/app/core/ev_engine.py:2125` | 1.35 | Do not break a pair/run core when an isolated tile improves both ukeire and safety.；见表达式 | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | V0固定；V2冻结 | `and c["effective_count"] >= core["effective_count"] * 1.35` |
| `ev_engine._apply_isolated_tile_shape_dominance.L2124C37` | `backend/app/core/ev_engine.py:2127` | 0.03 | Do not break a pair/run core when an isolated tile improves both ukeire and safety.；见表达式 | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | V0固定；V2冻结 | `<= core_risk - 0.03]` |
| `ev_engine._apply_close_ukeire_safety_dominance.L2154C80` | `backend/app/core/ev_engine.py:2157` | 0.78 | Account for a large danger gap when same-shanten ukeire is close.；见表达式 | 听牌概率 × 条件危险 × 胡数损失；与防守折让和风险倍率互相补偿 | V0固定；V2冻结 | `and candidate["effective_count"] >= risky["effective_count"] * 0.78` |
| `ev_engine._discard_candidate_note.L2282C62` | `backend/app/core/ev_engine.py:2285` | 8.0 | 生成切牌候选说明（多向听突出客风/役牌/搭子取舍）。；见表达式 | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | V0固定；V2冻结；仅说明文案 | `and _centrality_keep_score(t, dealer_tile) >= 8.0` |
| `ev_engine.calculate_best_discards.L477C40` | `backend/app/core/ev_engine.py:477` | 12.0 | 枚举暗手切牌，按 Net_EV = 进攻 − 防守净损失 − 向听惩罚 排序。；见表达式 | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | V0固定；V2冻结 | `float(g["ev_score"]) + (12.0 if g["action_type"] == "bu_gang" else 0.0),` |
| `ev_engine._structure_attack_adjustment.L1807C62` | `backend/app/core/ev_engine.py:1810` | 8.0 | 雀头保护 / 孤张切除 / 靠张中心度 / 百搭中张保护 / 好形推进。；见表达式 | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | V0固定；V2冻结 | `_centrality_keep_score(t, dealer_tile) >= 8.0` |
| `ev_engine._apply_close_ukeire_safety_dominance.L2156C31` | `backend/app/core/ev_engine.py:2159` | 0.04 | Account for a large danger gap when same-shanten ukeire is close.；见表达式 | 听牌概率 × 条件危险 × 胡数损失；与防守折让和风险倍率互相补偿 | V0固定；V2冻结 | `<= min(risk - 0.04, risk * 0.70)` |
| `ev_engine._apply_close_ukeire_safety_dominance.L2156C44` | `backend/app/core/ev_engine.py:2159` | 0.7 | Account for a large danger gap when same-shanten ukeire is close.；见表达式 | 听牌概率 × 条件危险 × 胡数损失；与防守折让和风险倍率互相补偿 | V0固定；V2冻结 | `<= min(risk - 0.04, risk * 0.70)` |
| `ev_engine._structure_attack_adjustment.L1896C25` | `backend/app/core/ev_engine.py:1899` | 0.7 | 雀头保护 / 孤张切除 / 靠张中心度 / 百搭中张保护 / 好形推进。；见表达式 | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | V0固定；V2冻结 | `factor = 0.7 if rem_n == 2 else 0.35` |
| `ev_engine._structure_attack_adjustment.L1896C48` | `backend/app/core/ev_engine.py:1899` | 0.35 | 雀头保护 / 孤张切除 / 靠张中心度 / 百搭中张保护 / 好形推进。；见表达式 | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | V0固定；V2冻结 | `factor = 0.7 if rem_n == 2 else 0.35` |
| `ev_engine._RINSHAN_SAMPLE_CAP` | `backend/app/core/ev_engine.py:60` | 12 | _RINSHAN_SAMPLE_CAP | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | 源码固定；未进入165项 | `_RINSHAN_SAMPLE_CAP = 12` |
| `ev_engine._TENPAI_RYANMEN_BASELINE` | `backend/app/core/ev_engine.py:66` | 8 | 标准两面等待的可摸张数；听牌胡分须计入命中机会 | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | 源码固定；未进入165项 | `_TENPAI_RYANMEN_BASELINE = 8  # 标准两面等待的可摸张数；听牌胡分须计入命中机会` |
| `ev_engine._MAX_DISCARD_CANDIDATES` | `backend/app/core/ev_engine.py:99` | 8 | 弱搭填充上限；漂浮孤张全部保留不受挤出 | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | 源码固定；未进入165项 | `_MAX_DISCARD_CANDIDATES = 8  # 弱搭填充上限；漂浮孤张全部保留不受挤出` |
| `ev_engine.L772C27` | `backend/app/core/ev_engine.py:772` | 2.0 | §6 非对称支付（无包牌）：庄相关全额，闲对闲半额。；见表达式 | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | 规则固定/禁止调优 | `return float(points) / 2.0` |
| `ev_engine.L2855C11` | `backend/app/core/ev_engine.py:2855` | 3.0 | 自摸和牌收入系数：庄 ×3，闲 ×2（§6）。；见表达式 | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | 规则固定/禁止调优 | `return 3.0 if is_dealer else 2.0` |
| `ev_engine.L2855C33` | `backend/app/core/ev_engine.py:2855` | 2.0 | 自摸和牌收入系数：庄 ×3，闲 ×2（§6）。；见表达式 | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | 规则固定/禁止调优 | `return 3.0 if is_dealer else 2.0` |
| `ev_engine.L478C50` | `backend/app/core/ev_engine.py:478` | 1.0 | 补杠强制领先余量 | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | 硬护栏/参考尺度固定，不独立搜索 | `float(best_discard["ev_score"]) + 1.0 if g["action_type"] == "bu_gang" else float(g["ev_score"]),` |
| `ev_engine.L483C46` | `backend/app/core/ev_engine.py:483` | 1.0 | 补杠强制领先余量 | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | 硬护栏/参考尺度固定，不独立搜索 | `float(best_discard["ev_score"]) + 1.0 if best_gang["action_type"] == "bu_gang" else float(best_gang["ev_score"]),` |
| `ev_engine.L2041C76` | `backend/app/core/ev_engine.py:2041` | 1.0 | 客风优势排序余量 | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | 硬护栏/参考尺度固定，不独立搜索 | `target = max(c["ev_score"] for c in dominated) + _EV_NEAR_TIE_EPS + 1.0` |
| `ev_engine.L2081C80` | `backend/app/core/ev_engine.py:2081` | 1.0 | 场见客风优势排序余量 | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | 硬护栏/参考尺度固定，不独立搜索 | `target = max(c["ev_score"] for c in less_seen) + _EV_NEAR_TIE_EPS + 1.0` |
| `ev_engine.L2131C36` | `backend/app/core/ev_engine.py:2131` | 1.0 | 孤张优势排序余量 | 与 SHANTEN_PENALTY、进张/结构分及防守扣分共同决定弃牌排序 | 硬护栏/参考尺度固定，不独立搜索 | `margin = _EV_NEAR_TIE_EPS + 1.0` |

#### call_decision（46项）

| 名称 | 当前文件:行 | 当前值 | 作用 | 耦合关系 | 状态 | 当前源码表达式 |
|---|---|---:|---|---|---|---|
| `call_decision._CALL_TENPAI_TEMPO_BONUS` | `backend/app/core/call_decision.py:53` | 60.0 | 副露直接进听节奏奖励 | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | V0固定；V2冻结 | `_CALL_TENPAI_TEMPO_BONUS = 60.0` |
| `call_decision._DEALER_TENPAI_CONTINUATION_BONUS` | `backend/app/core/call_decision.py:54` | 20.0 | 庄家副露进听额外奖励 | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | V0固定；V2冻结 | `_DEALER_TENPAI_CONTINUATION_BONUS = 20.0` |
| `call_decision._WIN_PASS_OPTION_CREDIT` | `backend/app/core/call_decision.py:56` | 16.8 | HU/PASS 比较的保留机会值 | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | V0固定；V2冻结 | `_WIN_PASS_OPTION_CREDIT = 16.8` |
| `call_decision._JUNK_CUT_SPEED_BONUS_MIN` | `backend/app/core/call_decision.py:58` | 15.0 | 碰后切废牌奖励下限 | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | V0固定；V2冻结 | `_JUNK_CUT_SPEED_BONUS_MIN = 15.0` |
| `call_decision._JUNK_CUT_SPEED_BONUS_MAX` | `backend/app/core/call_decision.py:59` | 25.0 | 碰后切废牌奖励上限 | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | V0固定；V2冻结 | `_JUNK_CUT_SPEED_BONUS_MAX = 25.0` |
| `call_decision._PONG_HU_EV_SCALE` | `backend/app/core/call_decision.py:61` | 2.5 | 碰底胡转 EV 倍率 | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | V0固定；V2冻结 | `_PONG_HU_EV_SCALE = 2.5` |
| `call_decision._REDUNDANT_SEQUENCE_CHI_PENALTY` | `backend/app/core/call_decision.py:65` | 55.0 | 冗余完整顺子吃牌罚分 | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | V0固定；V2冻结 | `_REDUNDANT_SEQUENCE_CHI_PENALTY = 55.0` |
| `call_decision._NO_SHANTEN_DROP_CALL_PENALTY` | `backend/app/core/call_decision.py:67` | 18.0 | 副露不降向听罚分 | SHANTEN_PENALTY 与 DEEP_SHANTEN_UNIT 在深向听近似中叠加，勿同时放大 | V0固定；V2冻结 | `_NO_SHANTEN_DROP_CALL_PENALTY = 18.0` |
| `call_decision._PASS_DRAW_TURN_BASE` | `backend/app/core/call_decision.py:69` | 22.0 | PASS 下一摸基础机会值 | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | V0固定；V2冻结 | `_PASS_DRAW_TURN_BASE = 22.0` |
| `call_decision._PASS_DRAW_UKEIRE_SCALE` | `backend/app/core/call_decision.py:70` | 0.35 | 每张有效进张额外加成（封顶见下） | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | V0固定；V2冻结 | `_PASS_DRAW_UKEIRE_SCALE = 0.35  # 每张有效进张额外加成（封顶见下）` |
| `call_decision._YAKUHAI_FAN_MAKE_CHANCE.0` | `backend/app/core/call_decision.py:63` | 0.25 | 按向听档折现役牌成番机会 | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V0固定；V2冻结 | `_YAKUHAI_FAN_MAKE_CHANCE = {0: 0.25, 1: 0.65}` |
| `call_decision._YAKUHAI_FAN_MAKE_CHANCE.1` | `backend/app/core/call_decision.py:63` | 0.65 | 按向听档折现役牌成番机会 | 与进张质量、雀头/孤张奖惩共同计分；同类切除奖励与保留罚分可能重复 | V0固定；V2冻结 | `_YAKUHAI_FAN_MAKE_CHANCE = {0: 0.25, 1: 0.65}` |
| `call_decision._hard_hu_discount.L346C11` | `backend/app/core/call_decision.py:372` | 0.15 | 硬胡翻倍（×2）期待收益的向听折现系数。；见表达式 | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | V0固定；V2冻结 | `return 0.15` |
| `call_decision._hard_hu_discount.L345C15` | `backend/app/core/call_decision.py:371` | 0.5 | 硬胡翻倍（×2）期待收益的向听折现系数。；见表达式 | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | V0固定；V2冻结 | `return 0.5` |
| `call_decision._early_flush_ambition_bonus.L399C23` | `backend/app/core/call_decision.py:425` | 200.0 | 为极早巡、低风险的深单色胚子估算保留大牌路线的期望价值。；见表达式 | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | V0固定；V2冻结 | `projected_points = 200.0 if honors else 260.0` |
| `call_decision._early_flush_ambition_bonus.L399C44` | `backend/app/core/call_decision.py:425` | 260.0 | 为极早巡、低风险的深单色胚子估算保留大牌路线的期望价值。；见表达式 | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | V0固定；V2冻结 | `projected_points = 200.0 if honors else 260.0` |
| `call_decision._early_flush_ambition_bonus.L400C27` | `backend/app/core/call_decision.py:426` | 0.48 | 为极早巡、低风险的深单色胚子估算保留大牌路线的期望价值。；见表达式 | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | V0固定；V2冻结 | `make_probability = min(0.48, 0.18 + 0.025 * (suit_count - 8) + 0.035 * max(0, 3 - off_suit))` |
| `call_decision._early_flush_ambition_bonus.L401C24` | `backend/app/core/call_decision.py:427` | 0.92 | 为极早巡、低风险的深单色胚子估算保留大牌路线的期望价值。；见表达式 | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | V0固定；V2冻结 | `make_probability *= 0.92 ** len(melds)` |
| `call_decision._pong_incentive.L461C48` | `backend/app/core/call_decision.py:487` | 0.85 | 碰牌收益量化：幺九/字底胡 + 废牌即切加速。；见表达式 | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | V0固定；V2冻结 | `hu_weight = 1.0 if shanten_before <= 1 else 0.85` |
| `call_decision._pong_incentive.L522C17` | `backend/app/core/call_decision.py:548` | 12.0 | 碰牌收益量化：幺九/字底胡 + 废牌即切加速。；见表达式 | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | V0固定；V2冻结 | `bonus += 12.0` |
| `call_decision._early_flush_ambition_bonus.L391C42` | `backend/app/core/call_decision.py:417` | 0.15 | 为极早巡、低风险的深单色胚子估算保留大牌路线的期望价值。；见表达式 | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | V0固定；V2冻结 | `if tenpai and max(tenpai.values()) >= 0.15:` |
| `call_decision._early_flush_ambition_bonus.L402C29` | `backend/app/core/call_decision.py:428` | 12.0 | 为极早巡、低风险的深单色胚子估算保留大牌路线的期望价值。；见表达式 | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | V0固定；V2冻结 | `safety_credit = max(0.0, 12.0 * (1.0 - (max(tenpai.values()) if tenpai else 0.03) / 0.15))` |
| `call_decision._pong_incentive.L460C33` | `backend/app/core/call_decision.py:486` | 1.15 | 碰牌收益量化：幺九/字底胡 + 废牌即切加速。；见表达式 | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | V0固定；V2冻结 | `scale = _PONG_HU_EV_SCALE * (1.15 if is_dealer else 1.0)` |
| `call_decision._pong_incentive.L481C66` | `backend/app/core/call_decision.py:507` | 0.45 | 碰牌收益量化：幺九/字底胡 + 废牌即切加速。；见表达式 | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | V0固定；V2冻结 | `make_chance = _YAKUHAI_FAN_MAKE_CHANCE.get(shanten_after, 0.45)` |
| `call_decision._evaluate_call_ev.L585C52` | `backend/app/core/call_decision.py:611` | 0.85 | _evaluate_call_ev；见表达式 | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | V0固定；V2冻结 | `hu_weight = 1.0 if shanten_before <= 1 else 0.85` |
| `call_decision._evaluate_pass_ev.L738C26` | `backend/app/core/call_decision.py:789` | 1.15 | 过牌：等待进张估进攻 EV − 向听×120 + 自摸巡摸牌权价值。；见表达式 | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | V0固定；V2冻结 | `draw_bonus *= 1.15` |
| `call_decision.evaluate_call_decision.L215C22` | `backend/app/core/call_decision.py:220` | 0.55 | 比较吃/碰/杠与过牌的净 EV，给出推荐响应。；见表达式 | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | V0固定；V2冻结 | `ev *= 0.55` |
| `call_decision.evaluate_call_decision.L301C53` | `backend/app/core/call_decision.py:309` | 0.85 | 比较吃/碰/杠与过牌的净 EV，给出推荐响应。；见表达式 | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | V0固定；V2冻结 | `hu_weight = 1.0 if shanten_now <= 1 else 0.85` |
| `call_decision._early_flush_ambition_bonus.L400C33` | `backend/app/core/call_decision.py:426` | 0.18 | 为极早巡、低风险的深单色胚子估算保留大牌路线的期望价值。；见表达式 | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | V0固定；V2冻结 | `make_probability = min(0.48, 0.18 + 0.025 * (suit_count - 8) + 0.035 * max(0, 3 - off_suit))` |
| `call_decision._early_flush_ambition_bonus.L400C67` | `backend/app/core/call_decision.py:426` | 0.035 | 为极早巡、低风险的深单色胚子估算保留大牌路线的期望价值。；见表达式 | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | V0固定；V2冻结 | `make_probability = min(0.48, 0.18 + 0.025 * (suit_count - 8) + 0.035 * max(0, 3 - off_suit))` |
| `call_decision._evaluate_call_ev.L610C69` | `backend/app/core/call_decision.py:645` | 4.0 | _evaluate_call_ev；见表达式 | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | V0固定；V2冻结 | `live_wait_weight = min(1.0, float(best['effective_count']) / 4.0)` |
| `call_decision.evaluate_call_decision.L304C50` | `backend/app/core/call_decision.py:312` | 0.35 | 比较吃/碰/杠与过牌的净 EV，给出推荐响应。；见表达式 | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | V0固定；V2冻结 | `+ _PASS_DRAW_TURN_BASE * 0.35)` |
| `call_decision._early_flush_ambition_bonus.L400C40` | `backend/app/core/call_decision.py:426` | 0.025 | 为极早巡、低风险的深单色胚子估算保留大牌路线的期望价值。；见表达式 | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | V0固定；V2冻结 | `make_probability = min(0.48, 0.18 + 0.025 * (suit_count - 8) + 0.035 * max(0, 3 - off_suit))` |
| `call_decision._early_flush_ambition_bonus.L402C88` | `backend/app/core/call_decision.py:428` | 0.15 | 为极早巡、低风险的深单色胚子估算保留大牌路线的期望价值。；见表达式 | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | V0固定；V2冻结 | `safety_credit = max(0.0, 12.0 * (1.0 - (max(tenpai.values()) if tenpai else 0.03) / 0.15))` |
| `call_decision._pong_incentive.L515C16` | `backend/app/core/call_decision.py:541` | 2.0 | 碰牌收益量化：幺九/字底胡 + 废牌即切加速。；见表达式 | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | V0固定；V2冻结 | `) / 2.0` |
| `call_decision._evaluate_call_ev.L586C40` | `backend/app/core/call_decision.py:612` | 1.15 | _evaluate_call_ev；见表达式 | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | V0固定；V2冻结 | `ev += hu * _PONG_HU_EV_SCALE * (1.15 if is_dealer else 1.0) * hu_weight` |
| `call_decision._early_flush_ambition_bonus.L402C80` | `backend/app/core/call_decision.py:428` | 0.03 | 为极早巡、低风险的深单色胚子估算保留大牌路线的期望价值。；见表达式 | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | V0固定；V2冻结 | `safety_credit = max(0.0, 12.0 * (1.0 - (max(tenpai.values()) if tenpai else 0.03) / 0.15))` |
| `call_decision.evaluate_call_decision.L303C28` | `backend/app/core/call_decision.py:311` | 1.15 | 比较吃/碰/杠与过牌的净 EV，给出推荐响应。；见表达式 | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | V0固定；V2冻结 | `* (1.15 if is_dealer else 1.0) * hu_weight` |
| `call_decision._PASS_DRAW_UKEIRE_CAP` | `backend/app/core/call_decision.py:71` | 20 | PASS 进张奖励封顶张数 | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | 源码固定；未进入165项 | `_PASS_DRAW_UKEIRE_CAP = 20` |
| `call_decision._EARLY_FLUSH_MIN_SUIT_TILES` | `backend/app/core/call_decision.py:72` | 8 | 早巡染手主色最少张数 | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | 源码固定；未进入165项 | `_EARLY_FLUSH_MIN_SUIT_TILES = 8` |
| `call_decision._EARLY_FLUSH_MIN_HAND_TILES` | `backend/app/core/call_decision.py:73` | 10 | 早巡染手主色加字牌最少张数 | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | 源码固定；未进入165项 | `_EARLY_FLUSH_MIN_HAND_TILES = 10` |
| `call_decision.L196C31` | `backend/app/core/call_decision.py:196` | 10 | 计分失败时胡数回退 | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | 硬护栏/参考尺度固定，不独立搜索 | `est_final_points = 10` |
| `call_decision.L328C33` | `backend/app/core/call_decision.py:328` | 1.0 | 冗余吃牌展示分低于PASS的硬余量 | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | 硬护栏/参考尺度固定，不独立搜索 | `net_ev=pass_ev - 1.0,` |
| `call_decision.L406C14` | `backend/app/core/call_decision.py:406` | 3 | 早巡染手最大巡数 | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | 硬护栏/参考尺度固定，不独立搜索 | `if turn > 3:` |
| `call_decision.L426C62` | `backend/app/core/call_decision.py:426` | 8 | 染手主色/杂色参考张数 | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | 硬护栏/参考尺度固定，不独立搜索 | `make_probability = min(0.48, 0.18 + 0.025 * (suit_count - 8) + 0.035 * max(0, 3 - off_suit))` |
| `call_decision.L426C82` | `backend/app/core/call_decision.py:426` | 3 | 染手主色/杂色参考张数 | 与 PASS 摸牌补偿、弃牌 EV、听牌奖励及碰底胡激励竞争 | 硬护栏/参考尺度固定，不独立搜索 | `make_probability = min(0.48, 0.18 + 0.025 * (suit_count - 8) + 0.035 * max(0, 3 - off_suit))` |

#### screen（8项）

| 名称 | 当前文件:行 | 当前值 | 作用 | 耦合关系 | 状态 | 当前源码表达式 |
|---|---|---:|---|---|---|---|
| `screen.joker_keep` | `backend/tools/arena.py:113` | 100 | 财神保留分 | 仅 fast 保留牌排序；不进入完整 EV | V0固定；V2冻结；仅fast | `if tile == match.god: return w['screen.joker_keep']` |
| `screen.duplicate_keep` | `backend/tools/arena.py:114` | 12 | 重复张保留分 | 仅 fast 保留牌排序；不进入完整 EV | V0固定；V2冻结；仅fast | `value = (counts[tile]-1)*w['screen.duplicate_keep']` |
| `screen.central_keep` | `backend/tools/arena.py:118` | 1 | 中心度倍率 | 仅 fast 保留牌排序；不进入完整 EV | V0固定；V2冻结；仅fast | `value += (4-abs(5-rank))*w['screen.central_keep']` |
| `screen.neighbor_keep` | `backend/tools/arena.py:119` | 5 | 邻张连接分 | 仅 fast 保留牌排序；不进入完整 EV | V0固定；V2冻结；仅fast | `for d in (-2,-1,1,2): value += counts.get(f'{rank+d}{suit}',0)*w['screen.'+('neighbor_keep' if abs(d)==1 else 'gap_keep')]` |
| `screen.gap_keep` | `backend/tools/arena.py:119` | 2 | 隔张连接分 | 仅 fast 保留牌排序；不进入完整 EV | V0固定；V2冻结；仅fast | `for d in (-2,-1,1,2): value += counts.get(f'{rank+d}{suit}',0)*w['screen.'+('neighbor_keep' if abs(d)==1 else 'gap_keep')]` |
| `screen.honor_keep` | `backend/tools/arena.py:120` | 2 | 役牌保留分 | 仅 fast 保留牌排序；不进入完整 EV | V0固定；V2冻结；仅fast | `elif face in (seat,'C','F','P'): value += w['screen.honor_keep']` |
| `screen.danger_penalty` | `backend/tools/arena.py:121` | 0 | 危险牌保留分 | 仅 fast 保留牌排序；不进入完整 EV | V0固定；V2冻结；仅fast | `if w['screen.danger_penalty']:` |
| `screen.call_bonus` | `backend/tools/arena.py:104` | 1 | 是否吃进碰杠的开关阈值（>=1） | 仅 fast 保留牌排序；不进入完整 EV | V0固定；V2冻结；仅fast | `return claim if claim and w['screen.call_bonus'] >= 1 else next(a for a in rows if a['action_type'] == 'pass')` |

#### scoring（23项）

| 名称 | 当前文件:行 | 当前值 | 作用 | 耦合关系 | 状态 | 当前源码表达式 |
|---|---|---:|---|---|---|---|
| `scoring.DEFAULT_BASE_HU` | `backend/app/core/scoring.py:31` | 10 | 胡牌者底胡 | 进入实际胡数与结算；不是可学习的策略权重 | 规则固定/禁止调优 | `DEFAULT_BASE_HU = 10` |
| `scoring.MAX_PAYMENT_PER_PLAYER` | `backend/app/core/scoring.py:32` | 100 | 单家单局实际支付上限；不截断牌型 final_hu | 进入实际胡数与结算；不是可学习的策略权重 | 规则固定/禁止调优 | `MAX_PAYMENT_PER_PLAYER = 100  # 单家单局实际支付上限；不截断牌型 final_hu` |
| `scoring.PAIR_SEAT_WIND_HU` | `backend/app/core/scoring.py:35` | 2 | 自家门风对 | 进入实际胡数与结算；不是可学习的策略权重 | 规则固定/禁止调优 | `PAIR_SEAT_WIND_HU = 2  # 自家门风对` |
| `scoring.PAIR_DRAGON_HU` | `backend/app/core/scoring.py:36` | 2 | 中 / 发 / 白 对 | 进入实际胡数与结算；不是可学习的策略权重 | 规则固定/禁止调优 | `PAIR_DRAGON_HU = 2  # 中 / 发 / 白 对` |
| `scoring.PAIR_NORMAL_HU` | `backend/app/core/scoring.py:37` | 0 | 普通对子 | 进入实际胡数与结算；不是可学习的策略权重 | 规则固定/禁止调优 | `PAIR_NORMAL_HU = 0  # 普通对子` |
| `scoring.PONG_TERMINAL_HONOR_HU` | `backend/app/core/scoring.py:40` | 4 | 风 / 幺九 / 字 | 进入实际胡数与结算；不是可学习的策略权重 | 规则固定/禁止调优 | `PONG_TERMINAL_HONOR_HU = 4  # 风 / 幺九 / 字` |
| `scoring.PONG_SIMPLE_HU` | `backend/app/core/scoring.py:41` | 2 | 2~8 中张 | 进入实际胡数与结算；不是可学习的策略权重 | 规则固定/禁止调优 | `PONG_SIMPLE_HU = 2  # 2~8 中张` |
| `scoring.ANKO_TERMINAL_HONOR_HU` | `backend/app/core/scoring.py:44` | 8 | 幺九字牌暗刻胡数 | 进入实际胡数与结算；不是可学习的策略权重 | 规则固定/禁止调优 | `ANKO_TERMINAL_HONOR_HU = 8` |
| `scoring.ANKO_SIMPLE_HU` | `backend/app/core/scoring.py:45` | 4 | 中张暗刻胡数 | 进入实际胡数与结算；不是可学习的策略权重 | 规则固定/禁止调优 | `ANKO_SIMPLE_HU = 4` |
| `scoring.MING_GANG_TERMINAL_HONOR_HU` | `backend/app/core/scoring.py:48` | 16 | 幺九字牌明杠胡数 | 进入实际胡数与结算；不是可学习的策略权重 | 规则固定/禁止调优 | `MING_GANG_TERMINAL_HONOR_HU = 16` |
| `scoring.MING_GANG_SIMPLE_HU` | `backend/app/core/scoring.py:49` | 8 | 中张明杠胡数 | 进入实际胡数与结算；不是可学习的策略权重 | 规则固定/禁止调优 | `MING_GANG_SIMPLE_HU = 8` |
| `scoring.AN_GANG_TERMINAL_HONOR_HU` | `backend/app/core/scoring.py:52` | 32 | 幺九字牌暗杠胡数 | 进入实际胡数与结算；不是可学习的策略权重 | 规则固定/禁止调优 | `AN_GANG_TERMINAL_HONOR_HU = 32` |
| `scoring.AN_GANG_SIMPLE_HU` | `backend/app/core/scoring.py:53` | 16 | 中张暗杠胡数 | 进入实际胡数与结算；不是可学习的策略权重 | 规则固定/禁止调优 | `AN_GANG_SIMPLE_HU = 16` |
| `scoring.ZIMO_HU` | `backend/app/core/scoring.py:56` | 2 | 自摸只加胡、不加番 | 进入实际胡数与结算；不是可学习的策略权重 | 规则固定/禁止调优 | `ZIMO_HU = 2  # 自摸只加胡、不加番` |
| `scoring.KANZHANG_HU` | `backend/app/core/scoring.py:57` | 2 | 嵌档（卡张） | 进入实际胡数与结算；不是可学习的策略权重 | 规则固定/禁止调优 | `KANZHANG_HU = 2  # 嵌档（卡张）` |
| `scoring.CHI_HU` | `backend/app/core/scoring.py:58` | 0 | 顺子恒 0 | 进入实际胡数与结算；不是可学习的策略权重 | 规则固定/禁止调优 | `CHI_HU = 0  # 顺子恒 0` |
| `scoring.FAN_DRAGON_PUNG_OR_KONG` | `backend/app/core/scoring.py:61` | 1 | 中/发/白 每组刻或杠 | 进入实际胡数与结算；不是可学习的策略权重 | 规则固定/禁止调优 | `FAN_DRAGON_PUNG_OR_KONG = 1  # 中/发/白 每组刻或杠` |
| `scoring.FAN_SEAT_WIND_PUNG_OR_KONG` | `backend/app/core/scoring.py:62` | 1 | 自家门风刻或杠 | 进入实际胡数与结算；不是可学习的策略权重 | 规则固定/禁止调优 | `FAN_SEAT_WIND_PUNG_OR_KONG = 1  # 自家门风刻或杠` |
| `scoring.FAN_HARD_HU` | `backend/app/core/scoring.py:63` | 1 | 硬碰硬（无「得」作百搭） | 进入实际胡数与结算；不是可学习的策略权重 | 规则固定/禁止调优 | `FAN_HARD_HU = 1  # 硬碰硬（无「得」作百搭）` |
| `scoring.FAN_RESTORED_JOKER` | `backend/app/core/scoring.py:64` | 1 | 得还原：每张 +1，最多 3 | 进入实际胡数与结算；不是可学习的策略权重 | 规则固定/禁止调优 | `FAN_RESTORED_JOKER = 1  # 得还原：每张 +1，最多 3` |
| `scoring.MAX_RESTORED_JOKER_FAN` | `backend/app/core/scoring.py:65` | 3 | 得还原番数上限 | 进入实际胡数与结算；不是可学习的策略权重 | 规则固定/禁止调优 | `MAX_RESTORED_JOKER_FAN = 3` |
| `scoring.FAN_HALF_FLUSH` | `backend/app/core/scoring.py:66` | 1 | 混一色 | 进入实际胡数与结算；不是可学习的策略权重 | 规则固定/禁止调优 | `FAN_HALF_FLUSH = 1  # 混一色` |
| `scoring.FAN_FULL_FLUSH` | `backend/app/core/scoring.py:67` | 3 | 清一色（与混一色互斥，取清） | 进入实际胡数与结算；不是可学习的策略权重 | 规则固定/禁止调优 | `FAN_FULL_FLUSH = 3  # 清一色（与混一色互斥，取清）` |

#### evaluator（2项）

| 名称 | 当前文件:行 | 当前值 | 作用 | 耦合关系 | 状态 | 当前源码表达式 |
|---|---|---:|---|---|---|---|
| `evaluator.L754C13` | `backend/app/core/evaluator.py:754` | 3.0 | _check_complete_win；见表达式 | 与 scoring 和 settlement 的庄闲结算一致 | 规则固定/禁止调优 | `factor = 3.0 if is_dealer else 2.0` |
| `evaluator.L754C35` | `backend/app/core/evaluator.py:754` | 2.0 | _check_complete_win；见表达式 | 与 scoring 和 settlement 的庄闲结算一致 | 规则固定/禁止调优 | `factor = 3.0 if is_dealer else 2.0` |

#### settlement（4项）

| 名称 | 当前文件:行 | 当前值 | 作用 | 耦合关系 | 状态 | 当前源码表达式 |
|---|---|---:|---|---|---|---|
| `settlement.L219C21` | `backend/app/core/settlement.py:219` | 2.0 | 计算四人终局筹码净变动（含主支付 + 固有胡头副结算）。；见表达式 | 与胡数、庄闲关系和单家支付上限一致 | 规则固定/禁止调优 | `half = pts / 2.0` |
| `settlement.L244C74` | `backend/app/core/settlement.py:244` | 2.0 | 计算四人终局筹码净变动（含主支付 + 固有胡头副结算）。；见表达式 | 与胡数、庄闲关系和单家支付上限一致 | 规则固定/禁止调优 | `pay = (hb - ha) if table[a].get("is_dealer") else (hb - ha) / 2.0` |
| `settlement.L255C74` | `backend/app/core/settlement.py:255` | 2.0 | 计算四人终局筹码净变动（含主支付 + 固有胡头副结算）。；见表达式 | 与胡数、庄闲关系和单家支付上限一致 | 规则固定/禁止调优 | `pay = (ha - hb) if table[b].get("is_dealer") else (ha - hb) / 2.0` |
| `settlement.L299C63` | `backend/app/core/settlement.py:299` | 2.0 | 计算四人终局筹码净变动（含主支付 + 固有胡头副结算）。；见表达式 | 与胡数、庄闲关系和单家支付上限一致 | 规则固定/禁止调优 | `min(pts if win_is_dealer else pts / 2.0, MAX_PAYMENT_PER_PLAYER)),` |

#### claim_v2（8项）

| 名称 | 当前文件:行 | 当前值 | 作用 | 耦合关系 | 状态 | 当前源码表达式 |
|---|---|---:|---|---|---|---|
| `claim_v2.L191C61` | `backend/app/core/claim_v2.py:191` | 1.0 | 直接进听奖励折现上限 | 共享 V1 待摸估值、PASS 摸牌补偿；不得与旧副露奖励叠加 | 硬护栏/参考尺度固定，不独立搜索 | `value += w['claim_to_tenpai_reward']*min(1., after['count']/4.)` |
| `claim_v2.L191C80` | `backend/app/core/claim_v2.py:191` | 4.0 | 直接进听奖励满额所需活张数 | 共享 V1 待摸估值、PASS 摸牌补偿；不得与旧副露奖励叠加 | 硬护栏/参考尺度固定，不独立搜索 | `value += w['claim_to_tenpai_reward']*min(1., after['count']/4.)` |
| `claim_v2.L198C55` | `backend/app/core/claim_v2.py:198` | 1.0 | 被支配吃牌至少低于PASS的硬余量 | 共享 V1 待摸估值、PASS 摸牌补偿；不得与旧副露奖励叠加 | 硬护栏/参考尺度固定，不独立搜索 | `value = min(value, pass_ev-max(1., w['redundant_chow_penalty']))` |
| `claim_v2.redundant_chow_penalty` | `backend/app/core/claim_v2.py:11` | 55.0 | 冗余吃牌罚分 | 共享 V1 待摸估值、PASS 摸牌补偿；不得与旧副露奖励叠加 | V2已搜索但未晋升；生产未启用 | `'redundant_chow_penalty': (45., 60.),；DEFAULTS 见第17行` |
| `claim_v2.no_advance_chow_penalty` | `backend/app/core/claim_v2.py:12` | 18.0 | 吃后向听不降罚分 | 共享 V1 待摸估值、PASS 摸牌补偿；不得与旧副露奖励叠加 | V2已搜索但未晋升；生产未启用 | `'no_advance_chow_penalty': (15., 22.),；DEFAULTS 见第17行` |
| `claim_v2.claim_to_tenpai_reward` | `backend/app/core/claim_v2.py:13` | 40.0 | 直接进听奖励（按活张折现） | 共享 V1 待摸估值、PASS 摸牌补偿；不得与旧副露奖励叠加 | V2已搜索但未晋升；生产未启用 | `'claim_to_tenpai_reward': (35., 45.),；DEFAULTS 见第17行` |
| `claim_v2.pung_value_incentive` | `backend/app/core/claim_v2.py:14` | 1.0 | 非听牌碰底胡激励倍率 | 共享 V1 待摸估值、PASS 摸牌补偿；不得与旧副露奖励叠加 | V2已搜索但未晋升；生产未启用 | `'pung_value_incentive': (0.8, 1.25),；DEFAULTS 见第17行` |
| `claim_v2.kong_risk_reward_factor` | `backend/app/core/claim_v2.py:15` | 1.0 | 岭上弃牌和补杠抢杠风险倍率 | 共享 V1 待摸估值、PASS 摸牌补偿；不得与旧副露奖励叠加 | V2已搜索但未晋升；生产未启用 | `'kong_risk_reward_factor': (0.9, 1.1),；DEFAULTS 见第17行` |

#### threat_assessment（13项）

| 名称 | 当前文件:行 | 当前值 | 作用 | 耦合关系 | 状态 | 当前源码表达式 |
|---|---|---:|---|---|---|---|
| `threat_assessment.L27C58` | `backend/app/core/threat_assessment.py:27` | 1 | 牌墙反推巡目（起始余墙/每轮摸牌/起始巡） | 只改变公开威胁提示；复用 tenpai_model 概率，不回写 EV | 提示固定/不进入EV | `round_turn = max(round_turn, (82 - wall_count) // 4 + 1)` |
| `threat_assessment.L27C54` | `backend/app/core/threat_assessment.py:27` | 4 | 牌墙反推巡目（起始余墙/每轮摸牌/起始巡） | 只改变公开威胁提示；复用 tenpai_model 概率，不回写 EV | 提示固定/不进入EV | `round_turn = max(round_turn, (82 - wall_count) // 4 + 1)` |
| `threat_assessment.L27C34` | `backend/app/core/threat_assessment.py:27` | 82 | 牌墙反推巡目（起始余墙/每轮摸牌/起始巡） | 只改变公开威胁提示；复用 tenpai_model 概率，不回写 EV | 提示固定/不进入EV | `round_turn = max(round_turn, (82 - wall_count) // 4 + 1)` |
| `threat_assessment.L33C27` | `backend/app/core/threat_assessment.py:33` | 2 | 连续新鲜中张最少次数 | 只改变公开威胁提示；复用 tenpai_model 概率，不回写 EV | 提示固定/不进入EV | `len(recent) == 2` |
| `threat_assessment.L31C34` | `backend/app/core/threat_assessment.py:31` | 2 | 新鲜中张回看长度 | 只改变公开威胁提示；复用听牌概率，不回写EV | 提示固定/不进入EV | `recent = player.discards[-2:]` |
| `threat_assessment.L34C67` | `backend/app/core/threat_assessment.py:34` | 1 | 新鲜牌公共可见次数 | 只改变公开威胁提示；复用听牌概率，不回写EV | 提示固定/不进入EV | `and all(_is_middle(tile) and visible_discards[tile] == 1 for tile in recent)` |
| `threat_assessment.L36C26` | `backend/app/core/threat_assessment.py:36` | 0.8 | 高危提示概率/副露组数/余墙阈值 | 只改变公开威胁提示；复用听牌概率，不回写EV | 提示固定/不进入EV | `if probability >= 0.8 or meld_count >= 3 or (meld_count >= 2 and wall_count <= 50):` |
| `threat_assessment.L36C47` | `backend/app/core/threat_assessment.py:36` | 3 | 高危提示概率/副露组数/余墙阈值 | 只改变公开威胁提示；复用听牌概率，不回写EV | 提示固定/不进入EV | `if probability >= 0.8 or meld_count >= 3 or (meld_count >= 2 and wall_count <= 50):` |
| `threat_assessment.L36C67` | `backend/app/core/threat_assessment.py:36` | 2 | 高危提示概率/副露组数/余墙阈值 | 只改变公开威胁提示；复用听牌概率，不回写EV | 提示固定/不进入EV | `if probability >= 0.8 or meld_count >= 3 or (meld_count >= 2 and wall_count <= 50):` |
| `threat_assessment.L36C87` | `backend/app/core/threat_assessment.py:36` | 50 | 高危提示概率/副露组数/余墙阈值 | 只改变公开威胁提示；复用听牌概率，不回写EV | 提示固定/不进入EV | `if probability >= 0.8 or meld_count >= 3 or (meld_count >= 2 and wall_count <= 50):` |
| `threat_assessment.L40C27` | `backend/app/core/threat_assessment.py:40` | 1 | 新副露警告最少组数 | 只改变公开威胁提示；复用听牌概率，不回写EV | 提示固定/不进入EV | `elif meld_count >= 1:` |
| `threat_assessment.L42C27` | `backend/app/core/threat_assessment.py:42` | 25 | 晚巡提示余墙/巡目阈值 | 只改变公开威胁提示；复用听牌概率，不回写EV | 提示固定/不进入EV | `elif wall_count <= 25 or round_turn >= 12:` |
| `threat_assessment.L42C47` | `backend/app/core/threat_assessment.py:42` | 12 | 晚巡提示余墙/巡目阈值 | 只改变公开威胁提示；复用听牌概率，不回写EV | 提示固定/不进入EV | `elif wall_count <= 25 or round_turn >= 12:` |

### 1.3 现有评估能力与证据边界

- `tune_ai_weights.py`：默认从V0开始，基准池为V0/conservative/aggressive及history目录里的stable配置；通用 `evaluate_pool` 在每局对手三家中保证至少两个不同指纹，但不是固定版本比例，候选物理座位固定1。single-stage支持 `--parameters`；two-stage固定12核心项、用 `explore` 代理筛选，不能直接搜索任意新权重。single-stage按代分配1%家族错误预算，two-stage按代×精英数分配；完整EV、至少2000局/500墙块、置信下界超过minimum-gain（默认1）及现任非劣才可晋升。它没有把放铳率不升做成通用硬门槛。
- `tune_claim_weights.py:31–34` 当前门槛是非smoke、专项测试通过、至少500墙块、配对均值>0且放铳率<=V1；不是最初V2设计所写的95%下界>0。通过 `claim_experiment.py` 每墙轮换物理座位、每墙四庄，归一化候选统计座位为1。初筛用 `claim-explore`，通用 `run_headless_simulation.py --mode` 目前不接受此模式。
- V2正式宽界批次：配对增益−0.858，下界−1.730742，放铳18.20%→18.60%；tight批次：增益−0.8905，下界−1.591445，放铳19.00%→18.60%，均未晋升。tight五项锁定值仍为55/18/40/1/1；不能把未改善归因于任一单项，也不能将其称为已验证生产V2。
- `validate_ai_weights_focused.py` 专为历史V1候选追加2000局，再合并4000局/1000块；门槛为单侧95%下界>0。最早2000局曾从9候选择优，合并仍有选择偏差；新增2000局独立增益0.994、下界0.305495更有解释力。V3不照搬合并旧筛选样本的做法。
- `tune_parameters.py --log-dir` 是日志诊断和建议工具，不是自动闭环优化器。`arena.py` 已输出净分、和牌/放铳/流局率，尚未提供副露机会分母、弃听、向听推进、自摸分类和Elo。模拟器见合法HU即和，故“拒绝和牌率”在当前仿真中被框架固定为0，须另测生产推荐函数的HU/PASS行为。

## 2. 解冻优先级与搜索空间

原则：先测触发频率、单参数±5%/±10%扰动后的动作翻转率、同墙净分差和行为差，再决定实际搜索子集。以下敏感度排序是根据公式/影响面的假设，未经本次仿真实测。每个小轮只动2–3项，其他全部固定在上次晋升值；保留父代作为零变更对照。每个候选相对现任每项最大±15%，最终晋升相对本大版本起点累计最大±25%；整数取整，始终与下表界限及schema硬界限取交集。严禁通过许多小轮绕过累计幅度上限。

### 2.1 第一批（V3，6项，重新开放4项核心并首次开放2项）

| 参数 | 当前值（约） | 建议搜索区间 | 优先理由与隔离方法 |
|---|---:|---|---|
| `ev_engine.SHANTEN_PENALTY` | 131 | 整数112–150 | 全局推进主尺度，影响大；固定DEEP_SHANTEN_UNIT=25避免相同向听罚分不可辨识 |
| `ev_engine._UKEIRE_QUALITY_WEIGHT` | 0.89052 | 0.76–1.02 | 常见进张信号，动作翻转易观测；与向听权重分轮搜索，最后2维局部复核 |
| `ev_engine._GOOD_SHAPE_DEFENSE_SCALE` | 0.412397 | 0.351–0.474 | 好形局部攻守折扣，可按好形/非好形分层辨识；固定风险参考值 |
| `tenpai_model._SIGMOID_CENTER` | 10.101048 | 8.6–11.6 | 公共巡目信号覆盖广；固定陡度、先验幅度与危险底值，避免全链同时缩放 |
| `ev_engine._GUEST_WIND_SINGLE_PENALTY` | 12 | 10.2–13.8 | 客风孤张事件明确，能用早巡客风专项和推进率区分；已有雀头额外罚分保持固定 |
| `ev_engine._ORPHAN_TERMINAL_UKEIRE_SCALE` | 0.22 | 0.187–0.253 | 只折现孤立幺九虚胖进张；与广义进张权重触发范围不同，先单变量再交互 |

前四项区间均落在 `ai_core_bounds.json`；后两项参考 `weights_schema.json` 的[6,24]、[0.11,0.44]收窄。选它们不是断言独立：推进两项存在耦合，按“推进→局部结构→攻守”分三个小轮，禁用全部6项同时随机搜索。新参数不被旧explore读取，必须以短完整EV作快筛，或先实现并验证真实读取它们的代理。

### 2.2 第二批（V4，风险校准与结构）

| 子组及明确键 | 建议区间 | 条件/原因 |
|---|---|---|
| `danger_model.BASE_HONOR_LIVE/BASE_HONOR_DEAD` | 0.136–0.184 / 0.017–0.023 | 按生熟字牌分层，保持DEAD<=LIVE；不要同时动听牌先验 |
| `danger_model.BASE_MID_456/BASE_NEAR_MID/BASE_TERMINAL` | 0.153–0.207 / 0.102–0.138 / 0.068–0.092 | 456、2378、19的校准曲线可区分；保留MID>=NEAR>=TERMINAL |
| `danger_model.WALL_BOTH_SIDES_FACTOR/WALL_ONE_SIDE_EDGE_FACTOR` | 0.383–0.518 / 0.595–0.805 | 断壁样本足够才动，保持双侧折扣<=单侧 |
| `tenpai_model._SIGMOID_STEEPNESS/_P_SPAN` | 0.357–0.483 / 0.442–0.598 | 中心固定，先校准斜率后幅度，不同时拟合危险底值 |
| `tenpai_model._MELD_ADD.1/.2` | 0.119–0.161 / 0.255–0.345 | 副露一/二组单独分桶；其余ADD/CAP及三组下限固定 |
| `ev_engine._SHAPE_RYANMEN/_SHAPE_KANCHAN/_SHAPE_PENCHAN` | 8.5–11.5 / 4.25–5.75 / 2.55–3.45 | 保留两面>=嵌>=边；先调两面/嵌的相对差，避免全结构统一缩放 |
| `ev_engine._YAKUHAI_SINGLE_POTENTIAL/_YAKUHAI_PAIR_POTENTIAL` | 10.722–14.505 / 12.965–17.541 | 保持单<=对<=刻22；搭配役牌供给分层 |
| `ev_engine._JANTOU_BREAK_PENALTY` | 17.909–24.229 | 先过唯一雀头回归，约束拆头率 |

V4每轮挑一个子组，最多3维；第二批并非17项一起搜索。概率参数用离线记录的真实终局/时点标签校准（Brier、可靠性分桶），标签只供训练评估，决策仍只读公开信息。对稀少染手和三副露高危样本暂不解冻。

### 2.3 第三批（V5，副露机制及低频风险）

| 参数/子组 | 建议区间 | 限制 |
|---|---|---|
| `claim_v2.redundant_chow_penalty` | 46.75–60 | 绝不削弱硬过滤；仅尚未被支配的吃法可提供梯度 |
| `claim_v2.no_advance_chow_penalty` | 15.3–20.7 | 与冗余罚分强耦合，先单项 |
| `claim_v2.claim_to_tenpai_reward` | 35–45 | 用进听率、活张质量而非副露次数作正向信号 |
| `claim_v2.pung_value_incentive` | 0.85–1.15 | 非听牌碰底胡补偿，听牌后不得重复计分 |
| `claim_v2.kong_risk_reward_factor` | 0.9–1.1 | 明/暗/补杠分层，单独验证抢杠风险 |
| `call_decision._PASS_DRAW_TURN_BASE/_PASS_DRAW_UKEIRE_SCALE` | 18.7–25.3 / 0.2975–0.4025 | 与进听奖励分轮；V2仅未听牌PASS加此补偿 |
| `danger_model.DYE_OWN_SUIT_MID_FACTOR/DYE_OTHER_SUIT_FACTOR` | 1.87–2.53 / 0.2125–0.2875 | 染手触发足量才搜索，严禁看暗手判断染手 |
| `ev_engine._ZIMO_THREAT_PRIOR/_DEFENSE_RISK_REFERENCE` | 0.238–0.322 / 0.102–0.138 | 最后才调的全局风险补偿；先验及danger底值锁定后单项消融 |

V5先做“当前V1+guard vs 同权重统一claim机制”的机制消融；机制改变与权重改变分开试验，不将V2失败候选直接上线。若不采用统一机制，则留在旧call分支，另开旧参数实验（TEMPO 51–69、PONG_SCALE 2.125–2.875、PASS_BASE 18.7–25.3），不把这两套奖励并用。其余全景条目默认继续冻结：特别是计分/支付、硬过滤、概率钳位、平均分母、候选数/岭上采样上限、说明与UI阈值、screen八项。后续若改采样算法，应作为实现版本单独验证，不能包装成权重优化。

## 3. 逐步调优流程（每个小轮）

1. **预登记与仪器检查**：冻结现任实现、165项配置、附加权重、规则内核、schema、池清单及CLI参数的哈希。记录字段单位、触发次数和各评分分量；对每个拟解冻键执行±5%/±10%探针，确认评分确实变化且守护不被绕过。新V3运行时须基于当前V1+guard快照，历史V1仍用历史源码。用256个训练墙块重放局面检查灵敏度，不将零触发参数继续送入优化器。
2. **快筛**：每小轮2代×8候选（含父代），每代512局=128块；参照每代同墙512局，共9216局。V3新键先用完整EV短跑，不能用不读取它们的fast/explore充数。对旧12核心可用explore，但至少20%候选需做完整EV交叉核对排序；相关性不足则全部改完整EV。快筛目标为配对净分，行为约束先过滤，Pareto前沿再择优；不将胜率盖过负净分。
3. **锁定**：最多3个筛选优胜者各2048局=512块，另跑相同赛程现任2048局，共8192局完整EV；这是选择集，可以排序但不得作为晋升证据。最终只锁一个候选，写 `locked_candidate`、参数差异、实现哈希、锁定时间和不可变候选ID。
4. **全量验证**：在未使用的新墙/对手赛程上候选与现任各8000局=2000块，合计16000局完整EV。主混合池与各压力单元的样本互不复用。所有候选动作按完整EV执行，使用真实settlement净分，含流局、互结、封顶；不以EV代理分充当最终收益。盲验证只运行一次，不看中间均值决定加样本。
5. **晋升判定**：按第4、5节全部门槛交集，失败则保留候选/证据、不覆盖现任。区间跨零视为证据不足。下一轮若继续调整，使用新锁定ID与新留出集；重试也纳入预登记的多重检验预算。
6. **写新版配置→冻结**：通过才原子写新的 `ai_weights_v3_rNN.json`、manifest、schema版本、bounds版本、完整键表、父版本/源码/赛程哈希、报告和回归日志，重新加载核验有效模块值与指纹。禁止覆盖 `ai_weights_v0.json`、`baseline_v1.json` 及历史快照。把已晋升版本加入**下一轮**池，当前实验池保持不变。生产接入是后续独立步骤，需要版本加载器支持、测试及启用记录；文件存在不代表生产已加载。冻结后修改任一参数或代码即另建版本。

### 3.1 种子、牌墙与checkpoint

四次庄家轮换共享一个物理墙种子，统计独立单位是墙块，不是局，也不是4次庄家轮换。候选物理座位按墙索引模4轮转，配对参照用完全相同座位、墙、庄家、三个对手版本与对手席位。若同一墙又跑多种池/候选座位，合并为一个大簇或用不同墙，不能把重放次数算独立样本。

建议预登记示例：训练从20600000起，锁定选择从20700000起，主盲验证从20800000起，压力矩阵从20900000起；每小轮命名空间间隔100000。实际开跑先检查所有旧实验的 `[seed, seed+hands/4)` 区间以及墙哈希，发现碰撞则整体换区间。不要只比较起始种子，seed+i会扩展范围。墙、开门财神、洗牌算法/规则内核、对手抽样及座位赛程全部存manifest。搜索扰动RNG与洗牌RNG分离，不因候选数量或worker数改变赛程；所有样本4局整块写checkpoint。

继续沿用约15秒进度和整块checkpoint；恢复须验证配置、代码、池、bounds、阶段、样本上限、种子赛程哈希；worker数可以变，其他实验语义不得变。失败/未结束块重跑，不丢弃“难局”，禁止跨版本复用决策缓存。

### 3.2 命令行：现有命令与待开发接口分开

以下是**现有脚本支持的用法示例，本次均未执行仿真**；第一条仅旧V0起点单阶段快筛，不能声称是在当前V1上调V3。`--parameters`不能与默认two-stage或`--focus-core`并用。

```powershell
cd F:\mahjong\backend
.\.venv\Scripts\python.exe scripts/tune_ai_weights.py --pipeline single-stage --mode ev --screen-only --generations 2 --population 8 --hands 512 --validation-hands 2000 --parameters ev_engine._GUEST_WIND_SINGLE_PENALTY ev_engine._ORPHAN_TERMINAL_UKEIRE_SCALE --seed 20600000 --workers 8 --output data/ai_tuning/v3-legacy-capability-example
.\.venv\Scripts\python.exe scripts/tune_claim_weights.py --generations 1 --population 6 --hands 500 --validation-hands 2000 --seed 20610000 --validation-seed 20810000 --workers 8 --output data/ai_tuning/v2-reproduction-example
.\.venv\Scripts\python.exe scripts/run_headless_simulation.py --mode ev --hands 2000 --seed 20900000 --workers 8 --policies tools/policy_pool/baseline_v0.json tools/policy_pool/baseline_v1.json tools/policy_pool/baseline_v0.json tools/policy_pool/baseline_v1.json --output data/headless/fixed-lineup-example.json
.\.venv\Scripts\python.exe scripts/tune_parameters.py --log-dir data/game_logs
```

第三条是固定四策略对阵报告，不自动生成与现任配对比较，不具备固定比例混合池或物理候选轮转。第二条具备V2实验的旧晋升写出逻辑，不能当V3晋升入口。`validate_ai_weights_focused.py --source ... --output ... --seed ... --workers 8` 只能复现其历史目录格式及追加2000局流程，不满足V3独立8000局设计。

建议新增 `scripts/tune_ai_weights_v3.py`（本次不创建），复用现有mutate/私有runtime/整块执行与paired_comparison，增加：

| 新接口 | 用途 |
|---|---|
| `--baseline --runtime-manifest --parameter-set --bounds` | 当前V1+guard起点，版本绑定，明确解冻白名单与窄边界 |
| `--pool-manifest --schedule-manifest` | 固定比例版本池与可审计的物理轮转赛程 |
| `--screen-mode ev --screen-hands --lock-hands --validation-hands` | 三阶段独立预算，不自动把选择集并入留出证据 |
| `--train-seed --lock-seed --validation-seed` | 检查样本区间/墙哈希不重叠 |
| `--max-relative-step --max-total-change --metrics-spec --alpha` | 幅度上限、行为约束和统计错误预算 |
| `--lock-only --validate-locked --promote-if-passed --resume` | 冻结候选后只验证，全部门槛通过才写新版本 |

拟议用法（**接口尚未实现，不能直接运行**）：

```powershell
.\.venv\Scripts\python.exe scripts/tune_ai_weights_v3.py --baseline app/config/ai_weights_optimized.json --runtime-manifest data/ai_tuning/v3/live-v1-guard.json --parameter-set v3-local-shape --bounds data/ai_tuning/v3/bounds.json --pool-manifest data/ai_tuning/v3/pool.json --schedule-manifest data/ai_tuning/v3/schedule.json --screen-mode ev --screen-hands 512 --lock-hands 2048 --validation-hands 8000 --train-seed 20600000 --lock-seed 20700000 --validation-seed 20800000 --max-relative-step 0.15 --max-total-change 0.25 --metrics-spec data/ai_tuning/v3/metrics.json --alpha 0.05 --lock-only
```

还需新增评估采集器与 `evaluate_policy_matrix.py`（固定阵容/版本配对、分层统计、Elo及墙块bootstrap），扩展V3版本的schema和runtime而不是放宽V2的冻结断言。生产加载器现仅支持12项，必须后续明确扩展并同步 `call_decision.SHANTEN_PENALTY` 导入副本；依旧启动时加载、不热变更。

## 4. 防策略坍塌机制

约束采用下列预登记默认值，后续只可在训练集上调整；主留出集打开后不得改门槛。比例均用百分点（pp），报告样本分母、均值差与墙块置信区间。

| 指标/异常 | 分母与采集方式 | 晋升约束 |
|---|---|---|
| 配对净分 | 所有完成局，包括流局；按墙块配对 | 主池单侧95%下界>0 |
| 放铳率 | 放铳/候选总局数，单列抢杠 | 观测差<=0，且差值单侧95%上界<=+0.5pp；低放铳但负净分照样拒绝 |
| 副露率 | 吃/碰/杠次数除各自**合法可选机会**，另报每局次数 | 各主要动作相对现任0.75–1.25；足量机会下不允许归零；超限需另立机制实验 |
| 平均向听推进 | 正常弃牌后到下一次正常弃牌后向听减少值；排除终局不成对窗口，另报各起始向听档 | 差值单侧95%下界>=−0.05向听/窗口；更快但乱吃须同时过净分门槛 |
| 自摸率 | 自摸和牌/候选总局数，同时报自摸/和牌 | 前者差值下界>=−1pp；区分自摸、荣和、抢杠，不能把总和牌率代替 |
| 永不吃碰/机械全吃碰 | 至少200个该类合法机会；按有收益/被支配标签分层 | 禁止有收益机会选择率为0或全机会选择率为1；稀有杠不足200则补专项样本而非判通过 |
| 永远弃听 | 听牌后选择增向听的弃牌/可保持听牌机会；区分高危可解释退让 | 低风险桶弃听率<=现任+2pp；已听牌保持率不能持续归零 |
| 盲目拆头、财神、超时 | 专项局面及评分分量；单列唯一雀头被拆次数 | 规则守恒、合法动作、零和、有限数值、终止性必须100%通过；强制胡牌在仿真外直接测 |

行为门槛是防退化约束，不能作为直接最大化奖励，否则可能刷副露/推进计数。差值按相同机会局面另做固定局面审计，避免策略改变导致机会分母变化掩盖异常。主仿真仍按实际走出的轨迹统计，两种口径并报。多项不退化门槛全部满足才通过；任何关键分层样本不足记“证据不足”。

参数结构约束：役牌单<=对<=刻、边<=嵌<=两面、熟字<=生字、MIN<=MAX、P_FLOOR+P_SPAN<=0.95、概率最终钳位、中心度1/9与2/8等对称关系保持；不让优化器同时缩放听牌先验、danger、损失倍率三个乘数。副露硬过滤在权重奖励之前，正收益正常吃/碰/杠仍必须可选。禁用新版本自我对战作为主训练池，冻结对手赛程贯穿一轮。

专项测试门槛建议复用以下实际文件；每次锁定前和晋升前都需全过，无跳过/xfail新增。后续实现新增参数读取、版本隔离、行为指标分母、checkpoint一致性、座位轮转和晋升门槛测试。

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_ai_weights_loading.py tests/test_offline_ai_tools.py tests/test_focused_validation.py tests/test_v1_chow_guard.py tests/test_claim_invariance.py tests/test_call_decision.py tests/test_ev_engine.py tests/test_danger_model.py tests/test_tenpai_model.py tests/test_action_generator.py tests/test_self_gang.py tests/test_payment_cap.py tests/test_settlement.py tests/test_physical_white_dragon.py tests/test_no_round_wind_fan.py -q
```

特别保留GM-86F219原样吃回过滤、有收益同宽听口不能误杀、正常1→0向听吃牌、役牌碰、岭上即和、白板替身和唯一雀头用例。新版配置加载失败不得静默降级掩盖问题。

双轨：配对净分是主目标，Elo用第5节固定阵容赛事得到的名次两两胜/平/负作辅助，不能由胡牌率换算。Elo不替代净分；净分通过但Elo相对现任的墙块bootstrap 95%下界<-10 Elo则拒绝并查弱点。

回滚：每次晋升保存前任配置+实现+schema，按版本指针整体回退，不能只退JSON。规则/硬护栏失败立即回滚；后续独立4000局/1000块监控若配对净分95%上界<0，或放铳增长95%下界>+0.5pp、出现永不吃碰/永久弃听则回滚。线上仅用公开状态遥测监控分布漂移，不能把非配对真人战绩直接混入离线显著性证据。回滚版本标记retired-bug并保留审计，禁止下一轮又当已验证强基准自动加入。

## 5. 基准池、评估矩阵与统计显著性

### 5.1 固定比例与更新

V3对手席位总配额建议：历史V0 20%、历史V1 40%、当前V1+guard 30%、V2-tight失败候选10%。V2在这里仅是低权重压力对手，明确标记“未晋升”；从实验locked_candidate及对应实现加载、校验5项为55/18/40/1/1，**不能假设存在生产 `ai_weights_v2.json`**。若不可恢复其完整指纹，则取消该席位并将10%给当前V1+guard，记录不同的池版本；不伪造历史V2。

使用确定性分层配额，不采用独立随机抽池后强行替换的旧算法来声称固定比例。每个四局墙块的三家对手至少两种历史谱系，整轮确保V0/V1均覆盖；版本不同而权重/实现完全相同的副本去重。2000主池墙块共6000对手块席位，20/40/30/10%配额正好1200/2400/1800/600。打乱顺序的RNG独立固定，4个物理候选席位与庄家均衡；不把同一个配额再按四局重复算独立样本。

晋升后下一轮：V0 20%、历史V1 30%、当前冠军30%、前任10%、V2压力10%；同版本重叠则合并配额，manifest写明实际比例。正在搜索的未晋升候选不能入主池。最多保留6个活跃实现，其余进冷归档；V0/V1永久锚点不退役。普通旧冠军在连续两次独立矩阵中被新冠军稳定支配、且没有独有克制型后才退役；有独特攻击/保守风格保留至少5%并从前任槽分配。V2压力版本如果机制被正式继任且专项覆盖等价，可移至冷压力集；规则错误/隐藏信息泄漏版本立即退出训练池，历史证据不删除。池变动后重跑锚点交叉赛，不跨池直接比较均值或Elo。

### 5.2 评估矩阵与规模

| 单元 | 对手/用途 | 每策略样本 | 是否参与主晋升统计 |
|---|---|---:|---|
| M 主混合池 | 固定版本配额；候选与现任同赛程 | 8000局/2000墙块 | 主净分/行为门槛 |
| A 旧版本压力 | 三家V0 | 2000局/500墙块 | 分层非劣，独立墙 |
| B 历史强基准压力 | 三家历史V1 | 2000局/500墙块 | 分层非劣，独立墙 |
| C claim压力 | 一家V0、一家V1、一家V2-tight | 2000局/500墙块 | 分层非劣，独立墙 |
| D 现任压力 | 三家当前冠军/起始V1+guard | 2000局/500墙块 | 分层非劣，独立墙 |
| E 历史锚点交叉赛 | 固定四版本阵容、名次两两比较 | 每阵容2000局/500墙块 | Elo尺度校准；池变动才重跑 |

A/B/D允许同质对手，是**诊断压力单元**，不混入M的多样对手训练分布。M+A–D每候选16000局、参照也16000局，共32000实际模拟局。E可复用相同内核/赛程版本已冻结的锚点证据；新的候选/现任Elo优先使用M及压力单元轨迹，禁止重复计入一个墙块。主要低频事件桶至少200次有效机会，否则必须预先规划专项采样并另报；不能把人为富集专项并入自然分布胜率。

### 5.3 统计定义和门槛

设第b个独立墙块的4局候选净分减现任净分的均值为d_b；增益为所有d_b均值，SE=s(d)/sqrt(B)。单次锁定检验的单侧95%下界为 mean−1.644854×SE，要求>0（建议预登记业务最小收益0.1分/局时则要求>0.1）。至少500块只是**历史最低底线**；V3主检验计划2000独立块，压力单元最少500块。数据缺块不能拿完整局数替代；不得把候选与参照两臂或四庄当成独立样本。

同时用固定随机种子的墙块bootstrap（至少10000次）检验重尾稳定性；若正态近似下界>0而bootstrap下界<=0，则证据不足，不晋升。放铳、自摸、副露、弃听等也按墙块重采样，不能用逐动作独立二项检验夸大精度。A–D压力单元使用单侧95%非劣界，建议下界>=−1分/局，并报告各座位/庄闲分层；该容忍值必须事先固定。

每个已锁定候选一次验证，未锁定的选择集完全不进入确认区间。若一个版本预算预定R次晋升尝试，采用Bonferroni α=0.05/R或预登记序贯α支出；仍展示未校正单侧95%区间，但决策按校正下界。不能在失败后无限重试“单次95%”。不得看到中途有利就停；若要增样，预先设计分阶段α支出及最大样本，不能复刻V1选优样本混入确认样本。

Elo：使用含互结后的四家净分排名，两两胜=1、平=0.5、负=0；固定V0为1500锚点，在固定阵容数据上拟合Bradley–Terry/Elo尺度，四人同局的六对结果仍按墙块聚类。另报对每个版本的净分和排名胜率、循环克制矩阵。排名Elo可能掩盖得失分幅度，因此仅作辅助非劣门槛；版本加入/退役导致赛程变化时重新锚定，不能直接比较两个不同池的Elo绝对值。

## 6. V3/V4/V5迭代路线图

| 版本 | 解冻范围与顺序 | 每小轮预算（实际模拟局，含参照） | 计划规模/退出条件 |
|---|---|---|---|
| V3 | 第一批6项，推进→客风/孤幺九→好形/巡目风险；3个小轮，每轮2项 | 快筛9216 + 选择8192 + 主验证16000 + 压力16000 = 49408；另256块现任探针采样1024局 | 约15.13万局/3轮；新池另加E锚点赛；未过不晋升、不为凑V3解冻更多项 |
| V4 | 第二批17项分6个小轮，先危险分桶，再听牌曲线/副露先验，再结构/役牌/雀头 | 基础同V3；危险低频样本不足时预登记主验证增至12000局/策略，单轮再加8000局 | 约30.26万–35.06万局；每轮单侧检验预算按6次分配；触发不足参数继续冻结 |
| V5 | 第三批11项，先机制A/B消融，再5项claim分3轮、PASS/染手/风险分组；预算6个搜索小轮 | 每轮主验证16000局/策略，其余同V3，约65408局，外加1024探针局 | 搜索约39.86万局；机制消融另32000局，总约43.06万局；V2机制失败则停在V4或另开旧call分支 |

预算中的探针使用同一批1024局采集的局面多次评分，不为每个扰动重新生成整局；E锚点赛按实际阵容数×2000局另列。以上为局数预算，不承诺耗时；先测各阶段100块的吞吐与峰值内存再排机器时段。若追加样本，须在开留出集之前改预算/α计划。V3需要先完成版本隔离、真实参数读取、固定比例池、行为采集与门槛实现，才能开第一轮；这项文档工作不实施上述代码。

文档验收：核对六节、全景表键唯一/165旧键全覆盖、文件行号与代码表达式对应、配置值及模块计数；不执行耗时仿真。此次没有要求必须运行的测试命令，上述pytest命令是未来调优的回归门槛示例，不表示本次已运行通过。
