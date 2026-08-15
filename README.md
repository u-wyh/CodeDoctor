# CodeDoctor

CodeDoctor 已具备 C/C++ Runner、Docker 沙箱、Codeflaws Benchmark，以及基于 gcov line/branch evidence 的 Spectrum-Based Fault Localization。当前可对 50-case Pilot 的 repair tests 逐测试隔离采集覆盖，并生成原始 Ochiai 与保守 branch tie-breaking 的 tie-aware 对比。

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

Phase 7 使用 `repair-v2` 固定比较单次修复的三组输入。当前 Codeflaws 快照没有可靠的逐题题面，因此 A/B/C 都使用完全相同的 buggy source 与 repair-test 输入/期望输出作为共同 repair-time oracle；B 仅追加冻结的 FL-v1 Top-10，C 再追加 verdict、实际 stdout/stderr、exit code 和 timeout 等运行观察。Repair Pilot 的选择不使用 FL 命中表现，无可靠 FL 位置的样例仍保留。先构建与两个 FL 数据集都不重叠的 Repair Pilot，并生成 FL 输入：

```bash
python3 benchmark/scripts/build_repair_pilot.py --force
python3 benchmark/scripts/run_repair_pilot_fl.py --force
```

使用 OpenAI-compatible provider 时，凭据只从环境变量读取：

```bash
export CODEDOCTOR_API_KEY='...'
export CODEDOCTOR_BASE_URL='https://provider.example/v1'
export CODEDOCTOR_MODEL='fixed-model-version'
python3 benchmark/scripts/run_repair_ablation.py --limit 3 --resume
```

支持 `--cases`、`--group`、`--model`、`--limit` 和 `--resume`。真实在线 smoke 最多运行 3 cases × 3 groups（9 次调用）；完整 50-case A/B/C 运行前必须人工审查 prompts 和 smoke artifacts，并生成调用量、token、计费与泄漏边界预实验报告：

```bash
python3 benchmark/scripts/estimate_repair_experiment.py --manual-inspection passed
```

超过 9 次在线调用会被 CLI 拒绝。只有在预实验报告完成且用户明确批准后，才可使用 `--confirm-bulk`；该标志本身不代表自动获得批准。生成结构化统计和消融报告：

```bash
python3 benchmark/scripts/generate_repair_ablation_report.py
```

原始 prompts、模型响应和 patches 位于 `benchmark/artifacts/repair/`，默认不进入 Git；预实验报告见 [`benchmark/reports/llm_repair_pre_experiment.md`](benchmark/reports/llm_repair_pre_experiment.md)，消融报告见 [`benchmark/reports/llm_repair_evidence_ablation.md`](benchmark/reports/llm_repair_evidence_ablation.md)。

## 当前边界

Docker 后端显著缩小了程序权限，但仍不等同于针对敌意代码的完整强隔离。当前没有限制输出大小和磁盘写入量，没有自定义 seccomp/AppArmor 策略，也没有使用 gVisor、Kata Containers 或独立虚拟机。静态/动态分析工具将在后续阶段加入。
