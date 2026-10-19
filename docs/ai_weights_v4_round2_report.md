# V4 第二小轮调优报告

结论：未晋升，不生成 V4 配置。

现任基准为 V1+guard；生产默认加载及 optimized 配置保持原样。

## 方法修订摘要

R1：40 墙、每局最多 8 个固定状态；23 项单参数 ±20%/±40%，取 schema 硬界及次序约束交集。翻转率按四方向总翻转/总重放统计，≥1% 排名前三入选；每个候选只动一个参数，避免强耦合乘数同动。局部 EV 差以现任同一局面的评分为尺度，仅为诊断，不是真实收益。
训练局面采用确定种子的全局面蓄水抽样；局部 EV 覆盖不到的动作单列 missing_ev，不按零值解释。杠富集集包含 EV 训练轨迹和额外 fast 训练轨迹，后者仅用于获得合法状态，专项比较全部使用完整 EV。专项不进入自然分布胜率。
候选快筛使用同墙共同随机数；对独立主验证墙做单侧 95% 正态与墙块 bootstrap（10000次）。基准池 V0/历史V1/V1+guard=20%/40%/40%。报告使用普通函数与共用表格函数。

## 实际规模与耗时

```json
{
  "sizes": {
    "screen": 300,
    "main": 1000,
    "pressure": 252,
    "anchor": 300
  },
  "desired": {
    "screen": 300,
    "main": 1000,
    "pressure": 252,
    "anchor": 300
  },
  "scale": 1,
  "pilot_seconds": 8.625,
  "estimated_seconds": 2766.9,
  "seeds": {
    "pilot": 32600100,
    "sensitivity": 32610000,
    "enrichment": 32620000,
    "screen": 32710000,
    "main": 32810000,
    "A": 32910000,
    "B": 32920000,
    "C": 32930000,
    "D": 32940000,
    "E": 32950000
  },
  "workers": 8,
  "pool_fractions": [
    0.2,
    0.4,
    0.4
  ],
  "training_hands": 160,
  "kong_training_in_natural_sample": false,
  "scan_elapsed_already_completed": true,
  "resumed_locked_candidate": true,
  "elapsed_includes_interruptions": true,
  "win_priority": "Immediate legal win states are opportunities but never beneficial-kong refusals",
  "specialist_command": "F:\\mahjong\\backend\\.venv\\Scripts\\python.exe -m pytest tests/test_v1_chow_guard.py tests/test_claim_invariance.py tests/test_call_decision.py tests/test_ev_engine.py tests/test_danger_model.py tests/test_tenpai_model.py tests/test_action_generator.py tests/test_self_gang.py tests/test_payment_cap.py tests/test_settlement.py tests/test_physical_white_dragon.py tests/test_no_round_wind_fan.py -q",
  "specialist_returncode": 0,
  "regression_command": "F:\\mahjong\\backend\\.venv\\Scripts\\python.exe -m pytest tests/test_ai_weights_loading.py tests/test_offline_ai_tools.py tests/test_focused_validation.py tests/test_v3_tuning.py tests/test_v4_tuning.py tests/test_sensitivity_scan.py -q",
  "regression_returncode": 0
}
```
实际自然对局 5836 局；从吞吐试跑开始累计经过 3133.40 秒（含中断等待、扫描、富集、统计及最终 pytest）。workers=8；续跑命令设超时 10800 秒，输出 data/ai_tuning/v4-round2/console.log。扫描、快筛及锁定结果从检查点恢复，没有重跑或重新选参。

## 敏感度排序全表

