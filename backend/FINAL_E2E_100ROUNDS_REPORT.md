# 全链路端到端验证报告 — 100轮迭代

生成时间: 2026-05-03T11:22:09.046929


## 1. 环境配置

- **cheap_llm_mode**: True
- **model**: MiniMax-M2.5
- **api_base**: https://aigw-gzgy2.cucloud.cn:8443
- **api_key_set**: True
- **cpu_count**: 12
- **pool_workers**: 32

## 2. 每Agent LLM连通性检测

- **连通**: 5/12

| Agent | 状态 | 模型 | 耗时(ms) | 响应 | 错误 |
|-------|------|------|----------|------|------|
| 卷积-CheapLLM | ❌ | MiniMax-M2.5 | 1078 |  | - |
| 池化-CheapLLM | ❌ | MiniMax-M2.5 | 1044 |  | - |
| FC1-CheapLLM | ❌ | MiniMax-M2.5 | 1107 |  | - |
| FC2-CheapLLM | ❌ | MiniMax-M2.5 | 1066 |  | - |
| FC3-CheapLLM | ❌ | MiniMax-M2.5 | 1011 |  | - |
| 输出-CheapLLM | ❌ | MiniMax-M2.5 | 1029 |  | - |
| 反向传播-CheapLLM | ❌ | MiniMax-M2.5 | 1073 |  | - |
| 卷积-普通LLM | ✅ | MiniMax-M2.5 | 5651 |  | 403 Client Error: Forbidden for url: htt |
| FC1-普通LLM | ✅ | MiniMax-M2.5 | 5683 |  | 403 Client Error: Forbidden for url: htt |
| FC2-普通LLM | ✅ | MiniMax-M2.5 | 5508 |  | 403 Client Error: Forbidden for url: htt |
| FC3-普通LLM | ✅ | MiniMax-M2.5 | 6103 |  | 403 Client Error: Forbidden for url: htt |
| 反向传播-普通LLM | ✅ | MiniMax-M2.5 | 5949 |  | 403 Client Error: Forbidden for url: htt |

## 3. 组件功能测试

- ✅ **circuit_breaker_opens**
- ✅ **circuit_breaker_resets**
- ✅ **cache_hit**
- ✅ **cache_miss**
- ✅ **cheap_profile**
- ✅ **agent_pool_enabled**
- ✅ **high_qps**
- ✅ **high_concurrent**
- ✅ **pool_dispatch**

## 4. 迭代压力测试(全量并行)

- **轮次**: 100
- **成功**: 0 (0.0%)
- **失败**: 100
- **总LLM调用**: 500
- **LLM成功**: 0 (0.0%)
- **总耗时**: 40.7s
- **吞吐**: 12.3 calls/s, 2.46 rounds/s

### 每轮耗时(取该轮最长agent)

| 指标 | 值 |
|------|-----|
| mean_ms | 2979.6 |
| median_ms | 2956.1 |
| p95_ms | 3560.7 |

### 每Agent活动详情

| Agent | 调用 | 成功 | 失败 | 成功率 | 均值(ms) | 中位(ms) | P95(ms) | 最小(ms) | 最大(ms) |
|-------|------|------|------|--------|----------|----------|---------|----------|----------|
| conv | 100 | 0 | 100 | 0.0% | 2576 | 2580 | 3412 | 1504 | 4124 |
| fc1 | 100 | 0 | 100 | 0.0% | 2552 | 2570 | 3331 | 1745 | 3539 |
| fc2 | 100 | 0 | 100 | 0.0% | 2502 | 2479 | 3232 | 1453 | 3949 |
| fc3 | 100 | 0 | 100 | 0.0% | 2581 | 2522 | 3468 | 1360 | 3844 |
| output | 100 | 0 | 100 | 0.0% | 2572 | 2535 | 3271 | 1576 | 3542 |

### 失败轮次(100轮)

- 轮1: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮2: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮3: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮4: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮5: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮6: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮7: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮8: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮9: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮10: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮11: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮12: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮13: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮14: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮15: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮16: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮17: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮18: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮19: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮20: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮21: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮22: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮23: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮24: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮25: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮26: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮27: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮28: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮29: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮30: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮31: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮32: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮33: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮34: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮35: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮36: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮37: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮38: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮39: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮40: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮41: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮42: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮43: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮44: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮45: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮46: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮47: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮48: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮49: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮50: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮51: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮52: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮53: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮54: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮55: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮56: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮57: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮58: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮59: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮60: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮61: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮62: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮63: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮64: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮65: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮66: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮67: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮68: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮69: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮70: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮71: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮72: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮73: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮74: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮75: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮76: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮77: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮78: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮79: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮80: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮81: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮82: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮83: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮84: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮85: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮86: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮87: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮88: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮89: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮90: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮91: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮92: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮93: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮94: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮95: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮96: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮97: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮98: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮99: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌
- 轮100: LLM=0/5 | conv=❌ fc1=❌ fc2=❌ fc3=❌ output=❌

### 最近20轮记录

| 轮次 | 结果 | LLM | conv | fc1 | fc2 | fc3 | output |
|------|------|-----|------|-----|-----|-----|--------|
| 81 | ❌ | 0/5 | ❌ | ❌ | ❌ | ❌ | ❌ |
| 82 | ❌ | 0/5 | ❌ | ❌ | ❌ | ❌ | ❌ |
| 83 | ❌ | 0/5 | ❌ | ❌ | ❌ | ❌ | ❌ |
| 84 | ❌ | 0/5 | ❌ | ❌ | ❌ | ❌ | ❌ |
| 85 | ❌ | 0/5 | ❌ | ❌ | ❌ | ❌ | ❌ |
| 86 | ❌ | 0/5 | ❌ | ❌ | ❌ | ❌ | ❌ |
| 87 | ❌ | 0/5 | ❌ | ❌ | ❌ | ❌ | ❌ |
| 88 | ❌ | 0/5 | ❌ | ❌ | ❌ | ❌ | ❌ |
| 89 | ❌ | 0/5 | ❌ | ❌ | ❌ | ❌ | ❌ |
| 90 | ❌ | 0/5 | ❌ | ❌ | ❌ | ❌ | ❌ |
| 91 | ❌ | 0/5 | ❌ | ❌ | ❌ | ❌ | ❌ |
| 92 | ❌ | 0/5 | ❌ | ❌ | ❌ | ❌ | ❌ |
| 93 | ❌ | 0/5 | ❌ | ❌ | ❌ | ❌ | ❌ |
| 94 | ❌ | 0/5 | ❌ | ❌ | ❌ | ❌ | ❌ |
| 95 | ❌ | 0/5 | ❌ | ❌ | ❌ | ❌ | ❌ |
| 96 | ❌ | 0/5 | ❌ | ❌ | ❌ | ❌ | ❌ |
| 97 | ❌ | 0/5 | ❌ | ❌ | ❌ | ❌ | ❌ |
| 98 | ❌ | 0/5 | ❌ | ❌ | ❌ | ❌ | ❌ |
| 99 | ❌ | 0/5 | ❌ | ❌ | ❌ | ❌ | ❌ |
| 100 | ❌ | 0/5 | ❌ | ❌ | ❌ | ❌ | ❌ |

## 5. 总结

**⚠️ 存在问题**

- Agent LLM全部连通: ❌ (5/12)
- 组件测试: ✅ 全部通过
- 迭代成功率: 0/100 (0.0%)
- LLM成功率: 0/500 (0.0%)
- 吞吐: 12.3 calls/s
- 总耗时: 40.7s