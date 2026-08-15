# Codeflaws Benchmark

## 1. 选择原因

Codeflaws 收集了在线评测中的真实 C 程序缺陷，案例同时提供 buggy submission、accepted submission、修复测试、held-out 验证测试和缺陷分类。它适合先验证 CodeDoctor 的数据转换、Fault Localization、修复和独立验证链路，且无需自行大规模爬取 Codeforces。

## 2. 官方来源

- 官方网站：<https://codeflaws.github.io/>
- 官方归档：<https://www.comp.nus.edu.sg/~release/codeflaws/codeflaws.tar.gz>
- 官方仓库：<https://github.com/codeflaws/codeflaws>
- 官方缺陷分类表：<https://codeflaws.github.io/defect-table.html>

本地归档实测为 `265695532` bytes，SHA-256 为 `2673fc16fa05590c5c1171f5b633594713ae9207346a3d0ba4c4d8b2eea82b11`。下载信息和 UTC 时间保存在 `benchmark/datasets/codeflaws/metadata/download.json`。

## 3. 原始目录

每个原始 case 目录通常包含：

```text
<contest>-<problem>-bug-<buggy-id>-<reference-id>/
├── <contest>-<problem>-<buggy-id>.c
├── <contest>-<problem>-<reference-id>.c
├── Makefile
├── input-pos* / input-neg*
├── output-pos* / output-neg*
├── heldout-input-pos*
├── heldout-output-pos*
├── test-genprog.sh
└── test-valid.sh
```

完整数据位于 `benchmark/datasets/codeflaws/raw/`，归档位于 `downloads/`，两者均被 `.gitignore` 排除。当前实际解压规模约 2.9 GB、403843 个文件、3904 个 case 目录和 7808 个 C 源文件。

## 4. CodeDoctor 转换

`prepare_codeflaws.py` 将原始结构转换为 dataset-independent `BenchmarkCase`，写入 `metadata/manifest.jsonl`。路径均相对于项目根目录，不包含 `/home/...` 等机器路径。

测试集合以官方 `test-genprog.sh` 和 `test-valid.sh` 的 `case ... run_test` 映射为准，而不是收集目录中所有同前缀文件。部分目录还保留未被该 case 官方脚本引用的额外生成文件；将它们全部纳入会错误判定 accepted program 失败。

主要接口为：

```python
from benchmark import load_case

case = load_case("18-A-bug-15987401-15987453")
buggy_source = case.get_buggy_source()
repair_tests = case.get_repair_tests()
validation_tests = case.get_validation_tests()

# 仅供数据验证和最终评估
reference_source = case.get_reference_source(evaluation_only=True)
```

## 5. Repair 与 Validation

- `repair_tests` 来自 `test-genprog.sh`，未来允许修复系统用于执行反馈。
- `validation_tests` 来自 held-out 文件及 `test-valid.sh`，只用于最终 patch 验证，不能用于反复拟合补丁。

实际运行沿用官方脚本的输出规则：删除程序输出中的空行；在原脚本指定时移除行首空白；比较时忽略行尾空白。每个测试默认 5 秒超时。

## 6. Pilot 抽样

Pilot 使用固定随机种子 `20260815`。先按 `defect_class` 分组，在组内确定性打乱，再以类别 round-robin 顺序取候选，因此不是简单选择目录前 50 个。

只有同时满足以下条件的 case 才写入 `metadata/pilot.jsonl`：

1. buggy program 编译成功；
2. reference program 编译成功；
3. reference 通过全部 repair 和 validation tests；
4. buggy 至少失败一个正式测试；
5. 静态测试数据完整。

本次实际测试 55 个动态候选，得到 50 个 pilot case，覆盖 38 个 defect class。所有未准入案例写入 `excluded_cases.jsonl`，完整动态结果写入 `pilot_results.jsonl`。

## 7. 数据泄漏边界

`BenchmarkCase.repair_time_view()` 不包含 reference program 和 validation tests。`get_reference_source()` 默认拒绝读取，只有显式传入 `evaluation_only=True` 才开放。未来 Repair Agent 只能接收 buggy source、repair tests 和允许的 metadata；accepted source 不能进入 prompt、检索上下文或中间执行反馈。

Git 中的三案例 sample 包含 reference 文件用于展示完整数据模型，但同样标记为 `evaluation_only`，不能作为修复输入。

## 8. 完整性与执行验证

静态校验检查 source、Makefile、成对 input/output、唯一 case id、相对路径边界和可读性。当前 3904 个解析案例中，3884 个通过，20 个因官方测试映射不完整而无效。

动态验证在 `codedoctor-cpp-sandbox` 中执行，并保留 Phase 2 的网络、256 MB 内存、1 CPU、64 PID、capability、只读根文件系统等限制。编译使用各 case 的原始 Makefile；该 Makefile 为 `gcc -std=c99` 及 Codeflaws 链接参数，不能强行替换为通用 Runner 的 `g++ -std=c++17`。编译超时为 20 秒。

实际报告由 `generate_codeflaws_report.py` 从 validation、pilot、pilot results 和 exclusions 重新计算，见 `benchmark/reports/codeflaws_pilot_report.md`。

## 9. 当前数据问题

- 官方分类网页解析到 4085 行，而下载归档实际只有 3904 个 case；manifest 只以归档中真实目录为准。
- 20 个 case 缺少完整测试集合，静态排除。
- 55 个动态候选中，2 个 reference 未通过 repair suite，2 个未通过 validation suite，1 个 buggy 通过全部正式测试；这些案例均保留原因，没有静默删除。
- 原始目录中可能存在不属于官方脚本映射的额外 input/output，转换器会忽略它们。
- 输出比较实现了当前脚本的主要 `sed`/`diff` 语义，但尚未逐版本复刻所有 shell 工具边缘行为。

## 10. 后续扩展

后续接入 Defects4C 时应新增独立 adapter，将 Java 项目、触发测试和相关测试映射到同一 `BenchmarkCase` 概念；不应让 Codeflaws 路径或 C Makefile 规则泄漏到统一模型。扩展前应先稳定 pilot 的 Fault Localization 与 patch validation 协议，本轮未下载或处理 Defects4C。

## 常用命令

```bash
python3 -m benchmark.scripts.download_codeflaws
python3 -m benchmark.scripts.prepare_codeflaws
python3 -m benchmark.scripts.validate_codeflaws
python3 -m benchmark.scripts.build_codeflaws_pilot --target-size 50 --seed 20260815
python3 -m benchmark.scripts.generate_codeflaws_report
python3 -m benchmark.scripts.export_codeflaws_sample
```
