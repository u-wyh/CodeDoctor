# Spectrum-Based Fault Localization

## 1. SBFL 是什么

Spectrum-Based Fault Localization（SBFL）使用测试结果与程序执行覆盖之间的统计相关性，对可执行源码行进行可疑度排序。它回答的是“哪些行的执行模式最接近失败测试”，而不是证明某一行在语义上必然是根因。

CodeDoctor Phase 4 的输入严格限于：

```text
buggy source + repair tests + expected outputs
```

validation tests 与 reference source 不进入覆盖、spectrum、公式或排名。reference 只在排名生成后用于 evaluation-only ground truth。

## 2. 为什么覆盖可以帮助定位

若某行频繁被失败测试执行、很少被成功测试执行，它与失败行为具有较强统计相关性。反之，一行在成功与失败测试中都普遍执行，通常只是公共路径，区分能力较弱。

这种推断依赖测试多样性。若所有测试覆盖完全相同，任何公式都无法凭相同 spectrum 区分这些行。若没有成功测试，失败覆盖仍可计算，但缺少对照，Tarantula 等方法会产生大量同分。

## 3. Spectrum 四元组

对于每个可执行行 `l`：

- `ef`：执行 `l` 的失败测试数量。
- `ep`：执行 `l` 的成功测试数量。
- `nf`：没有执行 `l` 的失败测试数量。
- `np`：没有执行 `l` 的成功测试数量。

它们满足：

```text
ef + nf = total_failed
ep + np = total_passed
```

Coverage Matrix 保存逐测试布尔覆盖，Spectrum Builder 是独立纯函数，只从矩阵计算四元组。公式层不会读取测试文件、源码差异或 reference。

## 4. Ochiai

```text
Ochiai(l) = ef / sqrt((ef + nf) * (ef + ep))
```

Ochiai 同时考虑失败测试覆盖比例和覆盖该行的测试中失败测试所占程度。当分母为 0 时，CodeDoctor 定义结果为 0。

## 5. Tarantula

```text
failed_rate = ef / total_failed
passed_rate = ep / total_passed

Tarantula(l) = failed_rate / (failed_rate + passed_rate)
```

若某一测试类别总数为 0，对应 rate 定义为 0；若两个 rate 之和为 0，结果为 0。没有成功测试时，所有被任意失败测试覆盖且 failed rate 非零的行会得到 1，这一边界有数学定义，但区分能力很弱。

## 6. DStar2

```text
DStar2(l) = ef^2 / (ep + nf)
```

DStar2 对 `ef` 使用平方，更强烈奖励被失败测试覆盖的行。当 `ep + nf = 0` 且 `ef > 0` 时，理论结果为正无穷。为保持严格 JSON 数值格式，CodeDoctor 使用 IEEE-754 最大有限值 `sys.float_info.max` 作为正无穷排序哨兵；若 `ef` 同时为 0，则结果为 0。

## 7. 三种方法的直觉差异

- Ochiai 的归一化较平衡，常用于缺陷定位基线。
- Tarantula 显式比较失败与成功覆盖率；没有成功测试时退化最明显。
- DStar2 更偏好高 `ef`、低 `ep + nf` 的行，分数尺度可能远大于前两者。

在当前 Pilot 中，测试数量较少且路径高度相关，三者经常产生相同排序桶。公式不同并不能创造 coverage 中不存在的信息。

## 8. Coverage Matrix 构建

Coverage 编译保留 Codeflaws Makefile 的原始 CFLAGS/LDFLAGS，并通过命令行设置：

```text
CC="gcc -g -O0 --coverage"
```

这使编译命令同时含有原 `-std=c99`、`-fno-*` 参数和 gcov instrumentation。没有使用 ASan、UBSan 或 validation tests。

每个 repair test 的执行步骤为：

1. 从干净编译产物复制 source、binary 和 `.gcno` 到新的临时目录。
2. 创建新的受限 Docker 容器，只挂载该测试目录。
3. 以 5 秒超时运行 buggy program，并用 benchmark 的 expected-output 规则判定 PASS/FAIL。
4. 在同一测试目录运行 `gcov --json-format`。
5. 从 gzip JSON 读取所有 executable lines 和 `count > 0` 的 covered lines。
6. 删除容器与临时目录。

不同测试没有共享 `.gcda`，因此前一测试的计数不可能累积到后一测试。gcov JSON 由结构化解析器处理，不依赖人类可读文本的列宽或本地化格式。

gcov 默认只在正常退出时刷新 counter。若程序因 SIGSEGV 等信号终止，仅凭 `.gcno` 会生成误导性的全零结果。Coverage 编译因此通过 GCC `-include` 注入实验专用 signal handler：捕获 SIGSEGV、SIGABRT、SIGFPE、SIGBUS、SIGILL 后调用 `__gcov_dump()`，恢复默认处理并重新触发原信号。被测源码文件不被修改，退出码仍保留信号语义；当前 Pilot 的 3 个 exit 139 测试均通过该路径获得崩溃前部分覆盖。

