# 当前本地 V1 EV 参数完整清单

以本地 V1 启动加载结果为准；未核查已运行进程或 Render 的当前加载状态。

配置共165项：完整EV模块157项，离线快筛8项。V1仅允许12个核心参数从配置覆盖；其余参数在生产代码中保持V0值，不能仅修改JSON就生效。下表的边界来自离线调参schema，不代表生产允许开放所有参数。

带L/C后缀的键是冻结V0源码的行/列标识，不是当前生产源码行号；有些是阈值、分母或说明文案条件，并非独立策略权重。

★表示V1调参开放项（不代表每项最终数值均变化）。全部数值保留配置精度。

## danger_model（13项）

| 参数 | V1当前值 | V0原值 | 离线下界 | 离线上界 | 源码定义/使用表达式 |
|---|---:|---:|---:|---:|---|
| `danger_model.BASE_HONOR_LIVE` | 0.16 | 0.16 | 0.08 | 0.32 | `BASE_HONOR_LIVE = 0.16  # 字牌生张` |
| `danger_model.BASE_HONOR_DEAD` | 0.02 | 0.02 | 0.01 | 0.04 | `BASE_HONOR_DEAD = 0.02  # 字牌已见 ≥2（熟张上限）` |
| `danger_model.BASE_MID_456` | 0.18 | 0.18 | 0.09 | 0.36 | `BASE_MID_456 = 0.18  # 序数 4/5/6` |
| `danger_model.BASE_TERMINAL` | 0.08 | 0.08 | 0.04 | 0.16 | `BASE_TERMINAL = 0.08  # 序数 1/9` |
| `danger_model.BASE_NEAR_MID` | 0.12 | 0.12 | 0.06 | 0.24 | `BASE_NEAR_MID = 0.12  # 序数 2/3/7/8（介于幺九与深中张之间）` |
| `danger_model.WALL_BOTH_SIDES_FACTOR` | 0.45 | 0.45 | 0.225 | 0.9 | `WALL_BOTH_SIDES_FACTOR = 0.45` |
| `danger_model.WALL_ONE_SIDE_EDGE_FACTOR` | 0.7 | 0.7 | 0.35 | 1.0 | `WALL_ONE_SIDE_EDGE_FACTOR = 0.70  # 边张仅一侧可连且已断` |
| `danger_model.DYE_OWN_SUIT_MID_FACTOR` | 2.2 | 2.2 | 1.1 | 4.4 | `DYE_OWN_SUIT_MID_FACTOR = 2.2  # 染手花色 3~7` |
| `danger_model.DYE_OTHER_SUIT_FACTOR` | 0.25 | 0.25 | 0.125 | 0.5 | `DYE_OTHER_SUIT_FACTOR = 0.25  # 其余两门序数` |
| `danger_model.estimate_tile_danger.L80C18` | 0.75 | 0.75 | 0.375 | 1.0 | `danger *= 0.75` |
| `danger_model._base_danger.L115C16` | 0.5 | 0.5 | 0.25 | 1.0 | `base *= 0.5` |
| `danger_model._base_danger.L117C16` | 0.75 | 0.75 | 0.375 | 1.0 | `base *= 0.75` |
| `danger_model._base_danger.L99C57` | 2.0 | 2.0 | 1.0 | 4.0 | `return (BASE_HONOR_LIVE + BASE_HONOR_DEAD) / 2.0` |

## tenpai_model（21项）