训练种子 32610000 起，共 40 墙、1280 状态；所有验证种子独立。扫描耗时 709.12 秒。
| 排名 | 参数 | 翻转/重放 | 翻转率 | 翻转后局部EV差均值 | 缺失EV数 | 结论 |
|---|---|---|---|---|---|---|
| 1 | ev_engine._UKEIRE_QUALITY_WEIGHT | 82/5120 | 1.6016% | -0.681382 | 0 | 入选 |
| 2 | ev_engine._YAKUHAI_SINGLE_POTENTIAL | 56/5120 | 1.0938% | -0.887289 | 0 | 入选 |
| 3 | danger_model.BASE_HONOR_LIVE | 19/5120 | 0.3711% | 0.529611 | 0 | 未入选 |
| 4 | ev_engine._SHAPE_RYANMEN | 17/5120 | 0.3320% | -6.163695 | 0 | 未入选 |
| 5 | danger_model.BASE_MID_456 | 16/5120 | 0.3125% | 0.240944 | 0 | 未入选 |
| 6 | ev_engine._SHAPE_KANCHAN | 15/5120 | 0.2930% | 0.800953 | 0 | 未入选 |
| 7 | ev_engine._GUEST_WIND_SINGLE_PENALTY | 9/5120 | 0.1758% | -2.744978 | 0 | 未入选 |
| 8 | tenpai_model._SIGMOID_CENTER | 9/5120 | 0.1758% | -1.297000 | 0 | 未入选 |
| 9 | danger_model.BASE_NEAR_MID | 8/5120 | 0.1562% | -0.971887 | 0 | 未入选 |
| 10 | tenpai_model._MELD_ADD.1 | 7/5120 | 0.1367% | -0.688371 | 0 | 未入选 |
| 11 | tenpai_model._SIGMOID_STEEPNESS | 6/5120 | 0.1172% | -1.099267 | 0 | 未入选 |
| 12 | ev_engine._ORPHAN_TERMINAL_UKEIRE_SCALE | 4/5120 | 0.0781% | -0.154600 | 0 | 未入选 |
| 13 | tenpai_model._P_SPAN | 3/5120 | 0.0586% | -1.100967 | 0 | 未入选 |
| 14 | ev_engine._SHAPE_PENCHAN | 2/5120 | 0.0391% | -3.286200 | 0 | 未入选 |
| 15 | danger_model.BASE_TERMINAL | 1/5120 | 0.0195% | -3.091300 | 0 | 未入选 |
| 16 | ev_engine.SHANTEN_PENALTY | 1/5120 | 0.0195% | -46.563400 | 0 | 未入选 |
| 17 | danger_model.BASE_HONOR_DEAD | 0/5120 | 0.0000% | 证据不足 | 0 | 当前幅度内不敏感，继续冻结 |
| 18 | danger_model.WALL_BOTH_SIDES_FACTOR | 0/5120 | 0.0000% | 证据不足 | 0 | 当前幅度内不敏感，继续冻结 |
| 19 | danger_model.WALL_ONE_SIDE_EDGE_FACTOR | 0/5120 | 0.0000% | 证据不足 | 0 | 当前幅度内不敏感，继续冻结 |
| 20 | ev_engine._GOOD_SHAPE_DEFENSE_SCALE | 0/5120 | 0.0000% | 证据不足 | 0 | 当前幅度内不敏感，继续冻结 |
| 21 | ev_engine._JANTOU_BREAK_PENALTY | 0/5120 | 0.0000% | 证据不足 | 0 | 当前幅度内不敏感，继续冻结 |
| 22 | ev_engine._YAKUHAI_PAIR_POTENTIAL | 0/5120 | 0.0000% | 证据不足 | 0 | 当前幅度内不敏感，继续冻结 |
| 23 | tenpai_model._MELD_ADD.2 | 0/5120 | 0.0000% | 证据不足 | 0 | 当前幅度内不敏感，继续冻结 |

### 入选理由与区间

≥1% 且全表前三；候选均为单参数，不同时改变耦合乘数。方向按训练翻转数排序，最多各取两个方向。
| 参数 | 有效区间 |
|---|---|
| ev_engine._UKEIRE_QUALITY_WEIGHT | [0.625, 1.246727620234373] |
| ev_engine._YAKUHAI_SINGLE_POTENTIAL | [7.567872077012574, 15.253399288810538] |

