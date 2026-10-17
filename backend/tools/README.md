# 离线麻将 AI 评估与演化

正式批次可从 backend 运行：

```powershell
.\.venv\Scripts\python.exe -u scripts/tune_ai_weights.py --focus-core --generations 3 --population 8 --elites 3 --hands 1000 --validation-hands 2000 --workers 8 --output data/ai_tuning/formal-core-3g-v2
```

每约 15 秒显示完成局数、累计净分、当次评估 ETA。存档写入 `data/checkpoints/<output目录名>/`，保存完成评估、完整四局块的部分评估、精英参数和代际状态。异常恢复使用完全相同参数追加 `--resume`；可调整 workers，但实现与搜索参数变化时拒绝混用旧实验。恢复通过确定性重放搜索并重用评估存档，不重新计算已保存完整评估。进程池在退出时取消未开始任务并回收工作进程。

最终 `validation_report.md` 对比 2000 局净分、和牌率、放铳率及 12 项权重，`final_status.json` 记录晋升状态；仅晋升后产生同目录 `ai_weights_optimized.json`，这个专用实验输出路径不会被生产服务自动读取。大规模检验发现的白板替身重叠搭子 bug 已在离线所有策略中一致修正（逻辑财神牌名转换为实体 P），生产源码和冻结 V0 源文件未修改。

此工具不启动 FastAPI，不修改生产全局参数，不连接数据库或 WebSocket，不保存模拟牌谱到线上。默认不会加载 optimized 文件到生产。

## 快速开始（PowerShell，在 backend 目录）

```powershell
.\.venv\Scripts\python.exe scripts/run_headless_simulation.py --hands 50 --workers 1 --mode fast
.\.venv\Scripts\python.exe scripts/run_headless_simulation.py --hands 1000 --workers 4 --mode ev
.\.venv\Scripts\python.exe scripts/tune_ai_weights.py --focus-core --generations 10 --population 6 --hands 1000 --validation-hands 2000 --workers 4
```

指定物理座位 0/1/2/3 的策略（顺序即座位）：

```powershell
.\.venv\Scripts\python.exe scripts/run_headless_simulation.py --hands 1000 --workers 4 --mode ev --policies tools/policy_pool/aggressive.json tools/policy_pool/baseline_v0.json tools/policy_pool/conservative.json tools/policy_pool/baseline_v0.json
```

CLI 的 50 局 smoke 自动上取整到 52 局，确保完整四方轮庄。底层 API 拒绝不完整的四局块。每个块用同一随机牌墙轮换四个物理庄位；52 局是 13 个独立牌墙样本，2000 局是 500 个独立块。候选占物理座位 1（按 0/1/2/3 编号的第二位），其门风随庄家轮换，始终只能看到自身暗手和他家公开信息。

## 模块与参数

- `weights_schema.json`：逐参数 default/min/max/integer、原始位置和含义。所有值必须有限、非负且满足硬界限；概率系数不得超过 1，角色牌和牌形价值还有顺序约束。
- `policy_pool/baseline_v0.json`：冻结当前本地 AI 工作树的 V0（包含本次任务前已有的未提交 AI 修改），不是已部署线上版本。
- `policy_sources/`：V0 的 EV、吃碰杠决策、危险度和听牌概率源码快照。运行时按 AST 位置加载 JSON 权重。规则计分常量、面子张数、进张枚举上限和浮点容差不演化。
- `weights.py`：校验配置、哈希检查、独立模块加载。生产模块不会被 monkeypatch；策略图缓存最多 8 组，规则函数和规则缓存共享。
- `arena.py`：复用 PvpMatch 权威摸打和结算，覆盖时钟/展示事件/历史保存。胡牌布尔检查用同一个 evaluator 的 is_complete_win 避免无意义的向听穷举；单测检查合法动作与原内核一致。每局检查 136 张牌守恒、每种牌 4 张和净分零和。

