# V2 副露专项实验

基线：`backend/tools/policy_pool/baseline_v1.json` 与已验证的
`backend/app/config/ai_weights_optimized.json` 指纹必须一致。所有 165 项基础权重冻结，
包括 V1 已调优的 12 项核心权重。历史 V0/V1 的冻结源码和原公式均保留。

## 统一评分

实验实现位于 `backend/app/core/claim_v2.py`，只安装进离线候选的私有模块图。
PASS、CHI、PONG、各类 KONG 共享 `ClaimEvaluator.waiting()`：

- 听牌：Σ(公开信息估算的剩余和牌张数 × 实际计分收益) / 8。
- 非听牌：统一采用 V1 进张质量、手牌结构、役牌潜力、客风占位及向听惩罚。
- 胡数由现有规则内核计算；没有 PASS 独享的额外硬胡折现。
- 副露后的出牌仍由冻结的 V1 舍牌策略选择；比较动作时重新计算待摸状态值，
  不把“吃出孤张再切掉”的结构奖励重复带入副露收益。真实舍牌风险独立扣除。
- 过牌保留即将轮到的摸牌机会，已听牌也计算该机会价值。

这些是统一量纲的启发式分值，不是已校准的真实净得分期望；向听与结构近似仍需实战检验。

## 专项护栏

GM-86F219：V1 吃 135.2 / 过 99。V2 两种等价待摸手牌基础值均为 198，
吃牌不再凭不同分母获利。对原样打回、向听倒退，以及听口宽度与收益不增加的
冗余吃牌，最终分数严格小于过牌，不能通过调低罚分绕过。

规则未定义额外“门清役”；吃碰也不会自动失去硬胡。测试使用实际计分器验证
闭手顺子搬成明顺无收益时应过牌，不虚构门清役惩罚。

杠牌枚举所有公开信息下尚可能出现的补张；补张即和时立即计分，不强制弃牌。
胡分已包含杠面子时不重复计奖；取消旧策略杠相对碰保底与强制补杠，补杠计入公开抢杠风险。

## 搜索与验证

```powershell
cd F:\mahjong\backend
.\.venv\Scripts\python.exe scripts/tune_claim_weights.py --generations 2 --population 6 --hands 500 --validation-hands 2000 --validation-seed 20311000 --workers 8 --output data/ai_tuning/v2-claims-formal
```

初筛用 `claim-explore`：普通舍牌使用快速代理，吃碰杠使用真实决策，确保 5 项副露参数
确实进入评分。旧 `explore` 不读取这些参数，不能用来搜索 V2。

每轮 6 组（含父代）×500 局，2 轮。各轮用相同牌墙的 V1 作配对参照；最终仅锁定
最后一轮最优候选，在独立新牌墙上与 V1 各跑 2000 局完整 EV。
对手每局至少包含 V0、V1 两种历史策略；候选物理座位每墙轮换，每墙四方轮庄。
统计按四局牌墙块聚类，单侧 95% 常态近似下界必须 >0，且专项测试通过才晋升。
验证集不用于继续搜索或反复择优，避免再次引入多重比较选择偏差。

进度每约15秒写日志和完整牌墙块 checkpoint。可原命令加 `--resume` 恢复；
参数、基线或实现发生变化时拒绝混用旧 checkpoint。进程池在 finally 中回收。

通过才生成 `backend/app/config/ai_weights_v2.json`，并输出
`docs/ai_weights_v2_claims.md`。未通过仅保留 `locked_candidate.json`。
V2 文件包含 `policy_version` 与独立 `claim_weights`；现有生产加载器仍加载 V1，
不会自动把未验证的实验机制用于手机或线上服务。没有部署或 git push。