逐方向完整统计（含硬界/次序截断后的实际值）：
```json
[
  {
    "key": "ev_engine._UKEIRE_QUALITY_WEIGHT",
    "states": 1280,
    "replays": 5120,
    "flips": 82,
    "rate": 0.016015625,
    "local_ev_delta": [
      33.80440000000023,
      46.89500000000022,
      -33.02430000000007,
      -103.54840476190476
    ],
    "missing_ev": [
      0,
      0,
      0,
      0
    ],
    "directions": [
      {
        "scale": 0.6,
        "flips": 27,
        "rate": 0.02109375,
        "value": 0.625
      },
      {
        "scale": 0.8,
        "flips": 21,
        "rate": 0.01640625,
        "value": 0.7124157829910702
      },
      {
        "scale": 1.2,
        "flips": 10,
        "rate": 0.0078125,
        "value": 1.0686236744866053
      },
      {
        "scale": 1.4,
        "flips": 24,
        "rate": 0.01875,
        "value": 1.246727620234373
      }
    ],
    "bounds": [
      0.625,
      1.246727620234373
    ],
    "mean_flip_ev": -0.6813817653890778
  },
  {
    "key": "ev_engine._YAKUHAI_SINGLE_POTENTIAL",
    "states": 1280,
    "replays": 5120,
    "flips": 56,
    "rate": 0.0109375,
    "local_ev_delta": [
      -93.9503999999999,
      -16.36359999999999,
      30.31290000000007,
      30.31290000000007
    ],
    "missing_ev": [
      0,
      0,
      0,
      0
    ],
    "directions": [
      {
        "scale": 0.6,
        "flips": 16,
        "rate": 0.0125,
        "value": 7.567872077012574
      },
      {
        "scale": 0.8,
        "flips": 4,
        "rate": 0.003125,
        "value": 10.090496102683431
      },
      {
        "scale": 1.2,
        "flips": 18,
        "rate": 0.0140625,
        "value": 15.135744154025147
      },
      {
        "scale": 1.4,
        "flips": 18,
        "rate": 0.0140625,
        "value": 15.253399288810538
      }
    ],
    "bounds": [
      7.567872077012574,
      15.253399288810538
    ],
    "mean_flip_ev": -0.8872892857142813
  },
  {
    "key": "danger_model.BASE_HONOR_LIVE",
    "states": 1280,
    "replays": 5120,
    "flips": 19,
    "rate": 0.0037109375,
    "local_ev_delta": [
      -6.130900000000054,
      -6.130900000000054,
      4.9140000000000015,
      17.41039999999998
    ],
    "missing_ev": [
      0,
      0,
      0,
      0
    ],
    "directions": [
      {
        "scale": 0.6,
        "flips": 2,
        "rate": 0.0015625,
        "value": 0.096
      },
      {
        "scale": 0.8,
        "flips": 2,
        "rate": 0.0015625,
        "value": 0.128
      },
      {
        "scale": 1.2,
        "flips": 4,
        "rate": 0.003125,
        "value": 0.192
      },
      {
        "scale": 1.4,
        "flips": 11,
        "rate": 0.00859375,
        "value": 0.22399999999999998
      }
    ],
    "bounds": [
      0.096,
      0.22399999999999998
    ],
    "mean_flip_ev": 0.5296105263157829
  },
  {
    "key": "ev_engine._SHAPE_RYANMEN",
    "states": 1280,
    "replays": 5120,
    "flips": 17,
    "rate": 0.0033203125,
    "local_ev_delta": [
      -30.26399999999998,
      -15.393199999999979,
      -11.984104761904774,
      -47.14150264863342
    ],
    "missing_ev": [
      0,
      0,
      0,
      0
    ],
    "directions": [
      {
        "scale": 0.6,
        "flips": 5,
        "rate": 0.00390625,
        "value": 6.0
      },
      {
        "scale": 0.8,
        "flips": 3,
        "rate": 0.00234375,
        "value": 8.0
      },
      {
        "scale": 1.2,
        "flips": 3,
        "rate": 0.00234375,
        "value": 12.0
      },
      {
        "scale": 1.4,
        "flips": 6,
        "rate": 0.0046875,
        "value": 14.0
      }
    ],
    "bounds": [
      6.0,
      14.0
    ],
    "mean_flip_ev": -6.163694553561068
  },
  {
    "key": "danger_model.BASE_MID_456",
    "states": 1280,
    "replays": 5120,
    "flips": 16,
    "rate": 0.003125,
    "local_ev_delta": [
      2.609400000000022,
      4.828100000000035,
      -1.7912000000000035,
      -1.7912000000000035
    ],
    "missing_ev": [
      0,
      0,
      0,
      0
    ],
    "directions": [
      {
        "scale": 0.6,
        "flips": 7,
        "rate": 0.00546875,
        "value": 0.12
      },
      {
        "scale": 0.8,
        "flips": 5,
        "rate": 0.00390625,
        "value": 0.144
      },
      {
        "scale": 1.2,
        "flips": 2,
        "rate": 0.0015625,
        "value": 0.216
      },
      {
        "scale": 1.4,
        "flips": 2,
        "rate": 0.0015625,
        "value": 0.252
      }
    ],
    "bounds": [
      0.12,
      0.252
    ],
    "mean_flip_ev": 0.24094375000000312
  },
  {
    "key": "ev_engine._SHAPE_KANCHAN",
    "states": 1280,
    "replays": 5120,
    "flips": 15,
    "rate": 0.0029296875,
    "local_ev_delta": [
      6.745399999999989,
      7.802799999999991,
      1.8784000000000844,
      -4.412299999999931
    ],
    "missing_ev": [
      0,
      0,
      0,
      0
    ],
    "directions": [
      {
        "scale": 0.6,
        "flips": 4,
        "rate": 0.003125,
        "value": 3.0
      },
      {
        "scale": 0.8,
        "flips": 3,
        "rate": 0.00234375,
        "value": 4.0
      },
      {
        "scale": 1.2,
        "flips": 3,
        "rate": 0.00234375,
        "value": 6.0
      },
      {
        "scale": 1.4,
        "flips": 5,
        "rate": 0.00390625,
        "value": 7.0
      }
    ],
    "bounds": [
      3.0,
      7.0
    ],
    "mean_flip_ev": 0.8009533333333423
  },
  {
    "key": "ev_engine._GUEST_WIND_SINGLE_PENALTY",
    "states": 1280,
    "replays": 5120,
    "flips": 9,
    "rate": 0.0017578125,
    "local_ev_delta": [
      0.0,
      0.0,
      -10.316500000000076,
      -14.388300000000072
    ],
    "missing_ev": [
      0,
      0,
      0,
      0
    ],
    "directions": [
      {
        "scale": 0.6,
        "flips": 0,
        "rate": 0.0,
        "value": 7.199999999999999
      },
      {
        "scale": 0.8,
        "flips": 0,
        "rate": 0.0,
        "value": 9.600000000000001
      },
      {
        "scale": 1.2,
        "flips": 4,
        "rate": 0.003125,
        "value": 14.399999999999999
      },
      {
        "scale": 1.4,
        "flips": 5,
        "rate": 0.00390625,
        "value": 16.799999999999997
      }
    ],
    "bounds": [
      7.199999999999999,
      16.799999999999997
    ],
    "mean_flip_ev": -2.744977777777794
  },
  {
    "key": "tenpai_model._SIGMOID_CENTER",
    "states": 1280,
    "replays": 5120,
    "flips": 9,
    "rate": 0.0017578125,
    "local_ev_delta": [
      -2.187499999999986,
      2.8898999999999972,
      -6.187700000000035,
      -6.187700000000035
    ],
    "missing_ev": [
      0,
      0,
      0,
      0
    ],
    "directions": [
      {
        "scale": 0.6,
        "flips": 4,
        "rate": 0.003125,
        "value": 6.060628609033757
      },
      {
        "scale": 0.8,
        "flips": 1,
        "rate": 0.00078125,
        "value": 8.080838145378342
      },
      {
        "scale": 1.2,
        "flips": 2,
        "rate": 0.0015625,
        "value": 12.121257218067514
      },
      {
        "scale": 1.4,
        "flips": 2,
        "rate": 0.0015625,
        "value": 14.141466754412098
      }
    ],
    "bounds": [
      6.060628609033757,
      14.141466754412098
    ],
    "mean_flip_ev": -1.2970000000000066
  },
  {
    "key": "danger_model.BASE_NEAR_MID",
    "states": 1280,
    "replays": 5120,
    "flips": 8,
    "rate": 0.0015625,
    "local_ev_delta": [
      2.8898999999999972,
      2.8898999999999972,
      -6.135999999999996,
      -7.418899999999951
    ],
    "missing_ev": [
      0,
      0,
      0,
      0
    ],
    "directions": [
      {
        "scale": 0.6,
        "flips": 1,
        "rate": 0.00078125,
        "value": 0.08
      },
      {
        "scale": 0.8,
        "flips": 1,
        "rate": 0.00078125,
        "value": 0.096
      },
      {
        "scale": 1.2,
        "flips": 2,
        "rate": 0.0015625,
        "value": 0.144
      },
      {
        "scale": 1.4,
        "flips": 4,
        "rate": 0.003125,
        "value": 0.16799999999999998
      }
    ],
    "bounds": [
      0.08,
      0.16799999999999998
    ],
    "mean_flip_ev": -0.971887499999994
  },
  {
    "key": "tenpai_model._MELD_ADD.1",
    "states": 1280,
    "replays": 5120,
    "flips": 7,
    "rate": 0.0013671875,
    "local_ev_delta": [
      -3.3332000000000335,
      -6.187700000000035,
      0.0,
      4.702299999999994
    ],
    "missing_ev": [
      0,
      0,
      0,
      0
    ],
    "directions": [
      {
        "scale": 0.6,
        "flips": 3,
        "rate": 0.00234375,
        "value": 0.084
      },
      {
        "scale": 0.8,
        "flips": 2,
        "rate": 0.0015625,
        "value": 0.11200000000000002
      },
      {
        "scale": 1.2,
        "flips": 0,
        "rate": 0.0,
        "value": 0.168
      },
      {
        "scale": 1.4,
        "flips": 2,
        "rate": 0.0015625,
        "value": 0.196
      }
    ],
    "bounds": [
      0.084,
      0.196
    ],
    "mean_flip_ev": -0.6883714285714392
  },
  {
    "key": "tenpai_model._SIGMOID_STEEPNESS",
    "states": 1280,
    "replays": 5120,
    "flips": 6,
    "rate": 0.001171875,
    "local_ev_delta": [
      2.8898999999999972,
      2.8898999999999972,
      -6.187700000000035,
      -6.187700000000035
    ],
    "missing_ev": [
      0,
      0,
      0,
      0
    ],
    "directions": [
      {
        "scale": 0.6,
        "flips": 1,
        "rate": 0.00078125,
        "value": 0.252
      },
      {
        "scale": 0.8,
        "flips": 1,
        "rate": 0.00078125,
        "value": 0.336
      },
      {
        "scale": 1.2,
        "flips": 2,
        "rate": 0.0015625,
        "value": 0.504
      },
      {
        "scale": 1.4,
        "flips": 2,
        "rate": 0.0015625,
        "value": 0.588
      }
    ],
    "bounds": [
      0.252,
      0.588
    ],
    "mean_flip_ev": -1.0992666666666793
  },
  {
    "key": "ev_engine._ORPHAN_TERMINAL_UKEIRE_SCALE",
    "states": 1280,
    "replays": 5120,
    "flips": 4,
    "rate": 0.00078125,
    "local_ev_delta": [
      2.782100000000014,
      2.782100000000014,
      -3.0913000000000466,
      -3.0913000000000466
    ],
    "missing_ev": [
      0,
      0,
      0,
      0
    ],
    "directions": [
      {
        "scale": 0.6,
        "flips": 1,
        "rate": 0.00078125,
        "value": 0.132
      },
      {
        "scale": 0.8,
        "flips": 1,
        "rate": 0.00078125,
        "value": 0.17600000000000002
      },
      {
        "scale": 1.2,
        "flips": 1,
        "rate": 0.00078125,
        "value": 0.264
      },
      {
        "scale": 1.4,
        "flips": 1,
        "rate": 0.00078125,
        "value": 0.308
      }
    ],
    "bounds": [
      0.132,
      0.308
    ],
    "mean_flip_ev": -0.15460000000001628
  },
  {
    "key": "tenpai_model._P_SPAN",
    "states": 1280,
    "replays": 5120,
    "flips": 3,
    "rate": 0.0005859375,
    "local_ev_delta": [
      -3.0963999999999885,
      -3.0963999999999885,
      0.0,
      2.8898999999999972
    ],
    "missing_ev": [
      0,
      0,
      0,
      0
    ],
    "directions": [
      {
        "scale": 0.6,
        "flips": 1,
        "rate": 0.00078125,
        "value": 0.312
      },
      {
        "scale": 0.8,
        "flips": 1,
        "rate": 0.00078125,
        "value": 0.41600000000000004
      },
      {
        "scale": 1.2,
        "flips": 0,
        "rate": 0.0,
        "value": 0.624
      },
      {
        "scale": 1.4,
        "flips": 1,
        "rate": 0.00078125,
        "value": 0.728
      }
    ],
    "bounds": [
      0.312,
      0.728
    ],
    "mean_flip_ev": -1.10096666666666
  },
  {
    "key": "ev_engine._SHAPE_PENCHAN",
    "states": 1280,
    "replays": 5120,
    "flips": 2,
    "rate": 0.000390625,
    "local_ev_delta": [
      -3.2861999999999796,
      -3.2861999999999796,
      0.0,
      0.0
    ],
    "missing_ev": [
      0,
      0,
      0,
      0
    ],
    "directions": [
      {
        "scale": 0.6,
        "flips": 1,
        "rate": 0.00078125,
        "value": 1.7999999999999998
      },
      {
        "scale": 0.8,
        "flips": 1,
        "rate": 0.00078125,
        "value": 2.4000000000000004
      },
      {
        "scale": 1.2,
        "flips": 0,
        "rate": 0.0,
        "value": 3.5999999999999996
      },
      {
        "scale": 1.4,
        "flips": 0,
        "rate": 0.0,
        "value": 4.199999999999999
      }
    ],
    "bounds": [
      1.7999999999999998,
      4.199999999999999
    ],
    "mean_flip_ev": -3.2861999999999796
  },
  {
    "key": "danger_model.BASE_TERMINAL",
    "states": 1280,
    "replays": 5120,
    "flips": 1,
    "rate": 0.0001953125,
    "local_ev_delta": [
      0.0,
      0.0,
      0.0,
      -3.0913000000000466
    ],
    "missing_ev": [
      0,
      0,
      0,
      0
    ],
    "directions": [
      {
        "scale": 0.6,
        "flips": 0,
        "rate": 0.0,
        "value": 0.048
      },
      {
        "scale": 0.8,
        "flips": 0,
        "rate": 0.0,
        "value": 0.064
      },
      {
        "scale": 1.2,
        "flips": 0,
        "rate": 0.0,
        "value": 0.096
      },
      {
        "scale": 1.4,
        "flips": 1,
        "rate": 0.00078125,
        "value": 0.11199999999999999
      }
    ],
    "bounds": [
      0.048,
      0.11199999999999999
    ],
    "mean_flip_ev": -3.0913000000000466
  },
  {
    "key": "ev_engine.SHANTEN_PENALTY",
    "states": 1280,
    "replays": 5120,
    "flips": 1,
    "rate": 0.0001953125,
    "local_ev_delta": [
      -46.5634,
      0.0,
      0.0,
      0.0
    ],
    "missing_ev": [
      0,
      0,
      0,
      0
    ],
    "directions": [
      {
        "scale": 0.6,
        "flips": 1,
        "rate": 0.00078125,
        "value": 79
      },
      {
        "scale": 0.8,
        "flips": 0,
        "rate": 0.0,
        "value": 105
      },
      {
        "scale": 1.2,
        "flips": 0,
        "rate": 0.0,
        "value": 157
      },
      {
        "scale": 1.4,
        "flips": 0,
        "rate": 0.0,
        "value": 183
      }
    ],
    "bounds": [
      79,
      183
    ],
    "mean_flip_ev": -46.5634
  },
  {
    "key": "danger_model.BASE_HONOR_DEAD",
    "states": 1280,
    "replays": 5120,
    "flips": 0,
    "rate": 0.0,
    "local_ev_delta": [
      0.0,
      0.0,
      0.0,
      0.0
    ],
    "missing_ev": [
      0,
      0,
      0,
      0
    ],
    "directions": [
      {
        "scale": 0.6,
        "flips": 0,
        "rate": 0.0,
        "value": 0.012
      },
      {
        "scale": 0.8,
        "flips": 0,
        "rate": 0.0,
        "value": 0.016
      },
      {
        "scale": 1.2,
        "flips": 0,
        "rate": 0.0,
        "value": 0.024
      },
      {
        "scale": 1.4,
        "flips": 0,
        "rate": 0.0,
        "value": 0.027999999999999997
      }
    ],
    "bounds": [
      0.012,
      0.027999999999999997
    ],
    "mean_flip_ev": null
  },
  {
    "key": "danger_model.WALL_BOTH_SIDES_FACTOR",
    "states": 1280,
    "replays": 5120,
    "flips": 0,
    "rate": 0.0,
    "local_ev_delta": [
      0.0,
      0.0,
      0.0,
      0.0
    ],
    "missing_ev": [
      0,
      0,
      0,
      0
    ],
    "directions": [
      {
        "scale": 0.6,
        "flips": 0,
        "rate": 0.0,
        "value": 0.27
      },
      {
        "scale": 0.8,
        "flips": 0,
        "rate": 0.0,
        "value": 0.36000000000000004
      },
      {
        "scale": 1.2,
        "flips": 0,
        "rate": 0.0,
        "value": 0.54
      },
      {
        "scale": 1.4,
        "flips": 0,
        "rate": 0.0,
        "value": 0.63
      }
    ],
    "bounds": [
      0.27,
      0.63
    ],
    "mean_flip_ev": null
  },
  {
    "key": "danger_model.WALL_ONE_SIDE_EDGE_FACTOR",
    "states": 1280,
    "replays": 5120,
    "flips": 0,
    "rate": 0.0,
    "local_ev_delta": [
      0.0,
      0.0,
      0.0,
      0.0
    ],
    "missing_ev": [
      0,
      0,
      0,
      0
    ],
    "directions": [
      {
        "scale": 0.6,
        "flips": 0,
        "rate": 0.0,
        "value": 0.45
      },
      {
        "scale": 0.8,
        "flips": 0,
        "rate": 0.0,
        "value": 0.5599999999999999
      },
      {
        "scale": 1.2,
        "flips": 0,
        "rate": 0.0,
        "value": 0.84
      },
      {
        "scale": 1.4,
        "flips": 0,
        "rate": 0.0,
        "value": 0.9799999999999999
      }
    ],
    "bounds": [
      0.45,
      0.9799999999999999
    ],
    "mean_flip_ev": null
  },
  {
    "key": "ev_engine._GOOD_SHAPE_DEFENSE_SCALE",
    "states": 1280,
    "replays": 5120,
    "flips": 0,
    "rate": 0.0,
    "local_ev_delta": [
      0.0,
      0.0,
      0.0,
      0.0
    ],
    "missing_ev": [
      0,
      0,
      0,
      0
    ],
    "directions": [
      {
        "scale": 0.6,
        "flips": 0,
        "rate": 0.0,
        "value": 0.2474380476250056
      },
      {
        "scale": 0.8,
        "flips": 0,
        "rate": 0.0,
        "value": 0.32991739683334087
      },
      {
        "scale": 1.2,
        "flips": 0,
        "rate": 0.0,
        "value": 0.4948760952500112
      },
      {
        "scale": 1.4,
        "flips": 0,
        "rate": 0.0,
        "value": 0.5773554444583464
      }
    ],
    "bounds": [
      0.2474380476250056,
      0.5773554444583464
    ],
    "mean_flip_ev": null
  },
  {
    "key": "ev_engine._JANTOU_BREAK_PENALTY",
    "states": 1280,
    "replays": 5120,
    "flips": 0,
    "rate": 0.0,
    "local_ev_delta": [
      0.0,
      0.0,
      0.0,
      0.0
    ],
    "missing_ev": [
      0,
      0,
      0,
      0
    ],
    "directions": [
      {
        "scale": 0.6,
        "flips": 0,
        "rate": 0.0,
        "value": 12.64121797025203
      },
      {
        "scale": 0.8,
        "flips": 0,
        "rate": 0.0,
        "value": 16.854957293669376
      },
      {
        "scale": 1.2,
        "flips": 0,
        "rate": 0.0,
        "value": 25.28243594050406
      },
      {
        "scale": 1.4,
        "flips": 0,
        "rate": 0.0,
        "value": 29.496175263921405
      }
    ],
    "bounds": [
      12.64121797025203,
      29.496175263921405
    ],
    "mean_flip_ev": null
  },
  {
    "key": "ev_engine._YAKUHAI_PAIR_POTENTIAL",
    "states": 1280,
    "replays": 5120,
    "flips": 0,
    "rate": 0.0,
    "local_ev_delta": [
      0.0,
      0.0,
      0.0,
      0.0
    ],
    "missing_ev": [
      0,
      0,
      0,
      0
    ],
    "directions": [
      {
        "scale": 0.6,
        "flips": 0,
        "rate": 0.0,
        "value": 12.61312012835429
      },
      {
        "scale": 0.8,
        "flips": 0,
        "rate": 0.0,
        "value": 12.61312012835429
      },
      {
        "scale": 1.2,
        "flips": 0,
        "rate": 0.0,
        "value": 18.304079146572644
      },
      {
        "scale": 1.4,
        "flips": 0,
        "rate": 0.0,
        "value": 21.354759004334753
      }
    ],
    "bounds": [
      12.61312012835429,
      21.354759004334753
    ],
    "mean_flip_ev": null
  },
  {
    "key": "tenpai_model._MELD_ADD.2",
    "states": 1280,
    "replays": 5120,
    "flips": 0,
    "rate": 0.0,
    "local_ev_delta": [
      0.0,
      0.0,
      0.0,
      0.0
    ],
    "missing_ev": [
      0,
      0,
      0,
      0
    ],
    "directions": [
      {
        "scale": 0.6,
        "flips": 0,
        "rate": 0.0,
        "value": 0.18
      },
      {
        "scale": 0.8,
        "flips": 0,
        "rate": 0.0,
        "value": 0.24
      },
      {
        "scale": 1.2,
        "flips": 0,
        "rate": 0.0,
        "value": 0.36
      },
      {
        "scale": 1.4,
        "flips": 0,
        "rate": 0.0,
        "value": 0.42
      }
    ],
    "bounds": [
      0.18,
      0.42
    ],
    "mean_flip_ev": null
  }
]
```