| 参数 | V1当前值 | V0原值 | 离线下界 | 离线上界 | 源码定义/使用表达式 |
|---|---:|---:|---:|---:|---|
| `tenpai_model._P_FLOOR` | 0.028 | 0.028 | 0.014 | 0.056 | `_P_FLOOR = 0.028` |
| `tenpai_model._P_SPAN` | 0.52 | 0.52 | 0.26 | 1.0 | `_P_SPAN = 0.52` |
| ★ `tenpai_model._SIGMOID_CENTER` | 10.101047681722928 | 11.0 | 5.5 | 22.0 | `_SIGMOID_CENTER = 11.0` |
| ★ `tenpai_model._SIGMOID_STEEPNESS` | 0.42 | 0.42 | 0.21 | 0.84 | `_SIGMOID_STEEPNESS = 0.42` |
| `tenpai_model._MELD3_FLOOR` | 0.9 | 0.9 | 0.45 | 1.0 | `_MELD3_FLOOR = 0.90  # 三组副露仅余一搭与雀头，至少列为高听牌风险` |
| `tenpai_model._DEALER_BOOST` | 1.12 | 1.12 | 0.56 | 2.24 | `_DEALER_BOOST = 1.12` |
| `tenpai_model._CENTRAL_MULT` | 1.28 | 1.28 | 0.64 | 2.56 | `_CENTRAL_MULT = 1.28  # 每次主动中张` |
| `tenpai_model._CENTRAL_ADD` | 0.055 | 0.055 | 0.0275 | 0.11 | `_CENTRAL_ADD = 0.055` |
| `tenpai_model._PROGRESSION_MULT` | 1.18 | 1.18 | 0.59 | 2.36 | `_PROGRESSION_MULT = 1.18` |
| `tenpai_model._PROGRESSION_ADD` | 0.04 | 0.04 | 0.02 | 0.08 | `_PROGRESSION_ADD = 0.04` |
| `tenpai_model._SAFE_STREAK_MULT` | 1.15 | 1.15 | 0.575 | 2.3 | `_SAFE_STREAK_MULT = 1.15` |
| `tenpai_model._SAFE_STREAK_ADD` | 0.035 | 0.035 | 0.0175 | 0.07 | `_SAFE_STREAK_ADD = 0.035` |
| `tenpai_model._MELD_ADD.1` | 0.14 | 0.14 | 0.07 | 0.28 | `_MELD_ADD = {1: 0.14, 2: 0.30, 3: 0.48, 4: 0.55}` |
| `tenpai_model._MELD_ADD.2` | 0.3 | 0.3 | 0.15 | 0.6 | `_MELD_ADD = {1: 0.14, 2: 0.30, 3: 0.48, 4: 0.55}` |
| `tenpai_model._MELD_ADD.3` | 0.48 | 0.48 | 0.24 | 0.96 | `_MELD_ADD = {1: 0.14, 2: 0.30, 3: 0.48, 4: 0.55}` |
| `tenpai_model._MELD_ADD.4` | 0.55 | 0.55 | 0.275 | 1.0 | `_MELD_ADD = {1: 0.14, 2: 0.30, 3: 0.48, 4: 0.55}` |
| `tenpai_model._MELD_CAP.1` | 0.82 | 0.82 | 0.41 | 1.0 | `_MELD_CAP = {1: 0.82, 2: 0.90, 3: 0.93, 4: 0.95}` |
| `tenpai_model._MELD_CAP.2` | 0.9 | 0.9 | 0.45 | 1.0 | `_MELD_CAP = {1: 0.82, 2: 0.90, 3: 0.93, 4: 0.95}` |
| `tenpai_model._MELD_CAP.3` | 0.93 | 0.93 | 0.465 | 1.0 | `_MELD_CAP = {1: 0.82, 2: 0.90, 3: 0.93, 4: 0.95}` |
| `tenpai_model._MELD_CAP.4` | 0.95 | 0.95 | 0.475 | 1.0 | `_MELD_CAP = {1: 0.82, 2: 0.90, 3: 0.93, 4: 0.95}` |
| `tenpai_model._apply_progression_boost.L209C52` | 0.35 | 0.35 | 0.175 | 0.7 | `if early_ok and late_mid and early_mid_ratio <= 0.35:` |

## ev_engine（85项）