`ev` 使用完整 EV 和副露决策（合法和牌立即执行，不演化拒绝胡牌）。`fast` 保留原 PvP 轻量模式，只读取 `screen.*`。新增 `explore` 用局部搭子、邻张剩余供给、财神和役牌保留、公开巡目风险等廉价特征读取与 EV 相同的 12 项核心权重，是快速筛选的代理策略，不计算完整向听或胡分 EV，也不能代表完整 EV 的棋力。三种模式没有网络等待。

默认 `--pipeline two-stage`：每代快速代理对战 `--hands`（默认 1000），与相同牌墙和对手的 V0 配对；只保留累计净分严格超过 V0 的候选，按净分排序、和牌率破同分，最多 3 名精英。然后仅精英与完整 EV 的 V0/上一稳定版本在新牌墙上进行 `--validation-hands`（正式至少 2000）局检验。没有超过 V0 的候选时不进入第二阶段，不补充落后候选凑数。完整 EV 选出的最佳候选成为下一代搜索父本；父本不等于已晋升稳定策略。

`--focus-core` 明确锁定以下 12 项，其余 153 项始终为 V0 值；双阶段默认也只搜索此集合：

| 方向 | 参数（模块前缀省略） |
| --- | --- |
| 向听推进 | `SHANTEN_PENALTY`、`_DEEP_SHANTEN_UNIT` |
| 进张广度 | `_UKEIRE_QUALITY_WEIGHT` |
| 财神保留 | `_SHAPE_JOKER`、`_JOKER_MID_CUT_PENALTY` |
| 役牌与雀头 | `_YAKUHAI_SINGLE_POTENTIAL`、`_YAKUHAI_PAIR_POTENTIAL`、`_JANTOU_BREAK_PENALTY` |
| 风险与防守折价 | `_GOOD_SHAPE_DEFENSE_SCALE`、`_DEFENSE_RISK_REFERENCE` |
| 巡目风险曲线 | `tenpai_model._SIGMOID_CENTER`、`tenpai_model._SIGMOID_STEEPNESS` |

旧版单阶段通过 `--pipeline single-stage` 使用；该模式下 `--all-weights` 或 `--parameters KEY ...` 才能开放其他参数。`screen.*` 仅用于 fast。核心集合依据决策用途选定，尚未以大样本完成敏感度排序；代理会遗漏只在精确 EV 中体现的优秀候选，这属于快速筛选的代价。

## 完整 EV 的等价加速

`ev_acceleration.py` 仅对离线私有模块安装缓存：手牌身份计数、完整输入的候选切牌、摸入进张判定、向听和胡牌布尔值。缓存有界，策略相关缓存由每个独立权重模块持有，绝不跨参数误用；候选列表返回副本。绝章摸牌直接排除；摸后切回同一张且向听未变的分支提前跳过。没有削减有效进张数或岭上采样上限。

`shanten_kernel.py` 复刻既有向听 DFS 的分支顺序、百搭补张、雀头枚举和乐观剪枝，将递归字符串/Counter 操作改成 34 位整数数组，并传递剩余张数；在单次搜索中以无冲突的手牌整数编码记录已访问状态，避免重复分割（最优界只会收紧，之前剪掉的分支不会重新有效）。生产 evaluator 保持原样；`runtime(cfg, accelerated=False)` 保留冻结参考实现供一致性核对。`arena.py` 缓存完整可观察状态下的动作描述，跨轮庄复用时重新绑定本局 action_id，不缓存或窥探对手暗手。双阶段共享同一个进程池，跨候选/代际复用有界缓存，避免逐次重启 Windows 工作进程。

分析命令（cProfile 会降低实际吞吐量，应与正常运行分开计时）：

```powershell
.\.venv\Scripts\python.exe -m cProfile -o data/headless/profile.pstats scripts/run_headless_simulation.py --hands 4 --workers 1 --mode ev
.\.venv\Scripts\python.exe -c "import pstats; pstats.Stats('data/headless/profile.pstats').strip_dirs().sort_stats('cumtime').print_stats(25)"
```

