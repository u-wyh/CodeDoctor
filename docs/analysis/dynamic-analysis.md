# CodeDoctor 动态分析引擎设计

## 1. 阶段定位

CodeDoctor 的前两阶段解决了“如何可靠地编译和运行程序”以及“如何限制被测程序权限”的问题。第三阶段在此基础上回答另一个问题：程序失败时，系统能够获得什么可定位、可比较、可供后续自动修复使用的证据。

普通退出码和 stderr 只能说明一次执行的表面结果。动态分析通过在编译期插入检查逻辑，在运行时观察具体内存访问和未定义行为，并把报告转换为统一的 Bug Evidence。当前流程为：

```text
C++ Source + Input
        ↓
Sanitizer Analyzer
        ↓
Runner（Docker 或 local）
        ↓
-g -O1 -fno-omit-frame-pointer
-fno-pie -no-pie
-fsanitize=address,undefined
        ↓
Execution Result + Sanitizer stderr
        ↓
Layered Sanitizer Parser
        ↓
AnalysisResult.evidence[]
```

Runner 仍只负责执行。Analyzer 选择编译参数和运行环境。Parser 只负责把文本报告还原为证据。Evidence Model 不依赖某个 Sanitizer 的具体输出格式。

## 2. AddressSanitizer 原理

AddressSanitizer（ASan）主要检测内存安全错误。编译器在内存读写周围插入检查，并使用 shadow memory 表示应用地址是否可访问。堆对象、栈对象和全局对象周围会布置 poisoned redzone；越界访问落入 redzone 时，运行库能够报告访问地址、读写类型、访问宽度和调用栈。

释放堆对象后，其对应 shadow 区域会被标记为不可访问，因此再次解引用可检测为 heap-use-after-free。分配器拦截逻辑还可识别 double-free 和分配/释放方式不匹配等问题。

LeakSanitizer（LSan）随当前 GCC ASan 运行库启用。它在进程退出时扫描仍然可达的内存根，报告无法到达但尚未释放的堆对象。本项目通过 `ASAN_OPTIONS=detect_leaks=1` 明确启用泄漏检查。

ASan 不是通用逻辑错误检测器。合法地址上的错误值、错误算法、竞态条件，以及未执行路径中的缺陷不会被它发现。

## 3. UndefinedBehaviorSanitizer 原理

UndefinedBehaviorSanitizer（UBSan）针对 C/C++ 标准定义的未定义行为插入检查，例如有符号整数溢出、整数除零、非法移位、空指针解引用、数组下标越界和未对齐访问。

UBSan 的许多检查默认采用 recover 模式：报告错误后程序可以继续运行。因此 Runner 的状态可能仍是 `success`，但 AnalysisResult 已包含一个或多个 UBSan Evidence。这也是 CodeDoctor 不用退出码代替缺陷分类的原因。

当前配置使用 `UBSAN_OPTIONS=print_stacktrace=1:halt_on_error=0`，尽量保留多个诊断及其调用栈。无法恢复的硬件异常仍可能终止程序。

## 4. 为什么需要动态分析

动态分析提供的是一次具体执行上的行为证据，具有以下价值：

- 能确认缺陷在给定输入下真实发生，而不仅是静态可能性。
- 能记录失败访问的操作、宽度、地址和调用栈。
- 能把容器内路径还原为用户源码位置。
- 能区分同为 `runtime_error` 的越界、释放后使用、double-free 和除零。
- 能为后续 Fault Localization 提供候选文件、行号、函数和栈帧。
- 能为自动修复后的回归执行提供可比较的 Evidence 集合。

动态分析的代价是依赖测试输入和路径覆盖。没有执行到的缺陷不会产生报告，因此它必须与后续静态分析互补。

## 5. Runner Result 与 Analysis Evidence

两类结果属于不同层次：

- `RunnerResult` 描述编译与进程执行事实，包括状态、退出码、stdout、stderr、耗时和超时。
- `BugEvidence` 描述分析器从运行报告中识别出的缺陷事实，包括类别、源码位置、调用栈和分析器特有信息。

ASan 通常在首个严重错误后终止，因此 Runner 常为 `runtime_error`。UBSan 可能报告后继续，因此 Runner 可能为 `success`。普通非零退出码也可能完全没有 Sanitizer Evidence。CodeDoctor 不在这三种情况之间建立错误等价关系。

普通 CLI 的 JSON 保持原样。只有显式指定 `--analysis sanitizer` 时才增加：

```json
{
  "analysis": {
    "mode": "sanitizer",
    "evidence_count": 1,
    "evidence": []
  }
}
```

## 6. Bug Evidence Model

统一 Evidence 包含：

| 字段 | 含义 |
| --- | --- |
| `analyzer` | `asan`、`lsan` 或 `ubsan` |
| `category` | 稳定的 CodeDoctor 缺陷分类；无法分类时为 `unknown` |
| `severity` | 当前 Sanitizer 报告统一为 `error` |
| `summary` | 面向上层组件的简短摘要 |
| `message` | Sanitizer headline 或 runtime error 的详细消息 |
| `location` | 规范化后的文件、行、列；GCC 未提供列时允许为 null |
| `function` | 首个用户源码栈帧中的函数 |
| `stack_trace` | 有序栈帧列表 |
| `raw_report` | 完整 stderr 报告，不因 Parser 覆盖不足而丢失 |
| `memory_access` | ASan 的 READ/WRITE、访问宽度和地址 |
| `metadata` | UBSan 原消息等可扩展信息 |

