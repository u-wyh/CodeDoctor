# CodeDoctor

CodeDoctor is an **LLM-based Automated Program Repair Framework** for C/C++ programs. It combines fault localization, evidence-bounded LLM repair, controlled execution feedback, and progressively stronger patch validation on the Codeflaws benchmark.

> The core experimental pipeline (Phases 4-9) is frozen. The repository preserves the formal protocols, manifests, result tables, and reproducibility hashes; lightweight checks do not call an LLM API or rerun the expensive formal experiments.

## 核心模块

- **Fault Localization**：基于 gcov line/branch evidence 的 SBFL 与冻结的 FL-v1 tie-breaking。
- **LLM Repair**：严格区分 Base、FL-v1 与 Runtime Evidence 的单次修复消融。
- **Execution Feedback**：使用同一 first patch 的 Retry/Feedback 配对比较。
- **Patch Validation**：V1 repair tests、V2 hidden validation、V3 sanitizer 与 V4 differential validation ladder。

## 环境要求

- Linux
- Python 3.10 或更高版本（核心控制与测试仅使用 Python 标准库）
- Docker daemon（运行默认 sandbox 与 sanitizer integration tests）
- `g++`，支持 C++17（仅 local backend 或直接编译示例时需要）

构建专用镜像后即可运行 Docker smoke；不需要数据库、前后端服务或 LLM credential。

## 最终实验结果

- [Final Research Summary](benchmark/reports/final_research_summary.md)
- [Final Experiment Registry](benchmark/metadata/final/final_experiment_registry.json)
- [Reproducibility Registry](benchmark/metadata/final/reproducibility_registry.json)
- [Final Tables](benchmark/reports/final_tables/)
- [Development Log](docs/DEVELOPMENT_LOG.md)

## Fresh Clone 轻量复现

以下命令只读取已冻结 metadata 和小型 fixtures，不重新运行 Phase 6-9 正式实验，也不会发起 LLM 调用：

```bash
python3 -m unittest final_consolidation.tests.test_consolidation
python3 -m unittest benchmark.tests.test_models
python3 -m unittest repair.tests.test_pipeline
python3 -m unittest validation_phase9.tests.test_pipeline
```

Docker sandbox smoke：

```bash
docker build --tag codedoctor-cpp-sandbox --file sandbox/docker/Dockerfile sandbox/docker
python3 -m sandbox.runner.main examples/sum/main.cpp examples/sum/input.txt
```

完整原始 Codeflaws dataset、模型 raw responses 和大型运行 intermediates 默认不随 fresh clone 分发；正式结果通过 tracked manifests、hashes、reports 和 final tables 固定。不要把 formal experiment runner 当作轻量复现命令。

## 构建沙箱镜像

确保 Docker daemon 正在运行，然后在项目根目录执行：

```bash
docker build \
  --tag codedoctor-cpp-sandbox \
  --file sandbox/docker/Dockerfile \
  sandbox/docker
```

## 运行方式

在项目根目录执行：

```bash
python3 -m sandbox.runner.main examples/sum/main.cpp examples/sum/input.txt
```

默认使用 `docker` 后端。需要调试原有宿主执行逻辑时，可显式指定：

```bash
python3 -m sandbox.runner.main \
  examples/sum/main.cpp \
  examples/sum/input.txt \
  --backend local
```

动态分析模式使用独立 Sanitizer 编译配置，不影响普通运行：

```bash
python3 -m sandbox.runner.main \
  examples/asan_heap_overflow/main.cpp \
  examples/asan_heap_overflow/input.txt \
  --analysis sanitizer
```

分析结果在原 Runner JSON 基础上增加 `analysis.evidence[]`。每条 Evidence 包含分析器、缺陷分类、源码位置、函数、调用栈、内存访问以及完整原始报告。

默认运行超时为 5 秒，可通过 `--timeout` 修改：