## 快筛与锁定

| 候选 | 参数实际值（空为基准） | 净分差/局 | 放铳差 | 锁定 |
|---|---|---|---|---|
| 0 | {} | 0.000000 | 0.000000 | False |
| 1 | {"ev_engine._UKEIRE_QUALITY_WEIGHT": 0.625} | -1.286667 | 0.010000 | False |
| 2 | {"ev_engine._UKEIRE_QUALITY_WEIGHT": 1.246727620234373} | 1.140000 | -0.013333 | True |
| 3 | {"ev_engine._YAKUHAI_SINGLE_POTENTIAL": 15.135744154025147} | -0.590000 | 0.003333 | False |
| 4 | {"ev_engine._YAKUHAI_SINGLE_POTENTIAL": 15.253399288810538} | -0.560000 | 0.003333 | False |

## 主验证

| 指标 | 均值差 | 正态下界 | bootstrap下界 | 正态上界 | bootstrap上界 |
|---|---|---|---|---|---|
| net | 0.371000 | -0.590805 | -0.578050 | 1.332805 | 1.377050 |
| dealin | -0.003000 | -0.011235 | -0.011000 | 0.005235 | 0.005000 |
| zimo | 0.004000 | -0.001195 | -0.001000 | 0.009195 | 0.009000 |
| progress | 0.002299 | -0.000702 | -0.000740 | 0.005300 | 0.005233 |
| low_tenpai | 0.008571 | 0.000973 | 0.001771 | 0.016169 | 0.016822 |

