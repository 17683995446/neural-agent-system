<script setup>
import MermaidDiagram from '../components/MermaidDiagram.vue'

const archDiagram = `flowchart TB
    subgraph INPUT["<b>Layer 0: 输入层</b>"]
        REQ["用户需求<br/>User Requirement"]
        DECOMP["需求预分解<br/>decompose_requirement"]
        REQ --> DECOMP
    end

    subgraph CONV["<b>Layer 1: 卷积层</b> — 代码特征提取"]
        TS["Tree-sitter AST<br/>确定性解析"]
        CACHE["ASTCache<br/>LRU+磁盘持久化"]
        CD["ChangeDetector<br/>增量分析"]
        INDEX["CodeStructureIndex<br/>SQLite 6表索引"]
        TS --> CACHE --> CD --> INDEX
    end

    subgraph POOL["<b>Layer 2: 池化层</b> — 信息压缩"]
        HC["HierarchicalCompressor<br/>模块/文件/函数3级"]
        SCORE["AST增强评分<br/>函数名+类名+imports"]
        SORT["相关性排序<br/>Top 50/50/100"]
        HC --> SCORE --> SORT
    end

    subgraph FC1["<b>Layer 3: FC1全局理解层</b>"]
        SCW1["SmartContextWindow<br/>12K字符"]
        CODEX["CodeStructureIndex查询<br/>继承+装饰器+跨文件"]
        PLAN["按SubRequirement逐个规划"]
        MERGE["_merge_modification_lists<br/>区域级冲突检测"]
        SCW1 --> CODEX --> PLAN --> MERGE
    end

    subgraph FC2["<b>Layer 4: FC2代码生成层</b>"]
        DEP["ModificationDependencyGraph<br/>拓扑排序"]
        CONSENSUS["ConsensusEngine<br/>4策略语义等价"]
        APPLY["diff/patch模式<br/>file_state一致性"]
        VERIFY["verify_syntax<br/>compile+tree-sitter+pytest"]
        ROLLBACK["_rollback_failed_files<br/>失败回滚"]
        DEP --> CONSENSUS --> APPLY --> VERIFY --> ROLLBACK
    end

    subgraph FC3["<b>Layer 5: FC3测试生成层</b>"]
        SCW2["SmartContextWindow<br/>token感知截断"]
        GEN["测试代码生成"]
        SCW2 --> GEN
    end

    subgraph OUTPUT["<b>Layer 6: 输出层</b>"]
        RESULT["修改结果+测试+验证"]
    end

    subgraph MEMORY["<b>双记忆体系</b>"]
        STM["短期记忆<br/>Redis: 消息/信任/上下文"]
        LTM["长期记忆<br/>Milvus: 经验向量检索"]
    end

    subgraph TRUST["<b>信任度管理</b>"]
        TM["TrustManager<br/>矩阵[0,2]"]
        BP["反向传播<br/>_persist_trust_updates"]
        RC["RewardCalculator<br/>[-1,1]裁剪"]
        TM --> BP --> RC
    end

    subgraph INFRA["<b>基础设施</b>"]
        RL["LLMRateLimiter<br/>信号量+令牌桶"]
        CB["CircuitBreaker<br/>CLOSED→OPEN→HALF_OPEN"]
        LCACHE["LLMResponseCache<br/>TTL+LRU"]
        SP["SafePickle<br/>HMAC-SHA256"]
    end

    DECOMP --> TS
    INDEX --> SCORE
    SORT --> SCW1
    MERGE --> DEP
    ROLLBACK --> SCW2
    GEN --> RESULT
    RESULT --> BP
    TM -.-> FC1
    TM -.-> FC2
    STM -.-> POOL
    LTM -.-> FC1
    RL --> CB --> LCACHE
    SP --> CACHE

    style INPUT fill:#0e1a2b,stroke:#06b6d4,stroke-width:2px
    style CONV fill:#0e0e2b,stroke:#6366f1,stroke-width:2px
    style POOL fill:#1a0e2b,stroke:#8b5cf6,stroke-width:2px
    style FC1 fill:#1a1a0e,stroke:#f59e0b,stroke-width:2px
    style FC2 fill:#0e1a1a,stroke:#10b981,stroke-width:2px
    style FC3 fill:#1a0e1a,stroke:#ec4899,stroke-width:2px
    style OUTPUT fill:#1a0e0e,stroke:#ef4444,stroke-width:2px
    style MEMORY fill:#0e1a1a,stroke:#06b6d4,stroke-width:1px,stroke-dasharray: 5 5
    style TRUST fill:#1a1a0e,stroke:#f59e0b,stroke-width:1px,stroke-dasharray: 5 5
    style INFRA fill:#1a0e0e,stroke:#ef4444,stroke-width:1px,stroke-dasharray: 5 5`
</script>

<template>
  <div>
    <div class="page-header">
      <el-icon :size="24" color="var(--accent-primary)"><Share /></el-icon>
      <h2>7层神经网络架构图</h2>
      <el-tag type="info" size="small" style="margin-left:auto;">Tree-sitter优先 + LLM补充</el-tag>
    </div>
    <MermaidDiagram :definition="archDiagram" />
  </div>
</template>