| 参数 | V1当前值 | V0原值 | 离线下界 | 离线上界 | 源码定义/使用表达式 |
|---|---:|---:|---:|---:|---|
| ★ `ev_engine.SHANTEN_PENALTY` | 131 | 120 | 60.0 | 240 | `SHANTEN_PENALTY = 120` |
| `ev_engine._ZIMO_THREAT_PRIOR` | 0.28 | 0.28 | 0.14 | 0.56 | `_ZIMO_THREAT_PRIOR = 0.28` |
| `ev_engine._IISHANTEN_TURN_DISCOUNT` | 2 | 2 | 1.0 | 4 | `_IISHANTEN_TURN_DISCOUNT = 2` |
| ★ `ev_engine._UKEIRE_QUALITY_WEIGHT` | 0.8905197287388378 | 1.25 | 0.625 | 2.5 | `_UKEIRE_QUALITY_WEIGHT = 1.25  # 有效进张枚数质量权重` |
| ★ `ev_engine._DEEP_SHANTEN_UNIT` | 25 | 25 | 12.5 | 50 | `_DEEP_SHANTEN_UNIT = 25  # 多向听内向听档位代价（与 SHANTEN_PENALTY 分工）` |
| ★ `ev_engine._YAKUHAI_SINGLE_POTENTIAL` | 12.61312012835429 | 10.0 | 5.0 | 20.0 | `_YAKUHAI_SINGLE_POTENTIAL = 10.0  # 役牌孤张保留分（中发白 / 自风）` |
| ★ `ev_engine._YAKUHAI_PAIR_POTENTIAL` | 15.253399288810538 | 16.0 | 8.0 | 32.0 | `_YAKUHAI_PAIR_POTENTIAL = 16.0  # 役牌对子（接近刻）` |
| `ev_engine._YAKUHAI_PUNG_POTENTIAL` | 22.0 | 22.0 | 11.0 | 44.0 | `_YAKUHAI_PUNG_POTENTIAL = 22.0  # 已成役牌刻` |
| `ev_engine._SHAPE_PAIR` | 8.0 | 8.0 | 4.0 | 16.0 | `_SHAPE_PAIR = 8.0` |
| `ev_engine._SHAPE_PUNG` | 20.0 | 20.0 | 10.0 | 40.0 | `_SHAPE_PUNG = 20.0` |
| `ev_engine._SHAPE_RYANMEN` | 10.0 | 10.0 | 5.0 | 20.0 | `_SHAPE_RYANMEN = 10.0` |
| `ev_engine._SHAPE_KANCHAN` | 5.0 | 5.0 | 2.5 | 10.0 | `_SHAPE_KANCHAN = 5.0` |
| `ev_engine._SHAPE_PENCHAN` | 3.0 | 3.0 | 1.5 | 6.0 | `_SHAPE_PENCHAN = 3.0` |
| `ev_engine._COMPOSITE_KANCHAN_UPGRADE_BONUS` | 7.0 | 7.0 | 3.5 | 14.0 | `_COMPOSITE_KANCHAN_UPGRADE_BONUS = 7.0  # 留 2-4 并摸 5 可形成 4-5 两面` |
| `ev_engine._ANTI_PONG_TERMINAL_BONUS` | 3.0 | 3.0 | 1.5 | 6.0 | `_ANTI_PONG_TERMINAL_BONUS = 3.0  # 场见至少两张幺九，外部最多余一张，无法成碰` |
| `ev_engine._SHAPE_ISOLATED_MID` | 1.5 | 1.5 | 0.75 | 3.0 | `_SHAPE_ISOLATED_MID = 1.5` |
| `ev_engine._SHAPE_ISOLATED_TERM` | 0.5 | 0.5 | 0.25 | 1.0 | `_SHAPE_ISOLATED_TERM = 0.5` |
| ★ `ev_engine._SHAPE_JOKER` | 12.06978306750579 | 12.0 | 6.0 | 24.0 | `_SHAPE_JOKER = 12.0  # 手内「得」百搭` |
| `ev_engine._GUEST_WIND_SINGLE_PENALTY` | 12.0 | 12.0 | 6.0 | 24.0 | `_GUEST_WIND_SINGLE_PENALTY = 12.0  # 无役客风孤张占位价值低，优先切出` |
| `ev_engine._GUEST_WIND_PAIR_PENALTY` | 1.5 | 1.5 | 0.75 | 3.0 | `_GUEST_WIND_PAIR_PENALTY = 1.5  # 客风对子略扣（不如役牌对）` |
| `ev_engine._GUEST_SUBSTITUTE_HOLD_SCALE` | 0.2 | 0.2 | 0.1 | 0.4 | `_GUEST_SUBSTITUTE_HOLD_SCALE = 0.2  # 白板替身客风：有雀头潜力，占位惩罚压到 20%` |
| `ev_engine._SUBSTITUTE_HONOR_KEEP_BONUS` | 8.0 | 8.0 | 4.0 | 16.0 | `_SUBSTITUTE_HONOR_KEEP_BONUS = 8.0  # 保留健康白板替身字牌的雀头潜力加分` |
| `ev_engine._ORPHAN_TERMINAL_UKEIRE_SCALE` | 0.22 | 0.22 | 0.11 | 0.44 | `_ORPHAN_TERMINAL_UKEIRE_SCALE = 0.22  # 纯 1/9 两步靠搭进张泡沫折现` |
| `ev_engine._GUEST_SINGLE_PAIR_UKEIRE_SCALE` | 0.35 | 0.35 | 0.175 | 0.7 | `_GUEST_SINGLE_PAIR_UKEIRE_SCALE = 0.35  # 无役客风孤张配对：只有刻/雀头路线，无顺子扩展` |
| `ev_engine._ORPHAN_TERMINAL_KEEP_PENALTY` | 9.0 | 9.0 | 4.5 | 18.0 | `_ORPHAN_TERMINAL_KEEP_PENALTY = 9.0  # 切后仍持无邻张 1/9 的加重占位惩罚` |
| ★ `ev_engine._JANTOU_BREAK_PENALTY` | 21.06869661708672 | 20.0 | 10.0 | 40.0 | `_JANTOU_BREAK_PENALTY = 20.0  # 拆唯一法定雀头` |
| `ev_engine._ISOLATED_CUT_BONUS` | 6.0 | 6.0 | 3.0 | 12.0 | `_ISOLATED_CUT_BONUS = 6.0  # 切出纯孤张（与核心搭子无关）` |
| `ev_engine._TERMINAL_ISO_CUT_BONUS` | 7.5 | 7.5 | 3.75 | 15.0 | `_TERMINAL_ISO_CUT_BONUS = 7.5  # 切幺九孤张（优先于中张，次于死字牌）` |
| `ev_engine._ORPHAN_TERMINAL_CUT_BONUS` | 16.0 | 16.0 | 8.0 | 32.0 | `_ORPHAN_TERMINAL_CUT_BONUS = 16.0  # 无任何同花色邻/嵌的 1/9：最优先切除` |
| `ev_engine._DEAD_HONOR_CUT_BONUS` | 14.0 | 14.0 | 7.0 | 28.0 | `_DEAD_HONOR_CUT_BONUS = 14.0  # 切绝张/残缺字牌（Rem≤1）` |
| `ev_engine._ISOLATED_KEEP_PENALTY` | 4.0 | 4.0 | 2.0 | 8.0 | `_ISOLATED_KEEP_PENALTY = 4.0  # 切后仍持有序数/字牌孤张` |
| `ev_engine._DEAD_HONOR_KEEP_PENALTY` | 8.0 | 8.0 | 4.0 | 16.0 | `_DEAD_HONOR_KEEP_PENALTY = 8.0  # 切后仍持绝张字牌（加重）` |
| `ev_engine._GOOD_SHAPE_PUSH_BONUS` | 10.0 | 10.0 | 5.0 | 20.0 | `_GOOD_SHAPE_PUSH_BONUS = 10.0  # 好形（刻+两面×2+雀头）推进奖励` |
| ★ `ev_engine._GOOD_SHAPE_DEFENSE_SCALE` | 0.41239674604167603 | 0.45 | 0.225 | 0.9 | `_GOOD_SHAPE_DEFENSE_SCALE = 0.45  # 好形时压缩防守过度反应` |
| `ev_engine._SEEN_GUEST_WIND_CUT_BONUS` | 5.5 | 5.5 | 2.75 | 11.0 | `_SEEN_GUEST_WIND_CUT_BONUS = 5.5  # Rem≤2 场见客风：优先切除` |
| `ev_engine._SUBSTITUTE_YAKUHAI_CUT_PENALTY` | 9.0 | 9.0 | 4.5 | 18.0 | `_SUBSTITUTE_YAKUHAI_CUT_PENALTY = 9.0  # 切健康白板替身役牌（得≠白）惩罚` |
| `ev_engine._SUBSTITUTE_HONOR_CUT_PENALTY` | 12.0 | 12.0 | 6.0 | 24.0 | `_SUBSTITUTE_HONOR_CUT_PENALTY = 12.0  # 切健康白板替身字牌（含客风）惩罚` |
| `ev_engine._HEALTHY_YAKUHAI_CUT_FACTOR` | 0.25 | 0.25 | 0.125 | 0.5 | `_HEALTHY_YAKUHAI_CUT_FACTOR = 0.25  # 供给充足的役牌孤张：切除奖励压到 25%` |
| `ev_engine._NEIGHBOR_OF_GOD_KEEP_BONUS` | 15.0 | 15.0 | 7.5 | 30.0 | `_NEIGHBOR_OF_GOD_KEEP_BONUS = 15.0  # 财神同门 ±1/±2 的孤张顺子连接保留价值` |
| `ev_engine._CENTRALITY_CUT_REF` | 12.0 | 12.0 | 6.0 | 24.0 | `_CENTRALITY_CUT_REF = 12.0  # 与 5 序数保留分对齐` |
| `ev_engine._CENTRALITY_CUT_SCALE_TENPAI` | 0.4 | 0.4 | 0.2 | 0.8 | `_CENTRALITY_CUT_SCALE_TENPAI = 0.40  # 听牌：微差纠偏（切 8 ≈ +4.2）` |
| `ev_engine._CENTRALITY_CUT_SCALE_DEEP` | 0.55 | 0.55 | 0.275 | 1.0 | `_CENTRALITY_CUT_SCALE_DEEP = 0.55  # 一向听+：加强偏张优先` |
| ★ `ev_engine._JOKER_MID_CUT_PENALTY` | 4.407889513401241 | 4.5 | 2.25 | 9.0 | `_JOKER_MID_CUT_PENALTY = 4.5  # 持百搭时切 4/5/6 且另有偏张/字牌孤张` |
| `ev_engine._EV_NEAR_TIE_EPS` | 3.0 | 3.0 | 1.5 | 6.0 | `_EV_NEAR_TIE_EPS = 3.0  # &#124;ΔNetEV&#124;≤3 时按进张数 / 保留中张裁决` |
| `ev_engine._GUEST_WITH_HEAD_CUT_BONUS` | 24.0 | 24.0 | 12.0 | 48.0 | `_GUEST_WITH_HEAD_CUT_BONUS = 24.0  # 已有雀头：无役客风先于幺九清理` |
| `ev_engine._GUEST_WITH_HEAD_HOLD_PENALTY` | 18.0 | 18.0 | 9.0 | 36.0 | `_GUEST_WITH_HEAD_HOLD_PENALTY = 18.0` |
| `ev_engine._TERMINAL_EXTENSION_KEEP_BONUS` | 6.0 | 6.0 | 3.0 | 12.0 | `_TERMINAL_EXTENSION_KEEP_BONUS = 6.0` |
| `ev_engine._CENTRAL_SYNERGY_KEEP_BONUS` | 12.0 | 12.0 | 6.0 | 24.0 | `_CENTRAL_SYNERGY_KEEP_BONUS = 12.0` |
| ★ `ev_engine._DEFENSE_RISK_REFERENCE` | 0.1199965341591117 | 0.12 | 0.06 | 0.24 | `_DEFENSE_RISK_REFERENCE = 0.12  # 高危切牌的风险厌恶尺度，非概率修正` |
| `ev_engine._CENTRALITY_KEEP_BY_DIGIT.1` | 0.0 | 0.0 | 0.0 | 20.0 | `1: 0.0,` |
| `ev_engine._CENTRALITY_KEEP_BY_DIGIT.2` | 1.5 | 1.5 | 0.75 | 3.0 | `2: 1.5,` |
| `ev_engine._CENTRALITY_KEEP_BY_DIGIT.3` | 5.0 | 5.0 | 2.5 | 10.0 | `3: 5.0,` |
| `ev_engine._CENTRALITY_KEEP_BY_DIGIT.4` | 10.0 | 10.0 | 5.0 | 20.0 | `4: 10.0,` |
| `ev_engine._CENTRALITY_KEEP_BY_DIGIT.5` | 12.0 | 12.0 | 6.0 | 24.0 | `5: 12.0,` |
| `ev_engine._CENTRALITY_KEEP_BY_DIGIT.6` | 10.0 | 10.0 | 5.0 | 20.0 | `6: 10.0,` |
| `ev_engine._CENTRALITY_KEEP_BY_DIGIT.7` | 5.0 | 5.0 | 2.5 | 10.0 | `7: 5.0,` |
| `ev_engine._CENTRALITY_KEEP_BY_DIGIT.8` | 1.5 | 1.5 | 0.75 | 3.0 | `8: 1.5,` |
| `ev_engine._CENTRALITY_KEEP_BY_DIGIT.9` | 0.0 | 0.0 | 0.0 | 20.0 | `9: 0.0,` |
| `ev_engine._honor_rem_factor.L1345C15` | 0.4 | 0.4 | 0.2 | 0.8 | `return 0.4` |
| `ev_engine._evaluate_self_gang_candidates.L613C17` | 3.0 | 3.0 | 1.5 | 6.0 | `settle = 3.0 if is_dealer else 2.0` |
| `ev_engine._evaluate_self_gang_candidates.L613C39` | 2.0 | 2.0 | 1.0 | 4.0 | `settle = 3.0 if is_dealer else 2.0` |
| `ev_engine._evaluate_self_gang_candidates.L614C46` | 0.35 | 0.35 | 0.175 | 0.7 | `bonus_ev = float(hu_bonus) * settle * 0.35` |
| `ev_engine._apply_close_ukeire_safety_dominance.L2144C18` | 0.1 | 0.1 | 0.05 | 0.2 | `if risk < 0.10:` |
| `ev_engine.calculate_best_discards.L314C59` | 2.0 | 2.0 | 1.0 | 4.0 | `attack_ev += float(structure["delta"]) * (settle / 2.0)` |
| `ev_engine._guest_wind_hold_penalty.L1403C20` | 1.5 | 1.5 | 0.75 | 3.0 | `scale = 1.5 if rem_n <= 1 else (1.2 if rem_n == 2 else 1.0)` |
| `ev_engine._guest_wind_hold_penalty.L1416C41` | 15.0 | 15.0 | 7.5 | 30.0 | `penalty += min(base * scale, 15.0)` |
| `ev_engine._apply_close_ukeire_safety_dominance.L2161C71` | 0.1 | 0.1 | 0.05 | 0.2 | `adjustment = max(0.0, risky["ev_score"] - leader["ev_score"] + 0.1)` |
| `ev_engine._discard_candidate_note.L2385C67` | 0.4 | 0.4 | 0.2 | 0.8 | `has_yakuhai = yakuhai_score >= _YAKUHAI_SINGLE_POTENTIAL * 0.4` |
| `ev_engine.calculate_best_discards.L332C48` | 0.5 | 0.5 | 0.25 | 1.0 | `net_unit = max(threat["loss_ron"] * 0.5, threat["loss_ron"] - rebate)` |
| `ev_engine.calculate_best_discards.L333C72` | 2.0 | 2.0 | 1.0 | 4.0 | `risk_weight = 1.0 + min(p_dealin / _DEFENSE_RISK_REFERENCE, 2.0)` |
| `ev_engine.calculate_best_discards.L482C44` | 12.0 | 12.0 | 6.0 | 24.0 | `float(best_gang["ev_score"]) + (12.0 if best_gang["action_type"] == "bu_gang" else 0.0),` |
| `ev_engine._guest_wind_hold_penalty.L1403C44` | 1.2 | 1.2 | 0.6 | 2.4 | `scale = 1.5 if rem_n <= 1 else (1.2 if rem_n == 2 else 1.0)` |
| `ev_engine._central_synergy_keep_score.L1688C60` | 8.0 | 8.0 | 4.0 | 16.0 | `total += _CENTRAL_SYNERGY_KEEP_BONUS * min(supply / 8.0, 1.0)` |
| `ev_engine._discard_candidate_note.L2384C69` | 0.5 | 0.5 | 0.25 | 1.0 | `has_complex = shape_score >= (_SHAPE_PAIR + _SHAPE_RYANMEN * 0.5)` |
| `ev_engine._discard_candidate_note.L2270C58` | 8.0 | 8.0 | 4.0 | 16.0 | `_centrality_keep_score(t, dealer_tile) >= 8.0` |
| `ev_engine._apply_isolated_tile_shape_dominance.L2122C76` | 1.35 | 1.35 | 0.675 | 2.7 | `and c["effective_count"] >= core["effective_count"] * 1.35` |
| `ev_engine._apply_isolated_tile_shape_dominance.L2124C37` | 0.03 | 0.03 | 0.015 | 0.06 | `<= core_risk - 0.03]` |
| `ev_engine._apply_close_ukeire_safety_dominance.L2154C80` | 0.78 | 0.78 | 0.39 | 1.0 | `and candidate["effective_count"] >= risky["effective_count"] * 0.78` |
| `ev_engine._discard_candidate_note.L2282C62` | 8.0 | 8.0 | 4.0 | 16.0 | `and _centrality_keep_score(t, dealer_tile) >= 8.0` |
| `ev_engine.calculate_best_discards.L477C40` | 12.0 | 12.0 | 6.0 | 24.0 | `float(g["ev_score"]) + (12.0 if g["action_type"] == "bu_gang" else 0.0),` |
| `ev_engine._structure_attack_adjustment.L1807C62` | 8.0 | 8.0 | 4.0 | 16.0 | `_centrality_keep_score(t, dealer_tile) >= 8.0` |
| `ev_engine._apply_close_ukeire_safety_dominance.L2156C31` | 0.04 | 0.04 | 0.02 | 0.08 | `<= min(risk - 0.04, risk * 0.70)` |
| `ev_engine._apply_close_ukeire_safety_dominance.L2156C44` | 0.7 | 0.7 | 0.35 | 1.0 | `<= min(risk - 0.04, risk * 0.70)` |
| `ev_engine._structure_attack_adjustment.L1896C25` | 0.7 | 0.7 | 0.35 | 1.0 | `factor = 0.7 if rem_n == 2 else 0.35` |
| `ev_engine._structure_attack_adjustment.L1896C48` | 0.35 | 0.35 | 0.175 | 0.7 | `factor = 0.7 if rem_n == 2 else 0.35` |