### 自然分布吃碰杠（专项不混入本表）

| 类型 | 候选机会/选择 | 现任机会/选择 | 候选率 | 现任率 |
|---|---|---|---|---|
| chi | 1027/556 | 1027/544 | 0.541383 | 0.529698 |
| pong | 651/553 | 648/549 | 0.849462 | 0.847222 |
| ming_gang | 32/31 | 32/31 | 0.968750 | 0.968750 |
| an_gang | 31/10 | 31/9 | 0.322581 | 0.290323 |
| bu_gang | 19/19 | 18/18 | 1.000000 | 1.000000 |

## 杠专项

有收益定义：现任完整局部 EV 中该杠最佳分高于其他合法动作最佳分；比较同一固定状态。可立即和牌的状态仍计合法机会，但和牌优先，不标成有收益杠、不将选择和牌计作拒绝杠。要求每类≥200、选择率比在[0.75,1.25]、存在有收益状态且候选全部选择，并保留非杠选择。
| 类型 | 状态 | 现任选择 | 候选选择 | 有收益状态 | 有收益现任选择 | 有收益候选选择 |
|---|---|---|---|---|---|---|
| ming_gang | 902 | 848 | 850 | 848 | 848 | 848 |
| an_gang | 201 | 125 | 126 | 125 | 125 | 124 |
| bu_gang | 1361 | 1351 | 1351 | 963 | 963 | 963 |
```json
{
  "seed": 32620000,
  "walls": 3280,
  "hands": 3280,
  "counts": {
    "ming_gang": 902,
    "an_gang": 201,
    "bu_gang": 1361
  },
  "deduplicated": true,
  "trajectory": "EV scan walls plus one fast hand per additional training wall; evaluated with full EV"
}
```