`AnalysisResult.evidence` 天然是列表。ASan 往往只产生一个致命报告，但一次执行可以同时产生 UBSan 和 ASan 证据，也可以产生多个可恢复 UBSan 报告。

栈帧记录 index、function、file、line、column、address 和 `is_user_code`。`/workspace/main.cpp` 被规范化为 `main.cpp`；系统库帧仍保留。用户帧识别依据规范化的源文件身份，不依赖某个临时目录的绝对路径。

## 7. Parser 分层

Parser 没有使用单个大正则解析整份报告，而是执行以下步骤：

1. 扫描 ASan/LSan headline 和 UBSan `runtime error` 起始行。
2. 分别映射分析器类型和稳定缺陷分类。
3. 解析报告主调用栈，每一帧独立提取函数与位置。
4. 选择首个用户源码帧作为 ASan 主位置。
5. 解析 ASan 的 READ/WRITE、size 和 address。
6. 规范化 Docker 内部源码路径。
7. 保存完整原始 stderr 到每条 Evidence。

无法识别的 Sanitizer headline 会产生 `category=unknown`，而不是抛出异常。只有 `AddressSanitizer:DEADLYSIGNAL` 的不完整报告也会保留为 unknown Evidence。与 Sanitizer 无关的普通 stderr 不会被误认为 Evidence。

fixture 测试固定检查 category、line、column、function、memory access、用户栈帧、多 UBSan 诊断、JSON 序列化和 unknown 回退。真实 Docker 集成测试则验证编译器和运行库当前输出能够通过同一 Parser。

## 8. 当前检测范围

经过真实集成测试的类型如下：

| Analyzer | CodeDoctor category | 示例 |
| --- | --- | --- |
| ASan | `heap-buffer-overflow` | 堆数组越界写 |
| ASan | `stack-buffer-overflow` | 栈数组越界写 |
| ASan | `heap-use-after-free` | 释放后读取 |
| ASan | `double-free` | 同一堆指针重复释放 |
| LSan | `memory-leak` | 丢失的堆分配 |
| UBSan | `signed-integer-overflow` | `INT_MAX + 1` |
| UBSan | `division-by-zero` | 整数除零 |
| UBSan | `invalid-shift` | 移位位数等于类型宽度 |
| UBSan | `null-pointer-access` | 空指针解引用 |
| UBSan | `out-of-bounds` | 数组下标或对象空间不足 |

Parser 还预留并识别 global-buffer-overflow、stack-use-after-return、stack-use-after-scope、alloc-dealloc-mismatch 和 misaligned-address 等分类，但这些尚未纳入本阶段真实集成验收。

## 9. Sandbox 兼容性与设计取舍

Sanitizer 编译和运行继续使用 Phase 2 的相同 Docker 限制：禁用网络、256MB 内存和总内存加交换空间、1 核 CPU、64 个 PID、非 privileged、删除全部 capabilities、`no-new-privileges`、只读根文件系统，以及唯一的临时工作目录 bind mount。

ASan 在默认 PIE 构建下曾出现间歇性、只有重复 `AddressSanitizer:DEADLYSIGNAL` 的启动失败。该问题通过仅对分析构建增加 `-fno-pie -no-pie` 消除；连续 20 次正常程序压力运行均成功。没有提高资源上限或关闭任何沙箱安全设置。non-PIE 只影响分析二进制的地址布局，不影响普通 Runner。

## 10. 假阴性、假阳性与局限

主要假阴性来源包括：

- 测试输入没有覆盖缺陷路径。
- 优化改变了某些未定义行为的可观察形式。
- ASan 不检测初始化但逻辑错误的内存内容，也不检测所有生命周期和并发问题。
- LSan 把仍可从全局变量或栈访问的分配视为 reachable，不一定报告业务意义上的泄漏。
- 当前 Parser 只覆盖常见 GCC/Clang 文本形态，未知格式会降级为 `unknown`。

Sanitizer 通常具有较低假阳性率，因为报告对应实际发生的运行时检查失败。但 Evidence 的“根因位置”不一定等于报告的“失败访问位置”：内存早先被错误写坏时，ASan 可能在更晚的访问处报告。LSan 的 reachable 判定也可能与业务资源所有权不同。

当前还没有输出大小和临时磁盘配额，完整 raw report 可能较大；没有符号化工具链版本管理；没有跨 GCC/Clang 版本的 fixture 矩阵；没有合并语义重复的 UBSan/ASan Evidence；也没有执行覆盖率来解释“未发现证据”究竟意味着安全还是路径未执行。

## 11. 与 Fault Localization 的衔接

后续 Fault Localization 可以按以下顺序使用 Evidence：

1. 优先选择 `location` 指向的用户源码行。
2. 根据 `stack_trace.is_user_code` 收集同一执行路径上的候选调用点。
3. 使用 category 和 memory_access 区分根因模板，例如边界检查、生命周期管理或算术前置条件。
4. 结合未来的 Clang AST，把行号映射到表达式、语句和变量。
5. 修复后重新执行相同输入，比较 Evidence 是否消失、是否产生新 Evidence，以及普通输出是否保持正确。

动态 Evidence 不能独自证明根因，但它为静态结构分析和后续自动修复提供了真实、可回溯的运行时锚点。