## call_decision（38项）

| 参数 | V1当前值 | V0原值 | 离线下界 | 离线上界 | 源码定义/使用表达式 |
|---|---:|---:|---:|---:|---|
| `call_decision._CALL_TENPAI_TEMPO_BONUS` | 60.0 | 60.0 | 30.0 | 120.0 | `_CALL_TENPAI_TEMPO_BONUS = 60.0` |
| `call_decision._DEALER_TENPAI_CONTINUATION_BONUS` | 20.0 | 20.0 | 10.0 | 40.0 | `_DEALER_TENPAI_CONTINUATION_BONUS = 20.0` |
| `call_decision._WIN_PASS_OPTION_CREDIT` | 16.8 | 16.8 | 8.4 | 33.6 | `_WIN_PASS_OPTION_CREDIT = 16.8` |
| `call_decision._JUNK_CUT_SPEED_BONUS_MIN` | 15.0 | 15.0 | 7.5 | 30.0 | `_JUNK_CUT_SPEED_BONUS_MIN = 15.0` |
| `call_decision._JUNK_CUT_SPEED_BONUS_MAX` | 25.0 | 25.0 | 12.5 | 50.0 | `_JUNK_CUT_SPEED_BONUS_MAX = 25.0` |
| `call_decision._PONG_HU_EV_SCALE` | 2.5 | 2.5 | 1.25 | 5.0 | `_PONG_HU_EV_SCALE = 2.5` |
| `call_decision._REDUNDANT_SEQUENCE_CHI_PENALTY` | 55.0 | 55.0 | 27.5 | 110.0 | `_REDUNDANT_SEQUENCE_CHI_PENALTY = 55.0` |
| `call_decision._NO_SHANTEN_DROP_CALL_PENALTY` | 18.0 | 18.0 | 9.0 | 36.0 | `_NO_SHANTEN_DROP_CALL_PENALTY = 18.0` |
| `call_decision._PASS_DRAW_TURN_BASE` | 22.0 | 22.0 | 11.0 | 44.0 | `_PASS_DRAW_TURN_BASE = 22.0` |
| `call_decision._PASS_DRAW_UKEIRE_SCALE` | 0.35 | 0.35 | 0.175 | 0.7 | `_PASS_DRAW_UKEIRE_SCALE = 0.35  # 每张有效进张额外加成（封顶见下）` |
| `call_decision._YAKUHAI_FAN_MAKE_CHANCE.0` | 0.25 | 0.25 | 0.125 | 0.5 | `_YAKUHAI_FAN_MAKE_CHANCE = {0: 0.25, 1: 0.65}` |
| `call_decision._YAKUHAI_FAN_MAKE_CHANCE.1` | 0.65 | 0.65 | 0.325 | 1.0 | `_YAKUHAI_FAN_MAKE_CHANCE = {0: 0.25, 1: 0.65}` |
| `call_decision._hard_hu_discount.L346C11` | 0.15 | 0.15 | 0.075 | 0.3 | `return 0.15` |
| `call_decision._hard_hu_discount.L345C15` | 0.5 | 0.5 | 0.25 | 1.0 | `return 0.5` |
| `call_decision._early_flush_ambition_bonus.L399C23` | 200.0 | 200.0 | 100.0 | 400.0 | `projected_points = 200.0 if honors else 260.0` |
| `call_decision._early_flush_ambition_bonus.L399C44` | 260.0 | 260.0 | 130.0 | 520.0 | `projected_points = 200.0 if honors else 260.0` |
| `call_decision._early_flush_ambition_bonus.L400C27` | 0.48 | 0.48 | 0.24 | 0.96 | `make_probability = min(0.48, 0.18 + 0.025 * (suit_count - 8) + 0.035 * max(0, 3 - off_suit))` |
| `call_decision._early_flush_ambition_bonus.L401C24` | 0.92 | 0.92 | 0.46 | 1.0 | `make_probability *= 0.92 ** len(melds)` |
| `call_decision._pong_incentive.L461C48` | 0.85 | 0.85 | 0.425 | 1.0 | `hu_weight = 1.0 if shanten_before <= 1 else 0.85` |
| `call_decision._pong_incentive.L522C17` | 12.0 | 12.0 | 6.0 | 24.0 | `bonus += 12.0` |
| `call_decision._early_flush_ambition_bonus.L391C42` | 0.15 | 0.15 | 0.075 | 0.3 | `if tenpai and max(tenpai.values()) >= 0.15:` |
| `call_decision._early_flush_ambition_bonus.L402C29` | 12.0 | 12.0 | 6.0 | 24.0 | `safety_credit = max(0.0, 12.0 * (1.0 - (max(tenpai.values()) if tenpai else 0.03) / 0.15))` |
| `call_decision._pong_incentive.L460C33` | 1.15 | 1.15 | 0.575 | 2.3 | `scale = _PONG_HU_EV_SCALE * (1.15 if is_dealer else 1.0)` |
| `call_decision._pong_incentive.L481C66` | 0.45 | 0.45 | 0.225 | 0.9 | `make_chance = _YAKUHAI_FAN_MAKE_CHANCE.get(shanten_after, 0.45)` |
| `call_decision._evaluate_call_ev.L585C52` | 0.85 | 0.85 | 0.425 | 1.0 | `hu_weight = 1.0 if shanten_before <= 1 else 0.85` |
| `call_decision._evaluate_pass_ev.L738C26` | 1.15 | 1.15 | 0.575 | 2.3 | `draw_bonus *= 1.15` |
| `call_decision.evaluate_call_decision.L215C22` | 0.55 | 0.55 | 0.275 | 1.0 | `ev *= 0.55` |
| `call_decision.evaluate_call_decision.L301C53` | 0.85 | 0.85 | 0.425 | 1.0 | `hu_weight = 1.0 if shanten_now <= 1 else 0.85` |
| `call_decision._early_flush_ambition_bonus.L400C33` | 0.18 | 0.18 | 0.09 | 0.36 | `make_probability = min(0.48, 0.18 + 0.025 * (suit_count - 8) + 0.035 * max(0, 3 - off_suit))` |
| `call_decision._early_flush_ambition_bonus.L400C67` | 0.035 | 0.035 | 0.0175 | 0.07 | `make_probability = min(0.48, 0.18 + 0.025 * (suit_count - 8) + 0.035 * max(0, 3 - off_suit))` |
| `call_decision._evaluate_call_ev.L610C69` | 4.0 | 4.0 | 2.0 | 8.0 | `live_wait_weight = min(1.0, float(best['effective_count']) / 4.0)` |
| `call_decision.evaluate_call_decision.L304C50` | 0.35 | 0.35 | 0.175 | 0.7 | `+ _PASS_DRAW_TURN_BASE * 0.35)` |
| `call_decision._early_flush_ambition_bonus.L400C40` | 0.025 | 0.025 | 0.0125 | 0.05 | `make_probability = min(0.48, 0.18 + 0.025 * (suit_count - 8) + 0.035 * max(0, 3 - off_suit))` |
| `call_decision._early_flush_ambition_bonus.L402C88` | 0.15 | 0.15 | 0.075 | 0.3 | `safety_credit = max(0.0, 12.0 * (1.0 - (max(tenpai.values()) if tenpai else 0.03) / 0.15))` |
| `call_decision._pong_incentive.L515C16` | 2.0 | 2.0 | 1.0 | 4.0 | `) / 2.0` |
| `call_decision._evaluate_call_ev.L586C40` | 1.15 | 1.15 | 0.575 | 2.3 | `ev += hu * _PONG_HU_EV_SCALE * (1.15 if is_dealer else 1.0) * hu_weight` |
| `call_decision._early_flush_ambition_bonus.L402C80` | 0.03 | 0.03 | 0.015 | 0.06 | `safety_credit = max(0.0, 12.0 * (1.0 - (max(tenpai.values()) if tenpai else 0.03) / 0.15))` |
| `call_decision.evaluate_call_decision.L303C28` | 1.15 | 1.15 | 0.575 | 2.3 | `* (1.15 if is_dealer else 1.0) * hu_weight` |