## 压力单元 A–D

A=V0×3；B=历史V1×3；C=V0/历史V1/guard；D=guard×3。非劣界 −1。

### A

| 指标 | 均值差 | 正态下界 | bootstrap下界 | 正态上界 | bootstrap上界 |
|---|---|---|---|---|---|
| net | 0.892857 | -0.812642 | -0.698413 | 2.598357 | 2.714286 |

### B

| 指标 | 均值差 | 正态下界 | bootstrap下界 | 正态上界 | bootstrap上界 |
|---|---|---|---|---|---|
| net | 0.750000 | -0.892457 | -0.817460 | 2.392457 | 2.388889 |

### C

| 指标 | 均值差 | 正态下界 | bootstrap下界 | 正态上界 | bootstrap上界 |
|---|---|---|---|---|---|
| net | -0.472222 | -1.338642 | -1.345238 | 0.394198 | 0.376984 |

### D

| 指标 | 均值差 | 正态下界 | bootstrap下界 | 正态上界 | bootstrap上界 |
|---|---|---|---|---|---|
| net | -0.130952 | -1.648519 | -1.599206 | 1.386614 | 1.376984 |

## E 锚点赛与 Elo

E 固定 V0/候选/历史V1/guard 阵容，墙块 bootstrap，Elo 下界要求 ≥−10。
```json
{
  "versions": [
    "V0",
    "candidate",
    "historical-V1",
    "V1+guard"
  ],
  "ratings": [
    1500.0,
    1499.131407739511,
    1498.5523448898816,
    1500.0
  ],
  "gain": -0.8685922604890948,
  "gain_bootstrap_lower": -13.036110539643516,
  "pairwise_ranking_win_rates": [
    [
      null,
      0.49166666666666664,
      0.495,
      0.5166666666666667
    ],
    [
      0.5083333333333333,
      null,
      0.49833333333333335,
      0.49166666666666664
    ],
    [
      0.505,
      0.5016666666666667,
      null,
      0.48833333333333334
    ],
    [
      0.48333333333333334,
      0.5083333333333333,
      0.5116666666666667,
      null
    ]
  ],
  "blocks": 75,
  "hands": 300,
  "bootstrap_repeats": 10000,
  "bootstrap_seed": 61017,
  "net_per_hand": [
    -0.49333333333333335,
    -0.19333333333333333,
    0.27,
    0.4166666666666667
  ]
}
```