## 防退化评估

1. 固定 V0、保守、进攻历史池，三家对手至少包含两种历史策略，避免四家同候选自我对战。
2. 同一代候选和 incumbent 使用完全相同的牌墙、庄位、对手策略，比较累计净得失；统计置信区间以四局块为单位，避免将重复牌墙当成四个独立样本。
3. 与搜索样本完全分离的至少 2000 局完整 EV 检验，同时显著优于 V0 和上一稳定 incumbent 才晋升。默认要求对 V0 每局至少增加 1 净分，使用按预设代数 × 精英上限 Bonferroni 校正的单侧区间，整个运行的误晋升显著性预算为 1%。
4. 未通过检验则回退 incumbent，不输出新 optimized。通过的策略保存到 `--history-dir`，下次运行加入对手池；原 V0 永不覆盖。
5. `best_candidate.json` 只是未晋升搜索候选，不能当成生产优化参数。`--smoke-test` 允许 50 局验证（自动上取整至 52），无条件禁止 optimized 输出与稳定池写入。旧单阶段 `--screen-only` 则跳过验证。禁止用训练胜率宣称提升，也不保证任意未知对手/规则变更后绝不退化。

完整 EV 的信心门槛不能数学上保证永不退化，但能阻止未验证候选覆盖基准。所有部署和线上参数切换均需单独操作。

## 输出与复现

每次实验用新的 `--output` 目录；已有 trials.jsonl 会被拒绝，防止混淆不同运行。保存 run.json、分阶段 trials.jsonl、stage1 精英列表、stage2 基准完整记录、逐精英验证报告/牌局明细、最佳未晋升候选及通过门槛后的 ai_weights_optimized.json。报告记录净分/和牌率/放铳率，第二阶段包含相对 V0 的和牌率及放铳率差值。每个 arena 报告包含随机种子、庄位、四家策略指纹、动作数、每局净分，以及规则内核与离线策略实现的指纹；不同实现的结果拒绝配对。使用相同种子与配置，单进程/多进程结果一致。Windows 必须由脚本 main 入口启动 multiprocessing。

小样本自检：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_offline_ai_tools.py tests/test_pvp_match.py -q
.\.venv\Scripts\python.exe scripts/tune_ai_weights.py --focus-core --generations 2 --population 4 --hands 200 --validation-hands 50 --smoke-test --workers 4 --output data/ai_tuning/my-two-stage-smoke
```

此前本机完整 EV 四进程 52 局耗时 60.97 秒（约 0.85 局/秒）。本轮等价加速后相同 52 局耗时 11.48 秒（约 4.53 局/秒），每局胜者、放铳者、动作数、净分均与原报告相同。基准四家相同策略的结果能更充分利用轮庄缓存；历史池/新候选的吞吐量可能更低。所有计时包含 arena 的工作进程启动，不包含主 Python 启动；双阶段后续评估复用已有进程。这里没有执行 2000 局晋升或生成经验证的优化参数。

最终演练位于 `data/ai_tuning/two-stage-persistent-final/`：2 代、每代 4 候选 × 200 局快速筛选、逐精英 52 局完整 EV，第一代保留 2 名、第二代保留 3 名。共 2000 局代理对战（含 V0）与 364 局完整 EV（含 V0）；快速候选四进程暖池约 192～241 局/秒，完整 EV 精英评估约 2.67～4.27 局/秒。输出 `best_candidate.json`、13 条分阶段试验日志及 5 份精英验证报告，无 optimized 文件。第二代一组平均净分差 +1.69/局，但 99% 近似区间下界为 -4.01，不能认定优于 V0。

额外 8 进程混合 V0/保守/进攻策略 104 局测得 4.62 局/秒（`data/headless/two-stage-mixed-ev8.json`）。尚未稳定达到 5～10 局/秒，避免以增加线程数或代理吞吐量宣称达标。32 项离线/对战内核测试通过；880 个随机手牌（含百搭与副露面子数）向听结果与原 evaluator 全部一致。