## screen（8项）

| 参数 | V1当前值 | V0原值 | 离线下界 | 离线上界 | 源码定义/使用表达式 |
|---|---:|---:|---:|---:|---|
| `screen.joker_keep` | 100 | 100 | 40 | 200 | `Fast screening only, not full EV` |
| `screen.duplicate_keep` | 12 | 12 | 3 | 30 | `Fast screening only, not full EV` |
| `screen.central_keep` | 1 | 1 | 0 | 3 | `Fast screening only, not full EV` |
| `screen.neighbor_keep` | 5 | 5 | 1 | 12 | `Fast screening only, not full EV` |
| `screen.gap_keep` | 2 | 2 | 0 | 6 | `Fast screening only, not full EV` |
| `screen.honor_keep` | 2 | 2 | 0 | 12 | `Fast screening only, not full EV` |
| `screen.danger_penalty` | 0 | 0 | 0 | 50 | `Fast screening only, not full EV` |
| `screen.call_bonus` | 1 | 1 | 0 | 5 | `Fast screening only, not full EV` |

## 额外固定的数值控制（未纳入165项调参schema）

| 参数 | 当前值 |
|---|---:|
| `ev_engine._RINSHAN_SAMPLE_CAP` | 12 |
| `ev_engine._TENPAI_RYANMEN_BASELINE` | 8 |
| `ev_engine._MAX_DISCARD_CANDIDATES` | 8 |
| `call_decision._PASS_DRAW_UKEIRE_CAP` | 20 |
| `call_decision._EARLY_FLUSH_MIN_SUIT_TILES` | 8 |
| `call_decision._EARLY_FLUSH_MIN_HAND_TILES` | 10 |
| `tenpai_model._CENTRAL_LOOKBACK` | 2 |
| `tenpai_model._CENTRAL_EARLY_TURN` | 4 |
| `tenpai_model._SAFE_STREAK_MIN_TURN` | 5 |
| `tenpai_model._SAFE_STREAK_LOOKBACK` | 3 |
| `tenpai_model._SAFE_STREAK_NEED` | 2 |
| `tenpai_model._P_MIN` | 0.02 |
| `tenpai_model._P_MAX` | 0.95 |

## 冗余吃牌硬规则

吃后V1最优弃牌与吃入牌同质、吃前吃后均为听牌、逐张听口剩余数与计分收益完全一致且听口非空：不推荐该吃法，展示评分固定为PASS评分减1。合法吃/过选项保留给玩家；该1分差是推荐约束，不是新的模拟EV或调参权重。

## V2副露参数（仅离线实验，当前生产V1未启用）

| 参数 | 实验基准值 | 窄边界 |
|---|---:|---|
| `redundant_chow_penalty` | 55.0 | 45.0 ～ 60.0 |
| `no_advance_chow_penalty` | 18.0 | 15.0 ～ 22.0 |
| `claim_to_tenpai_reward` | 40.0 | 35.0 ～ 45.0 |
| `pung_value_incentive` | 1.0 | 0.8 ～ 1.25 |
| `kong_risk_reward_factor` | 1.0 | 0.9 ～ 1.1 |

胡牌合法性、财神映射、胡数结算、每张牌4张等为规则内核，不列为可调启发式权重；其规则值应查看scoring/constants/evaluator/settlement，不能以调参方式改变。

V1配置指纹：`560c1b97f2a3da4402e1051df4c3e0384fc4ba601b43a36204bfbee538e6d05f`。