## 门槛逐项

| 门槛 | 通过 |
|---|---|
| main_sample | 通过 |
| net | 未通过 |
| dealin | 未通过 |
| progress | 通过 |
| zimo | 通过 |
| low_risk_tenpai | 通过 |
| invariants | 通过 |
| elo | 未通过 |
| rate_chi | 通过 |
| opportunities_chi | 通过 |
| noncollapse_chi | 通过 |
| rate_pong | 通过 |
| opportunities_pong | 通过 |
| noncollapse_pong | 通过 |
| rate_ming_gang | 通过 |
| opportunities_ming_gang | 通过 |
| noncollapse_ming_gang | 通过 |
| rate_an_gang | 通过 |
| opportunities_an_gang | 通过 |
| rate_bu_gang | 通过 |
| opportunities_bu_gang | 通过 |
| pressure_A | 通过 |
| pressure_B | 通过 |
| pressure_C | 未通过 |
| pressure_D | 未通过 |
| noncollapse_an_gang | 未通过 |
| noncollapse_bu_gang | 通过 |
| minimum_main_walls | 通过 |

## 结论与下一轮建议

仅全部通过才生成 app/config/ai_weights_v4.json；本轮未通过，候选仅保存在 data/ai_tuning/v4-round2/。
下一轮优先复测显著敏感参数的独立局部区间；零翻转项继续冻结。若置信区间不足，应增加独立墙块，避免查看验证结果后再选参数。杠专项继续单独富集，不用自然稀少机会作否决。