## 9. Ground Truth

Ground truth 使用 Python `SequenceMatcher(autojunk=False)` 比较 buggy 与 reference 的源码行，只在 evaluation 模块中生成：

- 修改或删除：取 buggy 侧 changed block 中所有非空行。
- 多行修改：保留全部非空 buggy-side changed lines。
- reference-only 插入：buggy 侧没有直接行，映射到最近非空上下文，优先前一行，否则后一行。
- changed block 只有空行：同样映射到最近非空上下文。
- 非空花括号或声明行仍保留；规则不会查看 gcov 后再挑“更容易命中”的邻居。

结果保存为：

```json
{
  "case_id": "...",
  "fault_lines": [37, 38],
  "source": "buggy_reference_diff",
  "usage": "evaluation_only"
}
```

文本 diff ground truth 不是完美的语义根因标注。格式变化、花括号和不可执行行可能导致 fault line 不在 gcov ranking 中，这类情况按 miss 处理并在报告中分析。

## 10. 防止 Reference Leakage

定位数据流使用 `LocalizationInput`，该类型只包含 buggy source path、repair tests 和允许的 metadata，结构上不存在 reference 与 validation 字段。

```text
LocalizationInput
    -> Coverage Collector
    -> Coverage Matrix
    -> Spectrum Builder
    -> Ochiai/Tarantula/DStar2
    -> Ranking
```

另一条 evaluation-only 数据流为：

```text
buggy + explicit evaluation_only reference access
    -> textual diff
    -> ground truth fault lines
    -> metrics against completed rankings
```

Ground truth 文件位于 `benchmark/metadata/`，coverage 与 ranking 位于 `benchmark/results/fault_localization/`。算法 API 不接收 GroundTruth 参数。

## 11. 排名与并列

排序规则固定为：

1. suspiciousness 降序；
2. 分数相同时源码行号升序。

每条结果包含顺序 `rank`，同时保存 `tie_start_rank` 与 `tie_end_rank`。例如一个 fault line 位于 `[2, 8]` 同分组，其确定排名可能是 6；Top-5 会判定失败，但换一种 tie-break 可能命中。

本阶段 Top-K 使用确定的顺序 rank，保证重复运行一致。报告不会将并列组静默当作独立分数，也不会使用对算法更有利的 best-case tie rank。当前 Pilot 绝大多数 case 存在 top-score ties，因此解读 Top-K 时必须结合 tie 统计。

## 12. Top-K 与 MRR

对于一个 case，找到排名中第一个属于 ground truth 的行，其顺序位置为 `r`：

```text
Top-K hit = (r <= K)
reciprocal rank = 1 / r
```

若没有 ground-truth 行进入 ranking，则所有 Top-K 为 false，reciprocal rank 为 0。Top-K Accuracy 是命中 case 数除以参与评估 case 数；MRR 是所有 case reciprocal rank 的算术平均值。

本阶段计算 Top-1、Top-3、Top-5、Top-10 和 MRR，不增加定义易混淆的 EXAM Score。

## 13. 实际产物

- 冻结环境：`benchmark/metadata/experiment_environment.json`
- 逐测试 coverage：`benchmark/results/fault_localization/coverage/*.json`
- 可疑行与 spectrum：`benchmark/results/fault_localization/rankings/*.json`
- Evaluation-only ground truth：`benchmark/metadata/fault_localization_ground_truth.jsonl`
- 聚合指标：`benchmark/results/fault_localization/evaluation.json`
- 研究报告：`benchmark/reports/fault_localization_pilot_report.md`

完整运行：

```bash
python3 -m benchmark.scripts.run_fault_localization_pilot
python3 -m benchmark.scripts.generate_fault_localization_report
```

仅在算法或 ranking 变化后重建结果：

```bash
python3 -m benchmark.scripts.run_fault_localization_pilot --reuse-coverage
```

## 14. 局限

- SBFL 只衡量覆盖与失败的相关性，不理解数据依赖、控制依赖或程序语义。
- repair tests 少时 spectrum 粗糙，容易形成大规模同分。
- 全失败且无成功测试的 case 缺少对照；其排名可计算但证据弱。
- gcov 行覆盖无法表示同一行内多个表达式，也不会为纯花括号、宏展开等都生成独立可执行记录。
- 文本 diff 可能把语法上下文而非语义根因标为 ground truth。
- 当前实验只覆盖 50 个 C defect、GCC/gcov 12.2.0 和当前 Docker 镜像，不能直接外推到全量 Codeflaws 或其他语言。
- Docker suite 与临时文件仍共享宿主内核和本地磁盘，安全边界沿用 Phase 2，并非虚拟机级隔离。