```bash
python3 -m sandbox.runner.main \
  examples/timeout/main.cpp \
  examples/timeout/input.txt \
  --timeout 1
```

也可以直接运行入口文件：

```bash
python3 sandbox/runner/main.py examples/hello_world/main.cpp examples/hello_world/input.txt
```

Runner 会输出以下状态之一：

- `success`
- `compile_error`
- `runtime_error`
- `time_limit_exceeded`
- `internal_error`

## 测试

```bash
python3 -m unittest discover -s sandbox/tests -v
```

重新采集 50-case line/branch coverage 并生成 Phase 5 报告：

```bash
python3 benchmark/scripts/run_fault_localization_pilot.py --force
python3 benchmark/scripts/generate_branch_fault_localization_report.py
```

报告输出到 `benchmark/reports/fault_localization_branch_report.md`，结构化指标输出到 `benchmark/results/fault_localization/branch_evaluation.json`。

测试覆盖原 Runner 和 Docker 回归、Parser fixture，以及正常程序、heap/stack buffer overflow、use-after-free、double-free、memory leak、整数溢出、除零、非法移位和空指针访问的真实 Docker 集成分析。

动态分析的模型与研究边界详见 [`docs/analysis/dynamic-analysis.md`](docs/analysis/dynamic-analysis.md)。

## Codeflaws Benchmark

从官方数据生成 manifest、校验完整性并构建可复现 pilot：

```bash
python3 -m benchmark.scripts.download_codeflaws
python3 -m benchmark.scripts.prepare_codeflaws
python3 -m benchmark.scripts.validate_codeflaws
python3 -m benchmark.scripts.build_codeflaws_pilot --target-size 50
python3 -m benchmark.scripts.generate_codeflaws_report
```

完整原始数据和下载归档默认不进入 Git。统一模型可通过 `benchmark.load_case(case_id)` 使用；reference source 必须显式声明 `evaluation_only=True` 才能读取。数据来源、转换语义和当前统计详见 [`docs/benchmark/codeflaws.md`](docs/benchmark/codeflaws.md)。

## Docker 限制

每次编译和运行都会创建独立容器，并应用以下限制：

- 禁用网络
- 内存与内存加交换空间总量限制为 256MB
- CPU 限制为 1 核
- 进程数限制为 64
- 删除全部 Linux capabilities
- 启用 `no-new-privileges` 和只读容器根文件系统
- 仅将本次临时工作目录挂载到 `/workspace`
- 容器结束或超时后强制删除

## Fault Localization

先冻结实验环境，再采集覆盖和生成真实报告：

```bash
python3 -m benchmark.scripts.freeze_experiment_environment
python3 -m benchmark.scripts.run_fault_localization_pilot
python3 -m benchmark.scripts.generate_fault_localization_report
```

算法调整后可以复用已经保存的逐测试 coverage，不重新执行程序：

```bash
python3 -m benchmark.scripts.run_fault_localization_pilot --reuse-coverage
```

理论、数据流、ground truth 规则和指标定义见 [`docs/fault_localization/sbfl.md`](docs/fault_localization/sbfl.md)，实际 Pilot 结果见 [`benchmark/reports/fault_localization_pilot_report.md`](benchmark/reports/fault_localization_pilot_report.md)。

## LLM Repair Evidence Ablation

本节保留冻结 Phase 7 协议及历史执行入口，仅用于研究追溯；fresh-clone reproduction 不需要 credential，也不应重新发起正式调用。

Phase 7 使用 `repair-v2` 固定比较单次修复的三组输入。当前 Codeflaws 快照没有可靠的逐题题面，因此 A/B/C 都使用完全相同的 buggy source 与 repair-test 输入/期望输出作为共同 repair-time oracle；B 仅追加冻结的 FL-v1 Top-10，C 再追加 verdict、实际 stdout/stderr、exit code 和 timeout 等运行观察。Repair Pilot 的选择不使用 FL 命中表现，无可靠 FL 位置的样例仍保留。先构建与两个 FL 数据集都不重叠的 Repair Pilot，并生成 FL 输入：

```bash
python3 benchmark/scripts/build_repair_pilot.py --force
python3 benchmark/scripts/run_repair_pilot_fl.py --force
```

Phase 7 的候选 provider 已冻结为 DeepSeek Official API，继续使用 OpenAI-compatible Chat Completions。初始 `deepseek-v4-pro`、thinking high、max tokens 8192 的三次工程 smoke 全部耗尽 reasoning budget 且没有 final content，因此在正式实验开始前被标记为 superseded。最终候选配置固定为 `deepseek-v4-flash`、thinking enabled、reasoning effort low、stream false、max tokens 16384；这次预实验切换用于解决 output-budget compatibility failure，不是根据正式 repair 结果调参。Thinking mode 不发送 temperature，也不声称 temperature determinism。凭据优先读取 `DEEPSEEK_API_KEY`，再读取 generic fallback `CODEDOCTOR_API_KEY`，不会使用 `OPENAI_API_KEY`：

```bash
export DEEPSEEK_API_KEY='...'
python3 benchmark/scripts/run_repair_ablation.py \
  --provider deepseek --limit 1 --resume
```

真实 DeepSeek smoke 使用冻结 Repair Pilot manifest 的第一个 case，最多 1 case × 3 groups（3 次调用），transport retry 为 0。工程 smoke 会标记为 `pre_experiment_smoke` 并排除在正式 Evidence Ablation 指标之外；旧 Pro 与当前 Flash artifact 通过配置和 cache key 隔离。缺少凭据、配置漂移或 leakage audit 失败时不得联网。完整 50-case A/B/C 运行前必须人工审查 prompts 和 smoke artifacts，并生成调用量、真实 token usage、计费与泄漏边界预实验报告：

```bash
python3 benchmark/scripts/freeze_repair_runtime_evidence.py
python3 benchmark/scripts/audit_repair_prompt_reproducibility.py
python3 benchmark/scripts/estimate_repair_experiment.py --manual-inspection passed
```

`runtime-evidence-v1` 在正式 LLM 调用前按 Repair Pilot 顺序对每个 repair test 仅执行一次 buggy program，并冻结未归一化的 stdout、stderr、exit code、timeout 和 verdict。Manifest 绑定 50-case Pilot、repair-v2、测试顺序、Docker 配置以及每份 snapshot hash。正式 Group C 只加载并验证该 snapshot；缺失、损坏或 hash/protocol/Pilot 不匹配时 fail closed，不会现场重新执行 buggy program。A/B 不获得 runtime evidence，expected output 仍只属于三组共享的 repair-time oracle。

超过 3 次 DeepSeek 在线调用会被 CLI 拒绝。只有在真实 smoke、预实验报告和成本核验完成且用户另行明确批准后，才可使用 `--confirm-bulk`；该标志本身不代表自动获得批准。本轮没有批准 150-call bulk。生成结构化统计和消融报告：

```bash
python3 benchmark/scripts/generate_repair_ablation_report.py
```

原始 prompts、模型响应和 patches 位于 `benchmark/artifacts/repair/`，默认不进入 Git；预实验报告见 [`benchmark/reports/llm_repair_pre_experiment.md`](benchmark/reports/llm_repair_pre_experiment.md)，消融报告见 [`benchmark/reports/llm_repair_evidence_ablation.md`](benchmark/reports/llm_repair_evidence_ablation.md)。

## 当前边界

Docker 后端显著缩小了程序权限，但仍不等同于针对敌意代码的完整强隔离。当前没有限制输出大小和磁盘写入量，没有自定义 seccomp/AppArmor 策略，也没有使用 gVisor、Kata Containers 或独立虚拟机。CodeDoctor 的核心实验链路已经冻结，这些边界不在本轮扩展。
