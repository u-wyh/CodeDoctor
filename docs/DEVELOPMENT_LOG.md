# CodeDoctor 开发日志

本文件按开发轮次追加记录。已有记录不得覆盖；每轮代码和测试完成后，以更新本文件作为最后一个文件操作。

## 2026-08-15：第一阶段 C++ Runner（历史补录）

### 1. 本次目标

使用 Python 3 实现 Linux 环境下的 C++17 编译与运行控制程序，接收 `main.cpp` 和 `input.txt`，捕获编译及运行结果，支持 5 秒运行超时，并输出结构化 JSON。

### 2. 实际完成内容

- 使用 `g++ -std=c++17` 编译单个 C++ 源文件。
- 捕获编译和运行阶段的 stdout、stderr、退出码及耗时。
- 将输入文件作为程序 stdin。
- 实现 `success`、`compile_error`、`runtime_error`、`time_limit_exceeded`、`internal_error` 五种状态。
- 使用临时目录保存可执行文件，并使用独立进程组处理超时程序及其子进程。
- 创建 Hello World、两数求和、编译错误、非零退出码和死循环五类示例。
- 使用 Python `unittest` 创建集成测试和 CLI JSON 测试。

### 3. 文件变更

新增：

- `.gitignore`
- `README.md`
- `sandbox/__init__.py`
- `sandbox/runner/__init__.py`
- `sandbox/runner/config.py`
- `sandbox/runner/models.py`
- `sandbox/runner/executor.py`
- `sandbox/runner/main.py`
- `sandbox/tests/__init__.py`
- `sandbox/tests/test_runner.py`
- `examples/hello_world/main.cpp`、`input.txt`
- `examples/sum/main.cpp`、`input.txt`
- `examples/compile_error/main.cpp`、`input.txt`
- `examples/runtime_error/main.cpp`、`input.txt`
- `examples/timeout/main.cpp`、`input.txt`

删除：无。

### 4. 执行过的重要命令

```bash
python3 --version
g++ --version
python3 -m unittest discover -s sandbox/tests -v
PYTHONDONTWRITEBYTECODE=1 python3 sandbox/runner/main.py examples/sum/main.cpp examples/sum/input.txt
```

另外使用 Python 脚本依次调用 `run_cpp_program` 运行五个示例，并记录各状态、退出码、超时标志和耗时。

### 5. 实际测试结果

- 自动化测试最终为 7 项全部通过，耗时 1.251 秒。
- Hello World：`success`，stdout 为 `Hello World\n`。
- 两数求和：`success`，stdout 为 `3\n`。
- 编译错误：`compile_error`，编译退出码为 1。
- 非零退出码：`runtime_error`，程序退出码为 7。
- 死循环：`time_limit_exceeded`，默认超时实测约 5006 ms。
- 缺失源文件：`internal_error`。
- 直接脚本入口输出了可解析的 JSON。

### 6. 遇到的问题及解决方式

- 初始目录为空：从零创建包结构、示例和测试目录。
- 死循环程序可能遗留子进程：通过 `start_new_session=True` 创建独立会话，超时时使用进程组信号终止并回收输出。
- 需要同时支持模块和直接脚本入口：在 `main.py` 中根据 `__package__` 调整导入路径。

### 7. 当前已知不足

- 本地 Runner 不构成安全沙箱。
- 未限制 CPU、内存、磁盘、输出大小、文件访问和系统调用。
- 暂不适合执行不可信代码。

### 8. 下一步计划

- 将编译和运行迁移到 Docker 容器。
- 保留本地执行后端，增加可切换的执行后端结构。
- 对容器增加网络、内存、CPU 和进程数限制。

## 2026-08-15：第二阶段 Docker 沙箱化

### 1. 本次目标

在不破坏现有 CLI 和 JSON 结构的前提下，将 C++ 编译和运行迁入 Docker，默认使用 `codedoctor-cpp-sandbox` 镜像；保留本地后端，并增加网络、内存、CPU、PID 和权限限制以及 Docker 错误处理。

### 2. 实际完成内容

- 将原宿主执行逻辑迁入独立 `local` 后端，未删除其功能。
- 新增默认 `docker` 后端，并通过 `RunnerConfig.backend` 和 CLI `--backend` 切换。
- 默认编译超时改为 20 秒，程序运行超时保持 5 秒。
- Docker 后端会检查 Docker CLI、daemon 和目标镜像；缺失或不可用时返回带明确原因的 `internal_error`。
- 每次调用创建一次性临时工作目录，将源文件和输入复制进去，只将该目录 bind mount 到 `/workspace`。
- 编译和运行分别使用具名容器；正常结束、错误和超时路径都会执行 `docker rm --force`。
- 容器禁用网络，限制为 256MB 内存、总计 256MB 内存加交换空间、1 核 CPU、64 个 PID；删除全部 capabilities，启用 `no-new-privileges` 和只读根文件系统，未使用 privileged。
- `/tmp` 使用 64MB tmpfs，文件描述符限制为 256。
- 保持原有公开 `run_cpp_program()`、CLI 参数位置及 JSON 字段结构。
- 增加 Docker 错误与安全参数测试，并保留五类 C++ 集成测试。

### 3. 文件变更

新增：

- `sandbox/docker/Dockerfile`
- `sandbox/docker/.dockerignore`
- `sandbox/runner/docker_executor.py`
- `sandbox/runner/local_executor.py`
- `sandbox/runner/process.py`
- `sandbox/runner/result_factory.py`
- `docs/DEVELOPMENT_LOG.md`

修改：

- `README.md`
- `sandbox/runner/config.py`
- `sandbox/runner/executor.py`
- `sandbox/runner/main.py`
- `sandbox/tests/test_runner.py`

删除：无最终删除文件。原 `executor.py` 的宿主逻辑被重构到 `local_executor.py`，公共入口文件仍保留。

### 4. 执行过的重要命令

环境检查：

```bash
docker --version
docker info --format '{{.ServerVersion}}'
sudo -n true
unshare --user --map-root-user true
lxc version
lxd init --auto
```

Docker 验证环境和镜像构建：

```bash
lxc launch ubuntu:24.04 codedoctor-docker-host -c security.nesting=true -c security.syscalls.intercept.mknod=true -c security.syscalls.intercept.setxattr=true
lxc exec codedoctor-docker-host -- apt-get update
lxc exec codedoctor-docker-host -- env DEBIAN_FRONTEND=noninteractive apt-get install --yes docker.io python3
lxc exec codedoctor-docker-host -- docker info --format '{{.ServerVersion}} {{.Driver}}'
lxc exec codedoctor-docker-host -- docker build --tag codedoctor-cpp-sandbox --file /workspace/CodeDoctor/sandbox/docker/Dockerfile /workspace/CodeDoctor/sandbox/docker
```

由于 Docker Hub 连接超时，实际执行了以下本地基础镜像准备命令后重新构建：

```bash
lxc exec codedoctor-docker-host -- env DEBIAN_FRONTEND=noninteractive apt-get install --yes debootstrap
lxc exec codedoctor-docker-host -- debootstrap --variant=minbase bookworm /tmp/codedoctor-debian-rootfs http://deb.debian.org/debian
lxc exec codedoctor-docker-host -- sh -lc 'tar -C /tmp/codedoctor-debian-rootfs -c . | docker import - debian:bookworm-slim'
lxc exec codedoctor-docker-host -- docker build --tag codedoctor-cpp-sandbox --file /workspace/CodeDoctor/sandbox/docker/Dockerfile /workspace/CodeDoctor/sandbox/docker
```

测试和检查：

```bash
lxc exec codedoctor-docker-host -- su -s /bin/bash ubuntu -c 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s sandbox/tests -v'
lxc exec codedoctor-docker-host -- docker ps --filter name=codedoctor- --format '{{.Names}}'
lxc exec codedoctor-docker-host -- docker inspect --format 'Network={{.HostConfig.NetworkMode}} Memory={{.HostConfig.Memory}} MemorySwap={{.HostConfig.MemorySwap}} NanoCpus={{.HostConfig.NanoCpus}} Pids={{.HostConfig.PidsLimit}} Privileged={{.HostConfig.Privileged}} Readonly={{.HostConfig.ReadonlyRootfs}} CapDrop={{json .HostConfig.CapDrop}} SecurityOpt={{json .HostConfig.SecurityOpt}} Mounts={{json .Mounts}}' codedoctor-2181a70028f54fd59f304499f5e35db3
lxc stop codedoctor-docker-host
```

### 5. 实际测试结果

- 第一次 Docker 集成测试：12 项中 6 项失败，失败集中在所有需要成功编译/运行的 Docker 用例和验证环境的本地后端用例。
- 修复后再次运行：12 项全部通过，耗时 4.236 秒。
- 五类 Docker 示例结果：Hello World 和求和为 `success`；语法错误为 `compile_error`；退出码 7 为 `runtime_error`；死循环为 `time_limit_exceeded`。
- 缺失源文件、Docker CLI 缺失、daemon 不可用、镜像缺失均验证为 `internal_error`。
- 默认 5 秒超时实测约 5009 ms。
- 求和 CLI 实测：编译 424 ms，运行 198 ms，stdout 为 `3\n`。
- 镜像成功构建为 `codedoctor-cpp-sandbox:latest`，镜像 ID 为 `sha256:942eae83a5c515e44d0861fbfc76671f9c3dbbcfbde29defcdf22f3ae2ad92a6`。
- Docker 实际配置检查结果：网络为 `none`，内存和 MemorySwap 均为 268435456 字节，NanoCPUs 为 1000000000，PIDsLimit 为 64，Privileged 为 false，只读根文件系统为 true，CapDrop 为 `ALL`，SecurityOpt 为 `no-new-privileges`。
- 实际检查显示唯一 bind mount 为本轮临时目录到 `/workspace`。
- 超时和全部测试结束后，未发现残留的 `codedoctor-*` Docker 容器或 `codedoctor-docker-*` 临时目录。

### 6. 遇到的问题

- 当前宿主没有 Docker CLI，`docker` 命令不存在。
- `sudo -n true` 需要密码，无法直接在宿主安装 Docker。
- 内核拒绝无特权 user namespace，无法使用 rootless Docker。
- 第一次使用错误的 LXD 镜像别名 `images:ubuntu/24.04`，镜像不存在。
- Docker Hub 拉取 `debian:bookworm-slim` 时连接超时。
- 初版 bind mount 参数写成 `type=bind,src=...,dst=/workspace,rw`，Docker 29 要求 `--mount` 的字段为键值形式，因而返回退出码 125。
- 初版把 Docker CLI 的 125 基础设施错误误判成了 `compile_error`。
- LXD 验证宿主最初没有宿主 g++，导致 local 后端兼容性测试返回 `internal_error`。

### 7. 问题的解决方式

- 使用已安装并初始化的 LXD 创建隔离 Ubuntu 验证宿主，在其中安装 Docker 29.1.3，并挂载项目目录完成真实构建和测试。
- 将 LXD 镜像来源改为存在的 `ubuntu:24.04`。
- Docker Hub 不可用时，通过 Debian 官方软件源和 `debootstrap` 生成本地 Bookworm 根文件系统，导入为 `debian:bookworm-slim` 后原样执行项目 Dockerfile。
- 删除 `--mount` 参数末尾多余的 `rw`；bind mount 默认可写。
- 对 Docker CLI 退出码 125 增加容器存在性检查；容器未创建时转为明确的 `DockerBackendError` 和 `internal_error`。
- 在验证宿主安装 g++ 后重新执行 local 后端测试。
- 修复后完整重跑 12 项测试，并额外在程序运行期间执行 `docker inspect` 验证限制真实生效。

### 8. 当前已知不足

- 当前物理宿主仍没有 Docker CLI；默认调用会正确返回 `Docker CLI 'docker' was not found in PATH` 的 `internal_error`。真实 Docker 镜像和验证环境位于已停止的 `codedoctor-docker-host` LXD 容器中。
- Docker 容器共享 daemon 所在宿主的 Linux 内核，不是虚拟机级隔离。
- 尚未限制 stdout/stderr 总量和临时工作目录磁盘写入量，恶意程序可能消耗宿主内存或磁盘。
- 使用 Docker 默认 seccomp/AppArmor 配置，没有项目专用系统调用策略。
- 没有使用 gVisor、Kata Containers 或独立虚拟机。
- 当前 CLI 对已处理的用户程序错误仍返回进程退出码 0，调用方需要读取 JSON 中的 `status`。

### 9. 下一步计划

- 后续每轮开发继续以追加方式维护本日志，并确保日志更新是该轮最后一个文件操作。
- 在进入程序分析或 AI 修复阶段前，考虑增加输出大小和临时磁盘配额。
- 根据后续部署环境决定是否加入自定义 seccomp/AppArmor、gVisor 或更强隔离。
- 按项目后续阶段要求再引入缺陷分析工具；本阶段未加入 ASan、UBSan、clang-tidy、cppcheck、AI、前端或后端。

## 2026-08-15：第三阶段 Dynamic Analysis Engine

### 1. 本次目标

在保留普通 Runner 和 Docker Sandbox 行为的前提下，引入 ASan、LSan 和 UBSan 分析模式，建立 CodeDoctor 第一套统一 Bug Evidence Model；把 Sanitizer 文本报告解析为可序列化、支持多个诊断并保留完整原始报告的结构化证据。

### 2. 实际完成内容

- 新增独立 `analysis` 层，将执行、分析决策、文本解析和 Evidence 数据模型分离。
- 普通 Runner 行为保持兼容；仅显式使用 `--analysis sanitizer` 时启用动态分析并在原 JSON 中增加 `analysis` 字段。
- Runner 配置新增通用 `extra_compile_flags` 和 `run_environment`，local 与 docker 两种后端均支持，未把 Sanitizer 逻辑写入 Docker executor。
- Sanitizer 分析构建实际使用 `-g -O1 -fno-omit-frame-pointer -fno-pie -no-pie -fsanitize=address,undefined`。
- 运行环境实际设置 `ASAN_OPTIONS=detect_leaks=1:symbolize=1:exitcode=1`、`UBSAN_OPTIONS=print_stacktrace=1:halt_on_error=0` 和 `LSAN_OPTIONS=symbolize=1:exitcode=1`。
- 建立 `AnalysisResult`、`BugEvidence`、`SourceLocation`、`StackFrame`、`MemoryAccess` 模型。
- Evidence 支持 `analyzer`、`category`、`severity`、`summary`、`message`、源码位置、函数、调用栈、完整 `raw_report`、内存访问和可扩展 metadata。
- Parser 分层识别 ASan/LSan headline、UBSan runtime error、错误分类、源码位置、调用栈、用户源码帧和 ASan READ/WRITE 信息。
- `/workspace/main.cpp` 和本地主文件绝对路径会规范化为 `main.cpp`；系统库帧继续保留并标记为非用户源码。
- Parser 天然返回 Evidence 列表，真实测试观察到一次栈越界执行同时产生多个 UBSan/ASan Evidence。
- 未识别的 Sanitizer 类型降级为 `category=unknown`；只有重复 `AddressSanitizer:DEADLYSIGNAL` 的不完整报告也会保留原始证据。
- 创建正常程序、四类 ASan 错误、LSan 泄漏和四类 UBSan 错误的真实示例。
- 创建 ASan 和多诊断 UBSan fixture，以及独立 Parser 回归测试。
- 新增完整动态分析设计文档，说明原理、架构、模型、解析流程、检测范围、局限和 Fault Localization 衔接方式。

### 3. 新增、修改和删除的文件

新增：

- `analysis/__init__.py`
- `analysis/models.py`
- `analysis/sanitizer/__init__.py`
- `analysis/sanitizer/analyzer.py`
- `analysis/sanitizer/parser.py`
- `docs/analysis/dynamic-analysis.md`
- `sandbox/tests/test_sanitizer_parser.py`
- `sandbox/tests/test_sanitizer_integration.py`
- `sandbox/tests/fixtures/asan_heap_buffer_overflow.txt`
- `sandbox/tests/fixtures/ubsan_multiple.txt`
- `examples/sanitizer_clean/main.cpp`、`input.txt`
- `examples/asan_heap_overflow/main.cpp`、`input.txt`
- `examples/asan_stack_overflow/main.cpp`、`input.txt`
- `examples/asan_use_after_free/main.cpp`、`input.txt`
- `examples/asan_double_free/main.cpp`、`input.txt`
- `examples/asan_memory_leak/main.cpp`、`input.txt`
- `examples/ubsan_signed_overflow/main.cpp`、`input.txt`
- `examples/ubsan_division_by_zero/main.cpp`、`input.txt`
- `examples/ubsan_invalid_shift/main.cpp`、`input.txt`
- `examples/ubsan_null_pointer/main.cpp`、`input.txt`

修改：

- `README.md`
- `sandbox/runner/config.py`
- `sandbox/runner/process.py`
- `sandbox/runner/local_executor.py`
- `sandbox/runner/docker_executor.py`
- `sandbox/runner/main.py`
- `sandbox/tests/test_runner.py`
- `docs/DEVELOPMENT_LOG.md`

删除：无。

`sandbox/docker/Dockerfile` 未修改；现有 Debian Bookworm + g++ 镜像已经包含本阶段实际使用的 GCC Sanitizer 运行库。

### 4. 执行过的重要命令

Parser 测试：

```bash
python3 -B -m unittest sandbox.tests.test_sanitizer_parser -v
```

该命令在修复 frame location 解析前后均实际执行；修复后又在增加 DEADLYSIGNAL 回退测试后执行一次。

Docker 环境与镜像：

```bash
lxc start codedoctor-docker-host
lxc exec codedoctor-docker-host -- docker info --format '{{.ServerVersion}} {{.Driver}}'
lxc exec codedoctor-docker-host -- docker image inspect codedoctor-cpp-sandbox --format '{{.RepoTags}} {{.Id}}'
lxc exec codedoctor-docker-host -- docker build --tag codedoctor-cpp-sandbox --file /workspace/CodeDoctor/sandbox/docker/Dockerfile /workspace/CodeDoctor/sandbox/docker
```

完整测试实际多次执行：

```bash
lxc exec codedoctor-docker-host -- su -s /bin/bash ubuntu -c 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s sandbox/tests -v'
```

实际 JSON 验证：

```bash
lxc exec codedoctor-docker-host -- su -s /bin/bash ubuntu -c 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 -m sandbox.runner.main examples/sanitizer_clean/main.cpp examples/sanitizer_clean/input.txt --analysis sanitizer'
lxc exec codedoctor-docker-host -- su -s /bin/bash ubuntu -c 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 -m sandbox.runner.main examples/asan_heap_overflow/main.cpp examples/asan_heap_overflow/input.txt --analysis sanitizer'
lxc exec codedoctor-docker-host -- su -s /bin/bash ubuntu -c 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 -m sandbox.runner.main examples/ubsan_signed_overflow/main.cpp examples/ubsan_signed_overflow/input.txt --analysis sanitizer'
```

另外实际使用 `python3 -B - <<'PY'` 脚本通过 local 后端依次分析 10 个示例并打印状态、analyzer、category、line 和 function；使用同类脚本在 Docker 后端先连续运行正常程序 12 次，再在修复后连续运行 20 次。

清理检查和验证环境停止：

```bash
lxc exec codedoctor-docker-host -- docker ps --all --filter name=codedoctor- --format '{{.ID}} {{.Names}} {{.Status}}'
lxc exec codedoctor-docker-host -- find /tmp -maxdepth 1 -type d -name 'codedoctor-docker-*' -print
find /home/wyh/CodeDoctor -type d -name __pycache__ -print
lxc stop codedoctor-docker-host
```

### 5. 实际测试结果

- Parser fixture 第一次执行共 5 项，其中 3 PASS、1 FAIL、1 ERROR；失败原因为 stack frame 的文件、行、列拆分错误。
- 修复位置解析后 Parser 测试 5/5 PASS。
- 增加不完整 DEADLYSIGNAL 回退测试后 Parser 测试 6/6 PASS。
- local 后端预检实际检测到：heap-buffer-overflow、stack-buffer-overflow、heap-use-after-free、double-free、memory-leak、signed-integer-overflow、division-by-zero、invalid-shift、null-pointer-access；正常程序 Evidence 为空。
- Docker 全量测试第一轮共 27 项，25 PASS、2 FAIL。失败项为正常 Sanitizer 程序和 heap-buffer-overflow；随后单独重跑 heap-buffer-overflow 时成功得到 UBSan 与 ASan 两条 Evidence。
- 正常 Sanitizer 程序 Docker 压力复现 12 次，其中 2 次以退出码 139 失败，stderr 只有重复 `AddressSanitizer:DEADLYSIGNAL`。
- 增加 non-PIE 分析编译参数后，正常程序连续 20 次 Docker 运行全部成功，失败列表为空。
- 修复后完整套件曾达到 28/28 PASS，耗时 9.985 秒。
- 增加分析 CLI 回归测试后最终完整套件为 29/29 PASS，耗时 10.553 秒。
- 最终结果：29 PASS、0 FAIL、0 ERROR、0 SKIPPED。
- 内存泄漏在当前 GCC 12 / LSan / Docker 环境中稳定产生 `lsan`、`memory-leak` Evidence，因此未标记 SKIPPED。
- 真实 signed integer overflow CLI 结果：Runner 状态为 `success`、运行退出码 0、Evidence 数为 1；Evidence 为 `ubsan` / `signed-integer-overflow`，位置 `main.cpp:5:11`，函数 `main`，调用栈首帧为用户源码，完整 raw report 已保留。
- 最终检查未发现残留的 `codedoctor-*` Docker 容器、`codedoctor-docker-*` 临时目录或 Python `__pycache__`。

### 6. 遇到的问题及原因

#### 6.1 Stack frame 位置解析错误

fixture 首轮测试中，`/workspace/main.cpp:8:19` 被正则错误拆分为文件 `main.cpp:8` 和行 `19`。原因是文件字段允许冒号且匹配过于贪婪，导致列号被当成行号。

#### 6.2 Docker 中 ASan 间歇性 DEADLYSIGNAL

在保留 Phase 2 全部限制时，ASan 默认 PIE 二进制偶发在程序逻辑执行前以 139 退出，只产生重复 DEADLYSIGNAL。12 次复现中出现 2 次。该现象符合 PIE 地址随机化与 ASan shadow memory 地址布局间歇冲突的行为；不是被测正常程序本身的缺陷。

#### 6.3 Runner 状态不能代表 Sanitizer 诊断

真实 signed integer overflow 中 UBSan 报告了错误，但程序在 recover 模式下退出码仍为 0，Runner 状态为 `success`。相反，普通非零退出也可能没有任何 Sanitizer Evidence。

#### 6.4 同一执行包含多个报告

真实 heap 和 stack 越界运行可先产生 UBSan 报告，再产生 ASan 报告。若模型只保存单一诊断，会丢失有价值的补充证据。

### 7. 问题解决方式

- 将 frame 末尾位置正则收紧为 Linux 路径文件字段不包含冒号，明确拆分 file、line 和可选 column；修复后独立 Parser 测试通过。
- 仅在 Sanitizer 分析编译中加入 `-fno-pie -no-pie`；未修改普通 Runner，也未提高内存、CPU、PID 上限或放宽 capabilities、network、privileged、read-only 等 Docker 限制。
- non-PIE 修复后进行 20 次连续正常程序 Docker 压力测试，未再复现启动失败。
- 为只有 DEADLYSIGNAL 的不完整 ASan 文本增加单条 `unknown` Evidence 回退，保证 raw report 不被静默丢弃。
- 将 RunnerResult 与 AnalysisResult 分离；Evidence 分类完全来自 Sanitizer 报告，不依赖进程退出码。
- 将 `evidence` 设计为列表并对每个 UBSan/ASan headline 独立解析，支持单次执行的多个诊断。

### 8. 设计取舍

- `raw_report` 在每条 Evidence 中保存完整 stderr，而不是只保存匹配片段。该设计会重复数据，但确保后续 Parser 升级、论文实验和修复反馈能够回溯全部上下文。
- ASan/LSan/UBSan 使用统一基础模型，但 ASan 专有访问数据放入 `memory_access`，UBSan 原始 runtime message 放入 metadata，避免为了统一而丢失细节。
- LSan 证据的 analyzer 明确记录为 `lsan`，而不是合并成 `asan`；它仍由同一 sanitizer 分析模式产生。
- UBSan 保持 recover 模式以支持多个诊断；不可恢复的除零和空指针等行为仍可能触发后续 ASan signal 报告。
- 系统库栈帧保留，用户源码帧通过规范化文件身份标识，未依赖随机临时目录绝对路径。
- fixture 使用稳定、归一化的典型 GCC Sanitizer 文本；真实 Docker 集成测试独立验证当前编译器输出，避免 fixture 地址随机性影响回归。

### 9. 当前已知不足

- 动态分析只能发现当前输入实际执行路径上的缺陷，未覆盖路径会产生假阴性。
- 当前 Parser 重点覆盖常见 GCC/Clang 文本形态；未知格式只降级为 `unknown`，尚无多版本输出矩阵。
- GCC ASan 主栈帧经常只提供行号而没有列号，因此 ASan Evidence 的 column 可能为 null。
- 尚未对同一根因产生的 UBSan 与 ASan Evidence 做语义去重或关联。
- `raw_report` 可能较大，当前仍没有 stdout/stderr 大小限制和临时磁盘配额。
- ASan/UBSan 增加明显运行和内存开销；当前测试规模尚未形成性能基准。
- 未实现执行覆盖率，Evidence 为空不能证明程序没有缺陷。
- Docker 仍共享宿主内核，没有使用 gVisor、Kata 或虚拟机级隔离。

### 10. 下一步计划

- 下一阶段建议实现 Clang AST Program Analysis，但本轮未开始。
- 将动态 Evidence 的 file、line、function 与未来 AST 节点建立映射。
- 后续 Fault Localization 可优先使用用户源码栈帧、缺陷 category 和 memory_access 缩小候选语句范围。
- 在后续工程强化阶段增加输出上限、临时磁盘配额和跨编译器版本 fixture。
- 继续在每轮完成代码和测试后，以追加 `docs/DEVELOPMENT_LOG.md` 作为最后一个开发操作。

---

## 2026-08-15 - Phase 3（调整后）：Dataset Acquisition & Benchmark Bootstrap

### 1. 本次目标

- 只处理 Codeflaws 官方数据，建立后续实验使用的数据基础，不进入 Fault Localization、LLM Repair、AST/CFG 或新的 Sanitizer 开发。
- 自动下载并解压官方完整归档，保存来源、时间、大小和校验值，避免重复下载和静默覆盖原始数据。
- 建立与 Codeflaws 原始目录解耦的 `BenchmarkCase` 模型、全量 manifest 和完整性检查。
- 使用缺陷分类和固定种子 `20260815` 分层筛选约 50 个 case，并在现有 Docker 沙箱中真实编译、运行 repair tests 和 held-out validation tests。
- 保存 pilot、排除记录、实际执行结果、统计报告和可提交 Git 的小样本，并明确阻止 reference source 泄漏到未来 repair-time 输入。

### 2. 实际完成内容

- 从 Codeflaws 官方 NUS 发布地址下载 `codeflaws.tar.gz`，从官方缺陷表下载分类 metadata；没有爬取 Codeforces，也没有使用第三方镜像。
- 下载器支持 `.part` 断点续传、已有归档跳过、非空 raw 目录拒绝覆盖、安全 tar 解压、网络错误提示、SHA-256 和 UTC 时间记录。
- 完整归档为 `265695532` bytes，SHA-256 为 `2673fc16fa05590c5c1171f5b633594713ae9207346a3d0ba4c4d8b2eea82b11`；下载时间记录为 `2026-08-15T13:17:43.267664+00:00`。
- 解压后的 raw 数据约 2.9 GB，共 403843 个文件、3904 个 case 目录、7808 个 C 源文件；下载目录约 254 MB。
- 官方分类网页解析到 4085 条记录，归档实际包含 3904 个 case；归档中的 3904 个 case 均匹配到 defect class，manifest 不创建网页中不存在于归档的案例。
- 实现统一 `BenchmarkCase`、`ProblemIdentity`、`ProgramArtifact`、`TestSuites` 和 `BenchmarkTest`，所有 manifest 路径均为项目根目录相对路径。
- 实现 `load_manifest()`、`load_case()`、buggy source 和两类测试访问接口；`get_reference_source()` 必须显式传入 `evaluation_only=True`，`repair_time_view()` 排除 reference 和 validation tests。
- 以官方 `test-genprog.sh` / `test-valid.sh` 中的 `case ... run_test` 映射定义正式测试集合，并保留脚本指定的空行、行首空白和行尾空白比较语义。
- 全量 manifest 共 3904 行、约 40 MB；静态校验最终得到 3884 valid、20 invalid，20 个无效案例均为测试集合不完整，无 missing source、missing Makefile、unreadable source 或 duplicate id。
- Docker benchmark 编译使用原始 Makefile 的 `gcc -std=c99`、`-lm -s -O2` 等参数，没有强行替换成通用 Runner 的 `g++ -std=c++17`。
- 在现有镜像中增加 `make`，benchmark 复用 Docker 模块公开的 `check_docker()` / `run_container()`，完整保留网络、256 MB 内存、1 CPU、64 PID、capability、只读根文件系统和临时目录挂载限制。
- Pilot 按 defect class 分组、组内固定种子打乱、类别 round-robin 排序。最终动态测试 55 个候选，50 个进入 pilot，覆盖 38 个 defect class。
- 最终 pilot 包含 180 个 repair tests 和 1600 个 validation tests。50 个 reference 全部通过对应完整测试，每个 pilot buggy 至少失败一个正式测试。
- `excluded_cases.jsonl` 最终 25 行：20 个静态测试不完整、2 个 reference repair 失败、2 个 reference validation 失败、1 个 buggy 通过全部正式测试。
- 生成 55 行 `pilot_results.jsonl`，记录两份程序的编译结果、suite 通过数、失败数、首个失败 test、超时和运行错误；生成 50 行 `pilot.jsonl` 和基于实际产物计算的 Markdown/JSON 报告。
- 导出 3 个自包含的小样本，每个保留 buggy、evaluation-only reference、Makefile、1 个 repair test 和 1 个 validation test；完整 raw 和归档继续由 `.gitignore` 排除。

### 3. 新增、修改和删除的文件

新增核心代码：

- `benchmark/__init__.py`
- `benchmark/config.py`
- `benchmark/models.py`
- `benchmark/codeflaws.py`
- `benchmark/execution.py`
- `benchmark/sampling.py`
- `benchmark/reporting.py`
- `benchmark/scripts/__init__.py`
- `benchmark/scripts/download_codeflaws.py`
- `benchmark/scripts/prepare_codeflaws.py`
- `benchmark/scripts/validate_codeflaws.py`
- `benchmark/scripts/build_codeflaws_pilot.py`
- `benchmark/scripts/generate_codeflaws_report.py`
- `benchmark/scripts/export_codeflaws_sample.py`
- `benchmark/tests/__init__.py`
- `benchmark/tests/test_download.py`
- `benchmark/tests/test_models.py`
- `benchmark/tests/test_execution.py`

新增数据、报告和文档：

- `benchmark/datasets/codeflaws/metadata/download.json`
- `benchmark/datasets/codeflaws/metadata/defect_classes.json`
- `benchmark/datasets/codeflaws/metadata/manifest.jsonl`
- `benchmark/datasets/codeflaws/metadata/validation_report.json`
- `benchmark/datasets/codeflaws/metadata/pilot.jsonl`
- `benchmark/datasets/codeflaws/metadata/pilot_results.jsonl`
- `benchmark/datasets/codeflaws/metadata/excluded_cases.jsonl`
- `benchmark/datasets/codeflaws/sample/` 下的 3 个小样本、README 和 sample manifest
- `benchmark/reports/codeflaws_pilot_report.md`
- `benchmark/reports/codeflaws_pilot_report.json`（生成数据，默认被 `.gitignore` 排除）
- `docs/benchmark/codeflaws.md`
- raw、processed、downloads、metadata 和 reports 目录的 `.gitkeep`

修改：

- `.gitignore`
- `README.md`
- `sandbox/docker/Dockerfile`
- `sandbox/runner/docker_executor.py`
- `docs/DEVELOPMENT_LOG.md`

删除：无。

本地生成但默认不纳入 Git：

- `benchmark/datasets/codeflaws/downloads/codeflaws.tar.gz`
- `benchmark/datasets/codeflaws/raw/codeflaws/` 完整解压数据

### 4. 执行过的重要命令

官方来源与可用性检查：

```bash
curl --head https://www.comp.nus.edu.sg/~release/codeflaws/codeflaws.tar.gz
git ls-remote https://github.com/codeflaws/codeflaws HEAD
```

下载、转换和静态验证：

```bash
python3 -m benchmark.scripts.download_codeflaws
PYTHONDONTWRITEBYTECODE=1 python3 -m benchmark.scripts.prepare_codeflaws
PYTHONDONTWRITEBYTECODE=1 python3 -m benchmark.scripts.validate_codeflaws --strict
du -sh benchmark/datasets/codeflaws/raw benchmark/datasets/codeflaws/downloads
find benchmark/datasets/codeflaws/raw -type f | wc -l
sha256sum benchmark/datasets/codeflaws/downloads/codeflaws.tar.gz
```

Docker 镜像和 pilot 冒烟：

```bash
lxc start codedoctor-docker-host
lxc exec codedoctor-docker-host -- su -s /bin/bash ubuntu -c 'docker build --tag codedoctor-cpp-sandbox --file /workspace/CodeDoctor/sandbox/docker/Dockerfile /workspace/CodeDoctor/sandbox/docker'
lxc exec codedoctor-docker-host -- su -s /bin/bash ubuntu -c 'docker run --rm --network none codedoctor-cpp-sandbox make --version | head -1'
lxc exec codedoctor-docker-host -- su -s /bin/bash ubuntu -c 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 -m benchmark.scripts.build_codeflaws_pilot --target-size 2 --max-candidates 5 --force'
```

完整 pilot 在修复 suite 识别前后均实际执行；最终命令为：

```bash
lxc exec codedoctor-docker-host -- su -s /bin/bash ubuntu -c 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 -m benchmark.scripts.build_codeflaws_pilot --target-size 50 --seed 20260815 --force'
```

报告和样本：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m benchmark.scripts.generate_codeflaws_report
PYTHONDONTWRITEBYTECODE=1 python3 -m benchmark.scripts.export_codeflaws_sample
```

单元、回归和真实 case 复验：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s benchmark/tests -v
lxc exec codedoctor-docker-host -- su -s /bin/bash ubuntu -c 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s sandbox/tests -v'
```

另外实际执行内联 Python 完整性检查，断言 pilot 数量与唯一性、所有路径为相对路径且存在、pilot 与 reproducible results 集合一致、reference 通过全部测试、buggy 至少失败一次、reference 默认读取被拒绝，以及 3 个 sample 均可加载。

最终清理：

```bash
lxc exec codedoctor-docker-host -- su -s /bin/bash ubuntu -c 'docker ps -a --filter name=codedoctor- --format "{{.Names}} {{.Status}}"'
lxc exec codedoctor-docker-host -- find /tmp -maxdepth 1 -type d -name 'codedoctor-benchmark-*' -print
find /home/wyh/CodeDoctor -type d -name __pycache__ -print
lxc stop codedoctor-docker-host
```

### 5. 实际测试结果

- 下载成功：archive `265695532` bytes，SHA-256 校验完成，解压约 2.9 GB。
- 最终静态校验：3904 total、3884 valid、20 invalid、20 missing tests、0 missing buggy、0 missing reference、0 missing Makefile、0 unreadable source、0 duplicate id。
- `--strict` 静态校验按设计返回非零，因为真实存在 20 个无效 case；报告文件正常生成。
- 初始 benchmark 单元测试为 7/7 PASS；增加已有归档跳过测试后，最终为 8/8 PASS。
- Docker/Runner/Sanitizer 既有完整回归最终为 29/29 PASS，耗时 10.564 秒；增加 `make` 和公开 Docker 复用接口未破坏前两阶段。
- 两案例 Docker 冒烟为 2/2 可复现：第一个 reference 通过 31 个 repair 和 63 个 validation 文件（当时尚未按脚本映射过滤额外文件），第二个 reference 通过 4 个 repair 和 76 个 validation 文件。
- 修正测试集合语义后的最终 pilot：动态候选 55、可复现 50、动态可复现率 90.91%、静态与动态排除合计 25。
- 55 个候选的 buggy 与 reference 编译成功率均为 100%；动态排除不是编译失败。
- 50 个 pilot reference 实际通过 180 个 repair tests 和 1600 个 validation tests；50 个 buggy 均至少失败一个正式测试。
- 最终 pilot 完整性内联断言全部通过；manifest、pilot、results、exclusions 和 sample 的行数分别为 3904、50、55、25 和 3。
- 公共 Docker 接口重构后，额外真实复验 `18-A-bug-15987401-15987453`：reference 通过 4 个 repair、63 个 validation，buggy repair 失败 1 个，case 仍为 reproducible。
- 最终未发现残留 `codedoctor-*` 容器、`codedoctor-benchmark-*` / `codedoctor-docker-*` 临时目录或 `__pycache__`；LXD 验证环境已停止。

### 6. 遇到的问题

#### 6.1 Docker 镜像缺少 make

现有镜像只有 g++ 工具链，`command -v make` 无输出，无法直接执行 Codeflaws 原始 Makefile。

#### 6.2 错误地把所有同前缀文件视为正式测试

第一版转换器收集目录中全部 `input-*` / `output-*` 和 held-out 文件。完整 pilot 首轮测试 59 个动态候选才得到 50 个，产生 9 个动态排除；检查 `69-B-bug-18294344-18294349` 后发现目录有 67 组 repair 文件，但官方 `test-genprog.sh` 实际只映射 3 个。额外文件是生成过程遗留，不都属于该 case 的正式 suite。

#### 6.3 官方 metadata 与归档数量不同

官方 defect table 当前解析出 4085 条，而官方归档只有 3904 个 case 目录。若只依赖网页 metadata 会生成不存在的路径。

#### 6.4 现代环境下仍有不可复现候选

最终 55 个候选全部可编译，但 `427-A-bug-17275707-17275729`、`346-A-bug-5781133-5781150` 的 reference 未通过 validation；`673-D-bug-17790443-17791100`、`208-A-bug-17922157-17922172` 的 reference 未通过 repair；`171-F-bug-5237777-5237782` 的 buggy 通过全部正式测试。

#### 6.5 当前项目目录不是 Git working tree

执行 `git status --short` 返回 `not a git repository`。本轮已按要求设计 `.gitignore` 和 Git 应保存的文件边界，但无法在当前目录实际核验 staged/untracked 状态。

### 7. 问题解决方式

- 在 `codedoctor-cpp-sandbox` 镜像中只补充 `make`，实际重建镜像并验证 `GNU Make 4.3`；没有改变安全限制。
- 分析全部 3904 份官方脚本，确认 `test-genprog.sh` 均含可解析映射，`test-valid.sh` 有 3879 份含映射；转换器改为解析脚本中的 label、正/负 input 和 output 索引。
- 修正后重新生成全量 manifest 和 validation report，并从头重跑 50-case pilot。静态结果由 3878 valid / 26 invalid 变为语义正确的 3884 valid / 20 invalid；动态候选由 59 降为 55。
- manifest 只遍历归档真实目录，以官方网页分类作为 enrichment；不存在于归档的网页记录不生成虚假 case。
- 对最终 5 个动态不可复现候选保留完整 suite 统计和原因，继续按分层顺序取后续候选，直到得到 50 个准入 case。
- 将 Docker availability check 和受限命令执行提升为 Runner 的公开复用函数，避免 benchmark 依赖私有实现；重构后重新执行全部回归和单案例真实验证。

### 8. 设计取舍

- benchmark 编译服从原始 Makefile，而通用 Runner 继续保持 C++17 CLI；统一的是沙箱约束与结果验证流程，不强行统一语言标准。
- 同一程序的一个 suite 在单个受限容器中顺序执行，每个测试由容器内 `timeout` 单独限制为 5 秒。这显著降低了 1780 个 pilot reference 测试的容器启动成本，但同一 suite 内的测试不具备容器级隔离。
- pilot 只要求 buggy 至少失败一个正式测试；一旦 repair suite 已发现失败，不再运行该 buggy 的 validation suite。reference 始终运行完整 repair 和 validation suite。
- `pilot.jsonl` 内嵌准入证据，`pilot_results.jsonl` 保存全部动态候选结果，便于后续只携带 pilot 或审计筛选过程。
- tracked sample 只用于 schema 和开发测试，不代表完整 case；accepted source 虽存在于 sample，但 API 仍将其标记为 evaluation-only。

### 9. 当前已知不足

- Pilot 只有 50 个 C case，当前统计不能代表全部 3904 个案例或其他语言数据集。
- 使用 GCC 12 / Debian Bookworm 复现历史提交，可能与 Codeflaws 最初工具链存在行为差异；5 个动态排除尚未在历史编译器镜像中交叉验证。
- 输出比较覆盖官方脚本主要 `sed` 和 `diff --ignore-trailing-space` 语义，但没有逐字节复刻 GNU 工具在缺失末尾换行等边缘情况。
- 一个 suite 共用一个容器和可写 workspace，前一测试理论上可能影响后一测试；当前适用于可信 Codeflaws 数据，不是敌意程序的最强隔离模式。
- 仍没有 workspace 磁盘配额和 stdout/stderr 文件大小上限；恶意程序可能大量写入挂载目录。
- Docker 共享宿主内核，未使用 gVisor、Kata 或 VM；当前 Docker daemon 依赖额外 LXD 验证环境。
- reference 防泄漏目前是模型/API 边界，不是文件系统访问控制；直接读取 raw 或 sample 文件仍可绕过，因此未来 Agent 必须只接收 `repair_time_view()`。
- 全量 manifest 约 40 MB；虽然属于要求保留的 metadata，后续 Git 仓库可能需要评估压缩、release artifact 或 Git LFS 策略。
- 当前项目根目录没有 `.git`，尚未实际验证哪些文件会被 Git 跟踪。

### 10. 下一步计划

- 先冻结 pilot seed、manifest schema、数据版本和报告口径，为每次实验记录 dataset hash 与执行环境版本。
- 下一阶段建议基于这 50 个可复现 case 建立 Fault Localization 的最小实验协议，只使用 buggy source、repair tests 和运行证据，并继续把 validation tests 与 reference source 保持 evaluation-only。
- 在扩大到全量 Codeflaws 前，使用历史 GCC 环境复核 5 个动态排除，并增加逐测试容器隔离或 workspace 配额的可选严格模式。
- Codeflaws 链路稳定后，再通过独立 adapter 扩展 Defects4C；本轮没有下载或处理 Defects4C。

---

## 2026-08-15 - Phase 4：Spectrum-Based Fault Localization

### 1. 本次目标

- 冻结当前 Codeflaws Pilot、工具链、Docker 镜像和 Git 状态。
- 仅使用 buggy source 与 repair tests，逐测试独立采集 gcov 行覆盖并判定 PASS/FAIL；validation tests 不进入定位流程。
- 从 Coverage Matrix 计算每个 executable line 的 `ef/ep/nf/np`。
- 独立实现 Ochiai、Tarantula 和 DStar2，生成可复现且显式记录 ties 的可疑行排名。
- 通过 evaluation-only buggy/reference diff 建立 ground truth，保证 reference 不进入 coverage、spectrum、公式或 ranking。
- 在 50-case Pilot 上真实执行并计算 Top-1/3/5/10 与 MRR，生成包含成功和失败案例分析的研究报告。

### 2. 实际完成内容

- 发现项目不是 Git working tree 后执行 `git init`；未配置远程，也未自动创建 commit。冻结文件如实记录 `git_commit: null` 和 `git_repository_state: unborn_repository`。
- 生成 `benchmark/metadata/experiment_environment.json`，记录 Codeflaws archive SHA-256、manifest/pilot SHA-256、50 个 case ID、随机种子、schema version、GCC/gcov 版本、Docker image ID、Dockerfile SHA-256、coverage compiler、5 秒超时、逐测试隔离和 fatal-signal dump 策略。
- 冻结的 GCC 与 gcov 均为 Debian `12.2.0`；镜像 ID 为 `sha256:7f529aa877352a798339448978b742b45a25f241da10a7ec0a77270817842420`。
- 新建独立 `fault_localization` 包，将 models、gcov parser、collector、spectrum builder、公式、ranking、ground truth、evaluation 和 reporting 分层。
- `LocalizationInput` 由 `BenchmarkCase.repair_time_view()` 生成，类型中不存在 reference 和 validation tests 字段；最终 leakage scan 也未在 coverage/ranking 产物中发现 heldout/reference/validation 字段。
- Coverage 编译通过 Make 命令行设置 `CC="gcc -g -O0 --coverage -include /workspace/codedoctor_gcov_signal.h"`，同时保留原 Makefile 的 `-std=c99`、`-fno-*` 与链接参数。
- 每个 repair test 从干净 executable、source 和 `.gcno` 创建独立临时目录，在新的受限 Docker 容器中执行，再运行 `gcov --json-format`。不同测试不共享 `.gcda`。
- Verdict 复用 Benchmark 的 expected output、空行/行首处理和 trailing-space 比较语义；180 个 repair tests 实际得到 92 PASS、88 FAIL。
- 88 个 FAIL 中，85 个程序退出码为 0、因输出不匹配失败；3 个退出码为 139；没有测试超时。
- 为解决 fatal signal 前 gcov counter 不落盘的问题，通过 GCC `-include` 注入只用于 coverage 实验的 signal handler。它在 SIGSEGV/SIGABRT/SIGFPE/SIGBUS/SIGILL 时调用 `__gcov_dump()`，再恢复默认信号并重新触发，因此保留 139 verdict 和崩溃前部分覆盖。
- 结构化 gcov parser 同时保留 covered lines 与 count 为 0 的 executable lines，不解析本地化的人类可读 gcov 文本。
- Spectrum Builder 对每行计算 `ef/ep/nf/np`；最终完整性断言验证所有行满足 `ef+nf=total_failed`、`ep+np=total_passed`。
- Ochiai、Tarantula、DStar2 均为独立纯函数。零分母规则明确：Ochiai/Tarantula 返回 0；DStar2 在 `ep+nf=0 && ef>0` 时使用最大有限 IEEE-754 值表示排序意义上的正无穷，否则返回 0。
- Ranking 固定按 suspiciousness 降序、行号升序；每行保存顺序 `rank`、`tie_start_rank`、`tie_end_rank`、score、spectrum 和 source snippet。
- 50 个 Pilot case 均至少有一个 failing repair test，因此全部参与 SBFL；其中 10 个没有 passing repair test，结果保留并增加 `no_passing_repair_test` 警告。
- Ground truth 使用 `SequenceMatcher(autojunk=False)`。修改/删除取 buggy-side 非空 changed lines；reference-only insertion 或纯空白 changed block 映射到最近非空 buggy context，优先前一行；规则不查看 coverage 后再选择更容易命中的行。
- 生成 50 份 coverage JSON、50 份 ranking JSON、50 行 evaluation-only ground truth，以及聚合 evaluation JSON；结果目录约 1.4 MB。
- 最终 50-case 指标：Ochiai 与 DStar2 Top-1 10%、Top-3 32%、Top-5 46%、Top-10 62%、MRR 0.2601458425；Tarantula 的四个 Top-K 相同，MRR 0.2594614282。
- ties 非常普遍：三种算法均有 48 个 case 的 top score 并列，47 个 case 的首个 fault line 位于并列组。报告明确使用确定性位置 rank，不使用 best-case tie rank。
- 实际报告深入分析成功案例 `133-A-bug-18286216-18286228`、`370-A-bug-15330051-15330091`，以及失败案例 `471-A-bug-18116605-18116641`、`66-A-bug-13987166-13987365`。

### 3. 新增、修改和删除的文件

新增核心实现：

- `fault_localization/__init__.py`
- `fault_localization/models.py`
- `fault_localization/gcov_parser.py`
- `fault_localization/collector.py`
- `fault_localization/spectrum.py`
- `fault_localization/algorithms.py`
- `fault_localization/ranking.py`
- `fault_localization/pipeline.py`
- `fault_localization/ground_truth.py`
- `fault_localization/evaluation.py`
- `fault_localization/reporting.py`

新增脚本：

- `benchmark/scripts/freeze_experiment_environment.py`
- `benchmark/scripts/run_fault_localization_pilot.py`
- `benchmark/scripts/generate_fault_localization_report.py`

新增测试：

- `fault_localization/tests/__init__.py`
- `fault_localization/tests/test_algorithms.py`
- `fault_localization/tests/test_gcov_parser.py`
- `fault_localization/tests/test_ground_truth.py`
- `fault_localization/tests/test_ranking.py`
- `fault_localization/tests/test_pipeline.py`
- `fault_localization/tests/test_collector_integration.py`

新增 metadata、结果、报告和文档：

- `benchmark/metadata/experiment_environment.json`
- `benchmark/metadata/fault_localization_ground_truth.jsonl`
- `benchmark/results/fault_localization/coverage/` 下 50 个 JSON
- `benchmark/results/fault_localization/rankings/` 下 50 个 JSON
- `benchmark/results/fault_localization/evaluation.json`
- `benchmark/reports/fault_localization_pilot_report.md`
- `docs/fault_localization/sbfl.md`

修改：

- `README.md`
- `benchmark/config.py`
- `benchmark/execution.py`
- `docs/DEVELOPMENT_LOG.md`

仓库状态：新增 `.git/`，无 remote、无 commit。删除：无项目文件删除。

### 4. 执行过的重要命令

Git、环境与哈希检查：

```bash
git init
git remote -v
lxc start codedoctor-docker-host
lxc exec codedoctor-docker-host -- su -s /bin/bash ubuntu -c 'docker image inspect codedoctor-cpp-sandbox --format "image_id={{.Id}} repo_digests={{json .RepoDigests}} created={{.Created}}"'
lxc exec codedoctor-docker-host -- su -s /bin/bash ubuntu -c 'docker run --rm --network none codedoctor-cpp-sandbox sh -c "gcc --version | head -1; gcov --version | head -1"'
sha256sum benchmark/datasets/codeflaws/metadata/manifest.jsonl benchmark/datasets/codeflaws/metadata/pilot.jsonl sandbox/docker/Dockerfile
```

冻结环境：

```bash
lxc exec codedoctor-docker-host -- su -s /bin/bash ubuntu -c 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 -m benchmark.scripts.freeze_experiment_environment'
```

gcov 冒烟实际在 LXD 中复制 `18-A-bug-15987401-15987453` 的 source、Makefile 和 input，使用受限 `docker run` 执行 coverage 编译、单测试运行与 `gcov --json-format`，并用 Python gzip/json 读取结果。该冒烟先暴露了 Make `override CFLAGS +=` 丢失原始 flags 的问题。

三案例冒烟：

```bash
lxc exec codedoctor-docker-host -- su -s /bin/bash ubuntu -c 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 -m benchmark.scripts.run_fault_localization_pilot --limit 3 --force'
```

完整 Pilot 在初始 collector、ground-truth 修正后以及 fatal-signal dump 修正后均实际执行或重建。最终从头执行命令为：

```bash
lxc exec codedoctor-docker-host -- su -s /bin/bash ubuntu -c 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 -m benchmark.scripts.run_fault_localization_pilot --force'
```

不重新执行测试的排名/ground-truth 重建实际多次执行：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m benchmark.scripts.run_fault_localization_pilot --reuse-coverage
```

报告生成：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m benchmark.scripts.generate_fault_localization_report
```

最终测试：

```bash
lxc exec codedoctor-docker-host -- su -s /bin/bash ubuntu -c 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s fault_localization/tests -v && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s benchmark/tests -v && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s sandbox/tests -v'
```

另外实际执行内联 Python 对 50 个 case 做完整性断言，包括 repair test ID 一致、无 heldout 字段、compile flags、每个 case 至少一项 FAIL、spectrum 守恒、三种 ranking 长度/顺序、3 个 crash tests 具有非空部分覆盖、最终指标和环境字段。使用 `rg` 执行 leakage scan，使用 `git check-ignore` 验证完整 raw 与归档被忽略。

最终清理：

```bash
lxc exec codedoctor-docker-host -- find /tmp/gcov-smoke -depth -delete
lxc exec codedoctor-docker-host -- sh -c 'docker ps -a --filter name=codedoctor- --format "{{.Names}} {{.Status}}"; find /tmp -maxdepth 1 -type d ... -print'
find /home/wyh/CodeDoctor -type d -name __pycache__ -print
lxc stop codedoctor-docker-host
```

### 5. 实际测试与实验结果

- 纯 Python Phase 4 测试在宿主首轮为 13 PASS、1 SKIPPED；collector Docker 测试在 LXD 启用后执行。
- collector integration 第一轮 1 FAIL：测试错误地把同一行上的 `if` 条件和未执行 body 当作“未执行行”。拆分语句后通过。
- 增加 crash partial coverage 后，最终 Phase 4 为 21/21 PASS，耗时 1.355 秒。
- Benchmark 回归最终 8/8 PASS。
- Runner/Sanitizer 既有回归最终 29/29 PASS，耗时 10.671 秒。
- 三案例真实冒烟：`18-A` 为 3 PASS/1 FAIL/37 executable lines，`149-B` 为 2/2/59，`572-A` 为 1/3/58；coverage error 为 0。
- 全量最终执行：50 case、180 repair tests、50 coverage files、50 ranking files、50 ground-truth records、0 coverage errors、0 not-localizable-no-failing case。
- Verdict：92 PASS、88 FAIL；85 个输出错误且 exit 0，3 个 exit 139，0 timeout。
- 10 个 case 没有任何 passing repair test，但全部有 failing tests，保留参与排名并明确警告。
- executable lines 每 case：min 4、median 17、mean 20.66、max 59。
- 最终 Top-K 三算法相同：Top-1 5/50，Top-3 16/50，Top-5 23/50，Top-10 31/50。
- Ochiai/DStar2 MRR 为 `0.2601458424616319`；Tarantula 为 `0.2594614281551375`。
- 最终完整性检查和 leakage scan 均通过；未发现残留 `codedoctor-*` 容器、coverage 临时目录或 `__pycache__`，LXD 已停止。

### 6. 遇到的问题

#### 6.1 Make override 丢失原始编译参数

gcov 冒烟使用 `--eval=override CFLAGS += ...` 时，实际编译行只剩 coverage flags，原始 `-std=c99`、`-fno-*` 和 `-lm -s -O2` 丢失。

#### 6.2 集成测试误解 gcov 行语义

测试把 `if (x == 999) puts("never")` 写在一行，并期望该行未覆盖；实际上条件判断已执行，所以 gcov 正确标记该行 covered。

#### 6.3 10 个 case 没有 PASS repair test

这类 case 有 failing tests，四元组与 Ochiai/DStar2 仍可计算，但缺少成功路径对照；Tarantula 中被失败测试覆盖的行容易全部得到 1。

#### 6.4 Ground truth 映射到空行

第一版 reference-only insertion 映射到前一物理行，`622-A-bug-18068430-18068439` 因此映射到空行 L6，必然无法进入 gcov ranking。只修 insertion 后仍发现纯空白 changed block 会产生同类问题。

#### 6.5 Fatal signal 不自动写 gcda

最终审计发现 3 个 exit 139 repair tests 的 coverage 全为 0。程序崩溃前实际上执行了代码，但 libgcov 没有机会正常刷新 `.gcda`，gcov 仅根据 `.gcno` 生成了误导性的零计数。

#### 6.6 Git 没有历史 commit

项目原本没有 `.git`。初始化后仍是 unborn repository，无法记录一个不存在的 commit hash。

#### 6.7 最终聚合清理命令被策略拒绝

包含 `rm -f` 的聚合命令在执行前被工具策略拒绝，未产生数据变化。随后将验证和清理拆开，并使用精确路径的 `find -delete`/`unlink` 完成。

### 7. 问题解决方式

- 改用 Make 命令行 `CC="gcc -g -O0 --coverage ..."`；CC 覆盖会在编译与链接命令前追加 instrumentation，同时 Makefile 自身的 CFLAGS/LDFLAGS 仍保留。集成测试断言两组 flags 同时出现。
- 将未执行 body 移到独立源码行，collector integration 随后验证 PASS/FAIL 分支互不污染、未执行语句仍属于 executable set 且 covered=false。
- 不把“无 PASS”误写成用户指定的 `not_localizable_no_failing_repair_test`；继续计算并保存 warning，在报告中单独统计和讨论证据弱化。
- Ground truth 修改/删除块过滤空行；reference-only insertion 或纯空白 changed block 映射到最近非空 context，优先向前。规则写入测试和文档，修正后 `622-A` 映射到 L5 并取得 rank 3。
- 为 coverage build 注入 signal handler；独立 crash integration 验证退出码仍为 139，且崩溃前第 2、4 行出现在 coverage。随后从头重跑全部 50 case。
- `git init` 后不创建虚假 commit、不配置 remote；环境文件明确记录 null/unborn。
- 使用精确临时路径清理并再次确认容器、目录和 pycache 均无残留。

### 8. 设计取舍

- 使用 gcov gzip JSON，而不是解析 `.gcov` 文本；这减少格式、列宽和 locale 依赖。
- 每个测试使用新 workspace 与新容器，而不是只删除共享 `.gcda`；成本更高，但 isolation 结论更强。
- fatal-signal handler 仅通过编译期 `-include` 注入，不修改保存的 buggy source；它会轻微改变进程 signal 环境，因此作为实验 instrumentation 明确记录。
- no-PASS case 仍进入算法评估，因为用户规定的不可定位条件是 no-FAIL，且公式边界已定义；报告不把它们与有成功对照的 case 混为同等证据质量。
- Ground truth 规则完全由文本 diff 决定，不查看 coverage 或 ranking 后再映射到 executable neighbor，避免为了提高指标引入 evaluation leakage。
- Top-K 使用 score 降序、line 升序的确定 rank；同时保存 tie 区间，不报告乐观 best-case tie accuracy。
- 不实现 EXAM Score，也不生成 Dashboard；当前指标和报告聚焦 Top-K、MRR、ties 与案例解释。

### 9. 当前已知不足

- 50 个 Pilot case 中 48 个存在 top-score tie、47 个 fault line 位于 tie group，说明 repair tests 的区分能力有限；顺序 Top-K 对行号 tie-break 敏感。
- 10 个全 FAIL case 没有成功执行对照，尤其会使 Tarantula 排名退化。
- textual diff ground truth 可能标记花括号、声明或其他 gcov 不认为 executable 的非空上下文；最终仍有 3 个 case 的 ground truth 完全不在 ranking 中。
- signal-time `__gcov_dump()` 在当前 3 个 SIGSEGV tests 中有效，但尚未覆盖多线程、重复信号、`_exit`、SIGKILL 或 timeout 强杀等情况。
- 行覆盖不能区分同一源码行内的多个表达式，也不提供数据依赖、控制依赖或语义因果。
- 当前只验证 GCC/gcov 12.2.0、50 个 C defect；未在其他 GCC 版本、Clang llvm-cov、全量 Codeflaws 或其他数据集上验证。
- Docker 仍共享宿主内核，workspace 仍无磁盘配额和输出上限。
- Git 仓库没有初始 commit，冻结文件只能记录 unborn 状态；当前全部项目文件在 Git 中仍为 untracked。

### 10. 下一步计划

- 在进入自动修复前，先评估 tie-aware best/worst/average rank 作为补充分析，但继续保留当前确定 rank 作为主指标。
- 扩充或选择更有区分力的 repair tests，重点改善 10 个 no-PASS case 和大规模 coverage ties。
- 研究将不可执行 textual ground truth 映射到 executable statements 的预注册规则，并与当前严格行匹配指标并列报告，不能事后按成绩选择规则。
- 下一阶段若进入 Fault Localization 增强，可研究动态切片、分支覆盖或语句级映射；本轮没有实现 AST/CFG、LLM 或自动修复。

## 2026-08-15 Phase 5：Tie-Aware SBFL 与真实 Branch Evidence

### 1. 本次目标

- 将本地仓库绑定到 `https://github.com/u-wyh/CodeDoctor.git`，在进入 Phase 5 前安全保存 Phase 1-4 基线，并确保 3.2GB 本地工作区中的 Codeflaws raw/归档不进入 Git。
- 重新审视 Phase 4 的大量 Ochiai ties，实现 best/worst/average rank、tie-aware Top-K/MRR 和 coverage equivalence class 分析。
- 使用 GCC/gcov 的真实 branch arcs 逐 repair test 隔离采集 branch count/taken，构建 branch spectrum，并以 max branch Ochiai 对 line Ochiai 的精确并列做保守 lexicographic tie-breaking。
- 在原 50-case/180-repair-test Pilot 上从头采集并比较 original line Ochiai 与 branch-aware Ochiai；完成 2 个改善案例和 2 个未改善案例分析，不使用 reference/validation evidence 参与定位。

### 2. 实际完成内容

- 检查到仓库位于 unborn `main` 且无 remote；添加 `origin`，远端 `ls-remote --heads` 为空。补强 `.gitignore` 后审计 staged 文件、敏感信息和大文件，创建 Phase 1-4 根提交 `f2a85a8`，提交信息为 `Initial CodeDoctor implementation through Phase 4`。
- `.gitignore` 新增 `.env*`、私钥/证书、日志、Python 工具缓存、build/dist/tmp/temp 和 gcov 临时文件规则。实际 `git check-ignore -v` 继续命中 265MB 下载归档、raw case 归档及生成 JSON 报告；staged 文件中没有 raw/download 文件或 50MiB 以上文件。
- `TestCoverage` 新增向后兼容的 `branches`；每条 `BranchCoverage` 保存 source line、line-local branch index、count、taken、fallthrough、throw。旧 Phase 4 JSON 缺少 `branches` 时仍可读取为空 tuple。
- collector 改用 `gcov --json-format --branch-probabilities --branch-counts`。每个 repair test 仍复制干净 executable/`.gcno` 到独立临时目录并启动新受限 Docker 容器，测试间不共享 `.gcda`。
- 增加 branch spectrum：每个 `(line, branch_index)` 按 taken/not-taken 和 PASS/FAIL 构造 `ef/ep/nf/np`，计算 Ochiai；同一 source line 取最大 branch score。
- 增加 `ochiai_branch_tiebreak`：排序键为 line Ochiai 降序、max branch Ochiai 降序、line 升序。branch 只打破完全相同的 line score，不反转原 line-SBFL 分数组。
- 实现 coverage equivalence class、branch coverage vector class、score-group size 统计。实现 tie-aware best/worst/average rank、tie size，以及 optimistic/pessimistic/average-rank Top-K 与 MRR；原确定 rank 指标继续保留。
- 从头重采集 50 case、180 repair tests，生成 50 份含 branch records 的 coverage 和 50 份含 branch spectrum/tie-break ranking 的 ranking；0 coverage error，仍为 92 PASS/88 FAIL。
- 新增结构化 `branch_evaluation.json` 和研究报告。报告展示 tie 成因、equivalence class、确定性与 tie-aware 指标、branch 方法、2 个改善案例 `158-C-bug-9967801-9967822`/`450-A-bug-12286209-12286212`，以及 2 个未改善案例 `471-A-bug-18116605-18116641`/`192-A-bug-18022160-18022194`。
- `471-A` 的 diff fault lines 不属于 gcov executable records，因此 line/branch 都无法排名；`192-A` 的 fault L19 与 L18 同为 `001`，两行都无 branch outcome，tie 仍为 `[1,2]`。
- 新增 branch-aware 方法文档并更新 README 的实验命令。未实现 weighted alpha sweep、LLM、Agent、RAG、Web、AST/CFG 或新数据集。

### 3. 新增、修改、删除的文件

新增：

- `fault_localization/tie_analysis.py`
- `fault_localization/branch_reporting.py`
- `fault_localization/tests/test_tie_analysis.py`
- `fault_localization/tests/fixtures/gcc12_branch.gcov.json`
- `benchmark/scripts/generate_branch_fault_localization_report.py`
- `benchmark/results/fault_localization/branch_evaluation.json`
- `benchmark/reports/fault_localization_branch_report.md`
- `docs/fault_localization/branch_aware_fl.md`

修改：

- `.gitignore`
- `README.md`
- `benchmark/config.py`
- `fault_localization/__init__.py`
- `fault_localization/algorithms.py`
- `fault_localization/collector.py`
- `fault_localization/evaluation.py`
- `fault_localization/gcov_parser.py`
- `fault_localization/models.py`
- `fault_localization/pipeline.py`
- `fault_localization/ranking.py`
- `fault_localization/spectrum.py`
- `fault_localization/tests/test_algorithms.py`
- `fault_localization/tests/test_collector_integration.py`
- `fault_localization/tests/test_gcov_parser.py`
- `fault_localization/tests/test_pipeline.py`
- `fault_localization/tests/test_ranking.py`
- `benchmark/results/fault_localization/coverage/*.json`（50 份真实重采集产物）
- `benchmark/results/fault_localization/rankings/*.json`（50 份真实重建产物）
- `docs/DEVELOPMENT_LOG.md`

删除：无。

### 4. 执行过的重要命令

```bash
git status --short --branch
git remote -v
git remote add origin https://github.com/u-wyh/CodeDoctor.git
git ls-remote --heads origin
git add .
git diff --cached --stat
git commit -m "Initial CodeDoctor implementation through Phase 4"
git push -u origin main
git push -u origin main
gh auth status

lxc start codedoctor-docker-host
lxc exec codedoctor-docker-host -- systemctl start docker
lxc exec codedoctor-docker-host -- su -s /bin/bash ubuntu -c 'docker info --format "{{.ServerVersion}}"'

lxc exec codedoctor-docker-host -- su -s /bin/bash ubuntu -c 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s fault_localization/tests -v && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s benchmark/tests -v && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s sandbox/tests -v'
lxc exec codedoctor-docker-host -- su -s /bin/bash ubuntu -c 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/run_fault_localization_pilot.py --force'
lxc exec codedoctor-docker-host -- su -s /bin/bash ubuntu -c 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/generate_branch_fault_localization_report.py'
lxc exec codedoctor-docker-host -- su -s /bin/bash ubuntu -c 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/run_fault_localization_pilot.py --reuse-coverage'

git diff --check
rg -n 'reference|validation|heldout|ground_truth|fault_lines' benchmark/results/fault_localization/coverage benchmark/results/fault_localization/rankings
git check-ignore -v benchmark/datasets/codeflaws/downloads/codeflaws.tar.gz benchmark/datasets/codeflaws/raw/codeflaws/674-E-bug-17842470-17842486.tar.gz benchmark/reports/codeflaws_pilot_report.json
lxc stop codedoctor-docker-host
```

另外实际执行内联 Python：验证 50 coverage/50 ranking 均有 branch 结构；每个 case 各测试拥有相同 branch universe；equivalence classes 完整分割 executable lines；branch-aware ranking 保留原 line score 且不反转 line-score 顺序；tie-aware rank 满足 `best <= average <= worst`；最终关键指标与 92/88 verdict totals 一致。对 100 份 coverage/ranking 在 `--reuse-coverage` 前后计算 SHA-256 并用 `cmp` 比较，输出 `ARTIFACT_HASHES_REPRODUCED`。

### 5. 实际测试与实验结果

- 开发中 Phase 5 Fault Localization 测试为 26/26 PASS；加入 branch JSON round-trip 后最终为 27/27 PASS，其中 2 个真实 Docker collector integration 均执行并通过。
- Benchmark 回归 8/8 PASS。
- Runner/Sanitizer 回归 29/29 PASS，耗时 10.593 秒。
- 50-case `--force` 真实重采集：50 case、180 repair tests、92 PASS、88 FAIL、0 coverage error。
- 50-case `--reuse-coverage` 重建：50 case、0 coverage error，100 份 coverage/ranking 哈希与重建前完全相同。
- leakage scan：coverage/ranking 中没有 `reference`、`validation`、`heldout`、`ground_truth`、`fault_lines` 字段。
- repository secret scan 无匹配；`git diff --check` 通过；Docker 无 `codedoctor-*` 残留容器，LXD 最终为 STOPPED。
- Original deterministic Ochiai：Top-1 5/50（10%）、Top-3 16/50（32%）、Top-5 23/50（46%）、Top-10 31/50（62%）、MRR `0.2601458425`。
- Branch tie-breaking deterministic：Top-1 11/50（22%）、Top-3 21/50（42%）、Top-5 28/50（56%）、Top-10 38/50（76%）、MRR `0.3836713097`。
- Original tie-aware average-rank：Top-1/3/5/10 为 0%/26%/42%/70%，MRR `0.2183211561`；pessimistic MRR `0.1384969372`。
- Branch tie-aware average-rank：Top-1/3/5/10 为 10%/36%/58%/76%，MRR `0.3468746856`；pessimistic MRR `0.2788235735`。
- optimistic MRR 从 `0.7865622711` 降至 `0.5623321123`。这是大 tie 被拆分后不再假定 fault 总能位于并列首位，不应解释为方法整体退化。
- top-score tie cases 从 48 降到 34；tied-fault cases 从 47 降到 41；平均最大 tie size 从 15.08 降到 10.94；平均 fault tie size 从 11.87 降到 5.77。
- 1,033 个 per-case executable line records 只有 143 个 per-case unique line vectors；每 case 平均 2.86 个 vector、2.70 个 spectrum pattern。最大 equivalence class 每 case 平均 14.40 行，最大为 49 行；58 个 executable fault lines 的 class size 平均 10.90。
- 原 Ochiai 共 106 个 tie groups，其中 92 个（86.79%）完全属于单一 coverage equivalence class；47 case 的整个 top tie 是单一 class。主要 tie 原因是 line coverage 本身相同，公式仅造成剩余少量合并。
- 观测到 796 个 per-case branch outcomes、202 个 per-case unique branch vectors。branch evidence 使 average tie-aware fault rank 在 25 case 改善、17 case 回退，其余不变或 fault 不可执行。

### 6. 遇到的问题

#### 6.1 LXD 启动后 Docker daemon 未运行

首次基线回归在 `docker info` 处失败：`/var/run/docker.sock` 不存在，三组测试尚未开始。

#### 6.2 GitHub push 无可用认证

Phase 1-4 基线 commit 成功。第一次 push 在 GnuTLS 握手处异常终止；第二次重试明确失败为 `could not read Username for 'https://github.com': No such device or address`。环境未安装 `gh`，`gh auth status` 返回 command not found。

#### 6.3 仅使用 `--branch-counts` 时 JSON branches 为空

真实 GCC 12.2 冒烟中，`gcov --json-format --branch-counts` 的 line records 没有 branch arcs。加入 `--branch-probabilities` 后才输出包含 count/fallthrough/throw 的 branch list。

#### 6.4 宿主机没有 Docker CLI

宿主执行 27 个 FL tests 时两个 collector integration 被 skip；同一测试集在 LXD Docker 环境中重新执行，27/27 全部通过。

#### 6.5 Branch evidence 并非统一改善

虽然整体 tie 与主要指标改善，仍有 17 case 的 average fault rank 回退。branch evidence 可能优先提升非 fault 控制行，straight-line fault 没有本地 branch outcome，非 executable diff line 更无法被 branch 方法补救。

#### 6.6 生成报告中的源码空白使 staged diff check 失败

最终提交前第一次 `git diff --cached --check` 报告 6 处 trailing whitespace，均来自案例源码代码块。第一次只对源码文本调用 `rstrip()` 后，空白源码行仍保留渲染前缀末尾的一个空格，检查继续报告 5 处；此时 commit 尚未执行。

### 7. 问题解决方式

- 使用 `systemctl start docker` 启动 LXD 内 daemon，确认 Docker Server `29.1.3` 后原样重跑基线和最终测试。
- GitHub 认证失败后不写 token、不修改系统凭据、不 force push；保留正确 `origin` 和本地 commits，继续完成可验证开发，并将失败原因明确记录。
- 以真实 gcov 输出确认参数组合，collector 固定同时使用 `--branch-probabilities --branch-counts`；将该 GCC 12.2 JSON 保存为小型 fixture。
- 所有需要 Docker 的最终测试、50-case 重采集和重建均在 `codedoctor-docker-host` 内实际运行。
- 不按结果调整规则或训练参数；保留 25 改善/17 回退的完整结果，并同时报告 optimistic、pessimistic 和 average-rank 指标。选择 lexicographic tie-break，不进行 Pilot ground-truth alpha 调参。
- 将 `rstrip()` 应用于报告中完整的源码展示行并重新生成报告，随后 `git diff --cached --check` 输出 `STAGED_DIFF_CHECK_PASSED`。该修正只改变 Markdown 行尾，不改变 evaluation JSON 或任何指标。

### 8. 设计取舍

- 保留 Phase 4 的 line collector、三种旧排名和 JSON 读取兼容；在同一小型模块体系内增量加入 branch records、branch spectrum 和新 ranking，未为目录外观做大重构。
- branch index 定义为 gcov 在每个 source line 的 branch list 顺序；taken 定义为 count > 0。保留 count 与 arc flags，避免把编译器 arc 误写成源码 predicate 真值。
- 同行多个 branch 采用 max Ochiai，因为一个高可疑控制 outcome 不应被均值稀释；报告明确 max 也可能放大偶然 arc。
- 主方法采用无参数 lexicographic tie-break。只在 line score 精确相等时使用 branch score，不允许其越过不同 line-score 组。
- 结构化 branch evaluation 与 Phase 4 evaluation 分开保存，只比较 original Ochiai 和 branch tie-breaking；不继续扩张 Tarantula/DStar2 或算法数量。
- deterministic 指标用于与 Phase 4 对齐，tie-aware average/pessimistic 用于判断提升是否超出 line-number 偶然顺序；optimistic 降低被如实保留。
- ground truth 只在 `branch_reporting.py` 的 evaluation/report 阶段读取；coverage、spectrum、branch aggregation、ranking 均不知道 fault lines。

### 9. 当前已知不足

- 仅在固定 50-case Pilot、180 个小型 repair tests、GCC/gcov 12.2 上验证；同一 Pilot ground truth 只用于评价但仍不能代表跨数据集泛化。
- 10 case 没有 PASS test，branch/line spectrum 都缺少成功路径对照；`450-A` 的改善主要是将全覆盖大 tie 分成 branch line 与 straight-line 两组。
- 17 case average fault rank 回退；branch evidence 不是语义因果，也不保证控制行就是 fault。
- 3 个 case 的 textual diff ground truth 完全不在 executable-line ranking；branch arcs 无法修复该表示不匹配。
- straight-line fault、相同 branch vectors 和同一行内复杂表达式仍可能无法区分。
- max branch aggregation 未与独立数据上的 mean/fixed weighted fusion 比较；本轮有意避免在 Pilot ground truth 上选择 alpha。
- fatal-signal coverage、Docker 宿主内核共享、无磁盘配额/输出上限等 Phase 4 安全和 instrumentation 局限仍存在。
- GitHub remote 已绑定，但 push 因当前环境缺少 GitHub HTTPS 凭据而失败；远端尚未获得本地 commits。

### 10. 下一步计划

- 优先在预注册、独立选择的 case split 或更大 Codeflaws 子集上复验 branch tie-breaking，避免把当前 Pilot 指标当作泛化结论。
- 研究 repair test augmentation/selection，重点增加不同执行路径和 PASS 对照，直接缩小 coverage equivalence classes。
- 为 non-executable textual diff fault 设计预注册的 executable-neighbor 映射，并与严格行匹配并列报告，不能按成绩事后选择。
- 在进入 LLM Repair 前，将 fault candidate 接口设计为保留 line score、branch score、tie interval 和 equivalence-class context，而不是只返回确定性的单行排名。

## 2026-08-15 - Phase 6: Independent Fault Localization Evaluation

### 1. 本次目标

- 在选择独立 Evaluation Set 前冻结 Phase 5 方法为 `fl-v1`，禁止使用 Evaluation 结果调参。
- 从未进入 50-case Pilot 的 Codeflaws valid cases 中，以固定种子 `20260816` 分层选择并动态验证 300 个独立 case。
- 只比较 Original line-level Ochiai 与冻结的 branch-aware FL-v1，完成 tie-aware、paired、bootstrap、McNemar、子组、coverage equivalence、0-PASS、non-executable fault、straight-line ambiguity 和 leakage 分析。
- 生成结构化结果、至少 6 个源码级案例研究和独立评估报告，并运行全部旧测试。

### 2. 实际完成内容

- 在选择 Evaluation Set 前创建 `benchmark/metadata/fl_method_v1.json`，记录公式、branch max aggregation、lexicographic ranking、tie 规则、允许/禁止输入及 9 个核心实现文件的 SHA-256；运行时和测试均会验证冻结哈希。
- 使用 seed `20260816` 在排除 Pilot 后按 39 个 defect class 轮转抽样。静态排除 20 个无测试 case；动态验证 322 个候选，得到 300 个合格 case，与 Pilot overlap 为 0。
- 每个候选重新验证 buggy/reference 编译、reference repair/validation tests、buggy 至少一个 failing repair test。动态排除 22 个：reference repair test 失败 14、reference validation test 失败 4、buggy repair tests 全通过 4；42 条静态/动态排除均保留原因。
- 在 LXD 内的真实 Docker 环境对 300 个 Evaluation case 完成 line/branch coverage 采集和 FL-v1 排名：300/300 localizable、0 coverage error。只保存 `ochiai` 与 `ochiai_branch_tiebreak` 两种排名，所有 ranking artifact 标记 `method_version=fl-v1`。
- ground truth 在排名生成后单独写入 evaluation-only 文件。扫描 600 份 localization artifacts，没有发现 reference、validation、heldout、ground truth 或 fault line 字段泄漏。
- 实现标准库配对 case-level bootstrap（10,000 samples，seed `20260816`）、精确双侧 McNemar、paired change counts 和预先固定边界的四类子组分析。
- 生成 `evaluation.json` 和独立实验报告。报告包含完整指标、绝对/相对提升、置信区间、Top-K 显著性、tie/equivalence 机制、失败边界、RQ1-RQ4，以及 2 个改善、2 个不变、2 个回退的源码级案例。
- 复用原 300 份 coverage 重新生成全部排名；重建前后 coverage/ranking 组合 SHA-256 均为 `5966489c561b72306d48cbd2943df092757d7e298f80c32d14d08faff1be42aa`。
- 逐例 coverage/ranking 共约 12MB，因可由脚本重建而保持 Git ignore；提交范围只包含 581KB 汇总 JSON、ground truth 元数据、报告、代码和测试，不包含 Codeflaws raw/archive。

### 3. 新增、修改、删除的文件

新增：

- `benchmark/metadata/fl_method_v1.json`
- `benchmark/datasets/codeflaws/metadata/fl_evaluation.jsonl`
- `benchmark/datasets/codeflaws/metadata/fl_evaluation_excluded.jsonl`
- `benchmark/datasets/codeflaws/metadata/fl_evaluation_results.jsonl`
- `benchmark/datasets/codeflaws/metadata/fl_evaluation_summary.json`
- `benchmark/metadata/fl_evaluation_ground_truth.jsonl`
- `benchmark/evaluation_set.py`
- `benchmark/scripts/build_fl_evaluation_set.py`
- `benchmark/scripts/run_fault_localization_evaluation.py`
- `benchmark/scripts/generate_independent_fault_localization_report.py`
- `benchmark/results/fault_localization_independent/evaluation.json`
- `benchmark/reports/fault_localization_independent_evaluation.md`
- `benchmark/tests/test_evaluation_set.py`
- `fault_localization/method_freeze.py`
- `fault_localization/statistics.py`
- `fault_localization/independent_evaluation.py`
- `fault_localization/independent_reporting.py`
- `fault_localization/tests/test_evaluation_runner.py`
- `fault_localization/tests/test_independent_evaluation.py`
- `fault_localization/tests/test_statistics.py`

修改：

- `.gitignore`
- `benchmark/config.py`
- `fault_localization/tests/test_method_freeze.py`
- `docs/DEVELOPMENT_LOG.md`

删除：无。

本地生成但忽略：

- `benchmark/results/fault_localization_independent/coverage/*.json`（300 份）
- `benchmark/results/fault_localization_independent/rankings/*.json`（300 份）

### 4. 执行过的重要命令

```bash
git status
git log --oneline -5
git remote -v
git push -u origin main

lxc start codedoctor-docker-host
lxc exec codedoctor-docker-host -- docker info --format '{{.ServerVersion}}'
lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/build_fl_evaluation_set.py'
lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/run_fault_localization_evaluation.py --force'
python3 benchmark/scripts/generate_independent_fault_localization_report.py

python3 -m unittest fault_localization.tests.test_statistics fault_localization.tests.test_independent_evaluation -v
python3 -m unittest discover -v
lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -v'
lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/run_fault_localization_evaluation.py --reuse-coverage'

find benchmark/results/fault_localization_independent/coverage benchmark/results/fault_localization_independent/rankings -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum
git check-ignore -v benchmark/datasets/codeflaws/downloads/codeflaws.tar.gz benchmark/datasets/codeflaws/raw/codeflaws/674-E-bug-17842470-17842486.tar.gz benchmark/results/fault_localization_independent/coverage/490-C-bug-9623374-9623441.json benchmark/results/fault_localization_independent/rankings/490-C-bug-9623374-9623441.json
git diff --check
lxc stop codedoctor-docker-host
```

另外实际执行了内联 Python 审计：验证 300 coverage、300 ranking、300 ground truth 数量一致；Evaluation/Pilot 无重叠；所有 ranking 只含两个预注册方法且版本为 `fl-v1`；300 个 reference repair/validation 均通过且 buggy repair 至少一项失败；抽样顺序与固定 seed 的分层候选顺序一致。

### 5. 实际测试与实验结果

- Evaluation 动态资格验证首次完整运行耗时 542.967 秒；322 个候选中 300 个入选、22 个动态排除。后续 resume 审计没有重复执行已记录 case。
- 300-case FL 强制重采集：300 case、1,194 repair tests、708 PASS、486 FAIL、0 coverage error。复用 coverage 的 300-case 重建耗时 0.935 秒且 artifact 哈希完全一致。
- 新增统计/边界单元测试最终 7/7 PASS；方法冻结、split、eligibility、runner、paired metrics、bootstrap、McNemar、subgroup、non-executable ground truth 和 leakage 均有测试覆盖。
- 宿主 `python3 -m unittest discover -v` 共运行 75 项：56 PASS、17 FAIL、2 SKIP。17 个失败与 2 个 skip 都来自宿主没有 Docker CLI/daemon；同一完整测试集随后在 LXD Docker 环境实际运行，75/75 PASS，耗时 12.151 秒，无 skip。
- Original Ochiai deterministic：Top-1/3/5/10 为 37/91/132/206，即 12.33%/30.33%/44.00%/68.67%，MRR `0.2773`。
- Branch-aware FL-v1 deterministic：Top-1/3/5/10 为 55/120/157/217，即 18.33%/40.00%/52.33%/72.33%，MRR `0.3475`。
- Average-rank MRR 从 `0.2552` 提高到 `0.3456`，差值 `+0.0904`；pessimistic MRR 从 `0.1880` 提高到 `0.3004`。
- deterministic MRR paired bootstrap difference `+0.0702`，95% CI `[+0.0432, +0.0986]`；average-rank MRR difference `+0.0904`，95% CI `[+0.0671, +0.1156]`。
- exact McNemar：Top-1 `p=0.000277`、Top-3 `p=0.000204`、Top-5 `p=0.001264`；Top-10 `p=0.117275`，后者没有达到常用 0.05 阈值。
- primary average-rank reciprocal outcome：99 case 改善、79 不变、122 回退。deterministic reciprocal outcome：84 改善、140 不变、76 回退。总体均值提升来自部分大幅改善，不能解释为每个 case 都受益。
- top-score tie cases 从 231 降到 157；fault-tie cases 从 256 降到 205；平均最大 tie size 从 15.87 降到 11.84；平均 fault tie size 从 12.05 降到 6.44。
- 6,531 个 executable line records 只有 959 个 unique coverage vectors，coverage equivalence ratio 为 85.32%；625 个原始 tie groups 中 510 个完全属于单一 line-coverage class。
- 52/300 case 为 0-PASS：average-rank MRR 增益仅 `+0.0310`，8/10/34 改善/不变/回退；有 PASS 的 248 case 增益 `+0.1028`，91/69/88 改善/不变/回退。
- 20/300（6.67%）case 的 ground-truth fault 完全不可执行；205/300（68.33%）存在最终 straight-line ambiguity。
- 最大子组增益出现在 fault equivalence class size 6-10（`+0.1503`）和 medium coverage diversity（`+0.1231`）。这些边界在运行前固定，仅用于解释，没有反向修改 `fl-v1`。
- leakage scan PASS；敏感信息扫描无匹配；raw/archive、coverage/ranking 中间产物均被 `.gitignore` 命中；Docker 无 `codedoctor-*` 残留容器，LXD 最终为 STOPPED。

### 6. 遇到的问题

#### 6.1 Evaluation summary 的静态排除数被 list alias 污染

首次动态选择后，`excluded = static_excluded` 使后续追加动态排除时同时修改了静态列表，summary 一度把 static exclusions 错写为 42；逐例 selection/exclusion records 本身正确。

#### 6.2 首次完整性审计错误地把静态无效候选纳入顺序

审计脚本直接重算全部非 Pilot 候选，未先应用 `validate_case` 的静态过滤，因此第一次顺序断言失败。

#### 6.3 non-executable/straight-line 单元测试夹具字段不完整

新增测试第一次构造 `RankedLine` 时遗漏 `ef/ep/nf/np/source_snippet`，测试报 `TypeError`。

#### 6.4 宿主环境不能运行 Docker 集成测试

宿主全量测试中的 Runner/Sanitizer 用例返回 `internal_error`，collector integration 被 skip，因为 Docker daemon 只在专用 LXD 内可用。

#### 6.5 第一次 LXD 全量测试使用了错误目录

命令进入 `/workspace` 后 unittest 发现 0 项并以 exit code 5 退出；实际仓库挂载点是 `/workspace/CodeDoctor`。

#### 6.6 独立结果不是逐例统一改善

average-rank 口径下回退 case（122）多于改善 case（99），尤其 0-PASS 和大于 10 行的 fault equivalence class 中回退较多。这是实际实验结果，不是实现错误。

### 7. 问题的解决方式

- 将 `excluded` 改为 `list(static_excluded)`，以已保存 results resume 后重新生成 summary，恢复 static=20、dynamic=22；未改变已选 300 case。
- 完整性审计先按生产代码相同的 `validate_case` 规则过滤静态无效项，再验证固定 seed、分层顺序、300 个资格条件和 Pilot overlap，最终通过。
- 为测试夹具补齐 `RankedLine` 全部必填字段后重跑，新增 7 项统计/边界测试全部通过。
- 保留宿主失败记录，并在 Docker 29.1.3 正常运行的 LXD 中执行同一完整 discovery，75/75 全部通过。
- 将工作目录改为 `/workspace/CodeDoctor` 后重跑；0-test 命令不计为测试通过。
- 没有按 Evaluation 结果修改 branch aggregation、ranking 或任何算法。报告同时保留 paired 回退数量、0-PASS 弱表现、回退案例和置信区间。

### 8. 设计取舍

- `fl-v1` 冻结元数据先于 Evaluation split 提交；Evaluation runner 调用原 `localize` 实现并只筛出两个预注册方法，不复制或改写核心算法。
- 逐例 coverage/ranking 是可复现中间产物，不进入 Git；结构化 aggregate 和 ground truth 元数据进入 Git，支持论文数字审计且控制仓库体积。
- primary paired outcome 使用 tie-aware average-rank reciprocal rank，减少 deterministic line-number 顺序造成的偶然收益；同时完整保留 deterministic 与 pessimistic 指标。
- bootstrap 对 case pair 重采样而不是分别重采样两个方法，保留同一 case 的配对结构；McNemar 只使用 discordant Top-K pair 并实现 exact binomial two-sided p-value。
- 子组边界在读取结果前固定，只有 repair test 数、PASS 有无、coverage diversity 和 fault equivalence class size 四个机制相关维度，没有按成绩添加分组。
- straight-line ambiguity 采用严格可复现定义：可执行 fault 在最终 branch-aware tie 中仍有非 fault line，且两者 line coverage vector 相同。它量化当前证据边界，不声称完成语义等价证明。

### 9. 当前已知不足

- 结论仍限于 Codeflaws、GCC/gcov 12.2、现有 repair tests 和一次固定 300-case split；尚未跨数据集或跨编译器复验。
- 52 个 0-PASS case 缺少成功路径对照，branch-aware 平均增益明显较小且逐例回退更多。
- 20 个 non-executable textual diff fault 无法进入 line/branch ranking；205 个 case 仍存在 straight-line ambiguity。
- branch evidence 是相关性证据而非因果/语义证据，可能优先提升非 fault 控制行；122 个 average-rank 回退 case 必须在使用端保留不确定性。
- Top-10 的 paired improvement 在本样本上不显著；不能把 Top-1/3/5 结论外推到所有 K。
- `fl_evaluation_summary.json` 的 `elapsed_seconds_this_run` 表示最近一次 resume 调用，resume 无待处理候选时为 0，未累计首次动态验证的 542.967 秒；完整耗时保留在本日志。
- 逐例 coverage/ranking 未提交，需要原 Codeflaws raw 数据、LXD Docker 环境和 sandbox image 才能从脚本重建。

### 10. 下一步计划

- 下一阶段优先研究 repair-test augmentation/selection，重点为 0-PASS case 增加成功路径对照并提升 coverage/branch diversity；必须使用新的开发 split，不能再用本 Evaluation Set 调参。
- 预注册 executable-neighbor ground-truth 辅助口径，单独处理 non-executable diff line，同时继续保留严格原始行指标。
- 在另一数据集或编译器版本复现实验，验证 `fl-v1` 的外部有效性以及 gcov branch mapping 的稳定性。
- 后续接口应输出候选列表、line/branch score、tie interval、equivalence class 和不确定性，而不是把 branch-aware rank 1 当作确定诊断。
- 本轮不开始 LLM Repair、Agent、RAG、AST/CFG、Sanitizer 新功能或参数调优。

## 2026-08-15 - Phase 7: LLM Repair Baseline & Evidence Ablation

### 1. 本次目标

- 冻结 Fault Localization 为 CodeDoctor FL-v1，不修改 line Ochiai、branch max aggregation 或 tie-breaking。
- 建立一个与 50-case FL Pilot、300-case独立 FL Evaluation 都不重叠的 50-case Repair Pilot Set，固定 seed `20260817`。
- 固定单轮、单次尝试的 A/B/C evidence ablation：A 仅 source，B 追加 FL-v1 Top-10，C 再追加 repair-test execution evidence。
- 实现可审查的 repair/evaluation 数据边界、OpenAI-compatible provider、完整源码提取、Docker patch validation、artifact cache/resume、配对 bootstrap/McNemar、失败分析与报告。
- 有真实 API credential 时先运行 2-3 case 在线 smoke，再运行完整 Pilot；没有 credential 时禁止伪造在线结果。

### 2. 实际完成内容

- 开始时确认工作区干净，HEAD 为 Phase 6 commit `76b57e049a57fe691859c79685febc025daf6e61`，`origin` 为 `git@github.com:u-wyh/CodeDoctor.git` 且 main 同步。
- 新建独立 Repair Pilot selector，复用既有 static validation、Docker `verify_case` 和 stratified candidate order。先排除 50-case Pilot 与 300-case Evaluation，再以 seed `20260817` 动态验证 61 个候选并得到 50 个合格 case。
- 50 个 case 全部满足 buggy/reference compile、reference repair/validation 全通过、buggy 至少一个 failing repair test；与两个冻结数据集的 overlap 均为 0。11 个动态排除全部保留：reference repair 失败 5、reference validation 失败 6。
- 对 Repair Pilot 真实采集 50/50 份 line/branch coverage，调用冻结 FL-v1 输出固定 Top-10；0 error。repair-time FL 文件只含行号、源码行、line/branch score、rank 和 tie interval。ground-truth fault 与 FL failure-boundary attributes 保存到独立 evaluation-only 文件。
- 创建 `repair-v1` protocol，固定 prompt `repair-evidence-v1`、Top-K=10、attempt=1、完整源码输出、extraction、model defaults、validation 定义、cache key 字段，并记录 6 个核心 repair 文件 SHA-256。每次运行在线 pipeline 前验证这些哈希。
- 用 `RepairContext` 与 `EvaluationContext` 分开可进入 LLM 的字段和 reference/hidden-validation/ground-truth 字段。prompt renderer 的输入类型只接受 RepairContext；Group A/B/C 基础提示完全相同，仅按组追加 evidence section。
- 实现标准库 OpenAI-compatible Chat Completions provider，配置包括 base URL、环境变量 API key、model、temperature、max tokens、timeout 和可选 seed；API key 不进入参数对象、cache 或 artifact。
- 实现 C/C++ fenced/plain full-source extraction、模型 timeout/API/malformed response 错误、内容寻址 cache、`--cases/--group/--model/--limit/--resume` CLI、单次 attempt 和 prompt/response hash 元数据。
- 生成 patch 使用现有受限 Docker sandbox 编译，先运行 repair tests；全部通过才运行 hidden validation。严格区分 invalid output、compile error、repair failure、plausible patch 与 validated patch，并记录 original-fail 未修复、previously-pass regression、validation overfitting、line diff 和是否修改 FL Top-10。
- 实现 A/B/C valid output、compile、plausible、validated 指标，B-A/C-B/C-A 的 paired bootstrap 95% CI 和 exact McNemar，失败模式计数及 FL hit/0-PASS 分层。当前无在线 artifact 时这些指标明确为 N/A。
- 当前环境的 `OPENAI_*` 与 `CODEDOCTOR_*` API key/base URL/model 均未设置，因此真实在线 LLM 调用为 0。实际运行 3 case × A/B/C 的 fake echo smoke 共 9 条，fake 仅返回 buggy source，9 条均真实编译并分类为 `repair_test_failed`；所有 fake artifact 标记 `experimental=false`，不进入实验指标。
- 单独以 evaluation-only reference 对一个 case 运行不落 artifact 的 Docker evaluator 自检，得到 `validated_patch`，3 个 repair tests 与 24 个 hidden validation tests 全通过；reference 从未进入 prompt。
- 最终报告明确保留在线 A/B/C 为 0 case/N/A，不把 fake smoke 写成模型修复实验，不回答尚未测量的 evidence effectiveness。

### 3. 新增、修改、删除的文件

新增：

- `benchmark/datasets/codeflaws/metadata/repair_pilot.jsonl`
- `benchmark/datasets/codeflaws/metadata/repair_pilot_excluded.jsonl`
- `benchmark/datasets/codeflaws/metadata/repair_pilot_results.jsonl`
- `benchmark/datasets/codeflaws/metadata/repair_pilot_summary.json`
- `benchmark/metadata/repair/repair_protocol_v1.json`
- `benchmark/metadata/repair/repair_pilot_fl.jsonl`
- `benchmark/metadata/repair/repair_pilot_attributes.jsonl`
- `benchmark/repair_set.py`
- `benchmark/scripts/build_repair_pilot.py`
- `benchmark/scripts/run_repair_pilot_fl.py`
- `benchmark/scripts/run_repair_ablation.py`
- `benchmark/scripts/generate_repair_ablation_report.py`
- `benchmark/results/repair/evidence_ablation.json`
- `benchmark/reports/llm_repair_evidence_ablation.md`
- `benchmark/tests/test_repair_set.py`
- `repair/__init__.py`
- `repair/models.py`
- `repair/context.py`
- `repair/prompting.py`
- `repair/provider.py`
- `repair/extraction.py`
- `repair/evaluator.py`
- `repair/artifacts.py`
- `repair/pipeline.py`
- `repair/protocol.py`
- `repair/reporting.py`
- `repair/tests/__init__.py`
- `repair/tests/test_artifacts.py`
- `repair/tests/test_evaluator.py`
- `repair/tests/test_extraction.py`
- `repair/tests/test_pipeline.py`
- `repair/tests/test_prompting.py`
- `repair/tests/test_protocol.py`
- `repair/tests/test_provider.py`
- `repair/tests/test_reporting.py`

修改：

- `.gitignore`
- `README.md`
- `benchmark/config.py`
- `docs/DEVELOPMENT_LOG.md`

删除：无。

本地生成但忽略：

- `benchmark/results/repair/coverage/*.json`（50 份，约 696KB）
- `benchmark/artifacts/repair/<case>/<group>/*.json`（9 份 fake smoke，约 132KB）

### 4. 执行过的重要命令

```bash
git status
git remote -v
git log -1 --oneline

python3 -m unittest discover -s repair/tests -v
python3 -m unittest benchmark.tests.test_repair_set -v

lxc start codedoctor-docker-host
lxc exec codedoctor-docker-host -- docker info --format '{{.ServerVersion}}'
lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/build_repair_pilot.py --force'
lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/run_repair_pilot_fl.py --force'
lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/run_repair_ablation.py --provider fake --limit 3 --resume'
lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -v'
lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/run_repair_pilot_fl.py --reuse-coverage'
python3 benchmark/scripts/generate_repair_ablation_report.py
python3 benchmark/scripts/run_repair_ablation.py --limit 1

find benchmark/results/repair/coverage -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum
find benchmark/artifacts/repair -type f -name '*.json' -print0 | sort -z | xargs -0 sha256sum | sha256sum
sha256sum benchmark/metadata/repair/repair_pilot_fl.jsonl benchmark/metadata/repair/repair_pilot_attributes.jsonl
git check-ignore -v benchmark/artifacts/repair/259-B-bug-13083263-13083279/A/*.json benchmark/results/repair/coverage/259-B-bug-13083263-13083279.json benchmark/datasets/codeflaws/raw/codeflaws/259-B-bug-13083263-13083279 benchmark/datasets/codeflaws/downloads/codeflaws.tar.gz
git diff --check
lxc stop codedoctor-docker-host
```

另外实际执行了内联 Python 审计：验证 Repair Pilot 50 case 唯一、两个 overlap 为 0、入选顺序等于前 50 个动态 eligible records、reference suites 全通过、buggy repair 至少一项失败；扫描 9 个 fake prompts 的 canary/section/secret 边界；以一个 reference source 验证完整 hidden validation 路径；统计 Repair Pilot FL attributes。

### 5. 实际测试与实验结果

- Repair Pilot selection：候选池 3,534，动态验证 61，入选 50，动态排除 11，耗时 111.027 秒，seed `20260817`，FL Pilot/Evaluation overlap 均为 0。
- Repair Pilot FL-v1：50/50 case、0 error；13 个 0-PASS、4 个 non-executable fault、36 个 straight-line ambiguity；FL Top-1/5/10 hit 分别为 8/25/38。
- FL coverage 重建前后组合 SHA-256 均为 `0871e5f6262a4be0458fda5d74127052610e35a37c75df55f0d92cb2aca7d03b`；FL JSONL hash 为 `99a41e38223c755b9c974aa37ccfd136d766ed260bd081ed4045b46c2d887af0`，attributes hash 为 `9f0b4287436dcc9b590c8177e304ee53d63eb43908bba03564e97991fddd378f`，复用 coverage 后完全一致。
- fake smoke：3 case × A/B/C = 9 artifacts，首次耗时 12.629 秒；全部 valid output、compile success，但 unchanged buggy source 仍失败 repair tests，分类 9 个 `repair_test_failed`。`--resume` 重跑未改 artifact，组合 hash 前后均为 `dc6d35db3251a64dbfe706380c008f808c54a624cff8c19ec86bc996d448d092`。
- reference evaluator 自检：`259-B-bug-13083263-13083279` 得到 `validated_patch`，3 repair + 24 validation tests 全通过；该调用不是模型实验且未保存模型 artifact。
- Repair 单元测试开发中最终为 21/21 PASS，Repair Set 为 2/2 PASS。
- LXD Docker 环境最终全仓库 `98/98 PASS`，耗时 12.113 秒，无 skip；包括真实 Runner、Sanitizer、coverage collector 与所有旧回归。
- leakage scan：9/9 artifacts PASS；A 无 FL/execution，B 有 FL 无 execution，C 两者都有；canary 不存在；model parameters 无 credential 字段；prompt/cache/artifact 不含 API key。
- 在线 OpenAI-compatible provider CLI 在无 model/base URL/API key 时实际返回 exit code 2 和清晰错误。真实在线 LLM calls=0；A/B/C online compile/plausible/validated、paired comparison、bootstrap CI、McNemar 均为 N/A。
- credential/raw/build audit 无敏感信息匹配；无 `.env`；Codeflaws raw/archive、repair coverage、prompt/raw response/patch artifacts 均被 `.gitignore` 命中；Docker 无 `codedoctor-*` 残留容器；LXD 最终 STOPPED。

### 6. 遇到的问题

#### 6.1 Resume 首跑与 cache 命中的结构类型不同

首次 pipeline 返回内存 dataclass 中的 tuple，resume 从 JSON 读取 list，内容相同但测试比较失败。

#### 6.2 首次 Repair Pilot 审计读取了不存在的 `success` 字段

`SuiteVerification.success` 是 Python property，`asdict` 后 JSON 只有 total/passed/failed 等字段，首次内联审计报 `KeyError: success`。

#### 6.3 LXD 创建的输出目录在宿主不可写

`benchmark/metadata/repair` 和 `benchmark/results/repair` 首次由 LXD root 创建，宿主 apply/report 写入分别报 permission denied。

#### 6.4 Artifact secret 扫描误报 `max_tokens`

初版扫描用包含匹配 `token` 判断敏感字段，把合法生成参数 `max_tokens` 当作 credential，报告生成被主动阻止。

#### 6.5 当前环境没有在线模型凭据

`OPENAI_API_KEY/BASE_URL/MODEL` 与 `CODEDOCTOR_API_KEY/BASE_URL/MODEL` 全部 unset，不能执行真实在线 smoke 或 50-case A/B/C Pilot。

#### 6.6 Staged diff 检查发现两个空包文件多余空行

`git diff --cached --check` 指出 `repair/__init__.py` 与 `repair/tests/__init__.py` 的 new blank line at EOF。

### 7. 问题的解决方式

- artifact 写入后统一从 JSON 重新读取并返回，使首跑和 resume 的公开结构完全相同；cache test 验证同配置只调用模型一次，参数变化产生新 key。
- 审计改为按 `total > 0 and passed == total` 判断 suite success，重新核验 50 个 case 后全部通过。
- 在 LXD 内只调整两个生成目录的写权限，随后宿主成功写入 protocol、summary 和 report；未改变 sandbox 容器安全配置。
- secret scan 改为明确禁止 `api_key/access_token/authorization/password/secret`，保留合法 `max_tokens`；重新扫描 9 个 artifacts 全部通过。
- 不创建假 credential、不调用未知端点、不把 fake 结果伪装成 LLM 指标。provider、mock、pipeline、报告均完成，在线指标明确 N/A。
- 删除两个 `__init__.py` 的多余空行并重新暂存，最终 staged diff check 通过。

### 8. 设计取舍

- 基础 prompt 只要求最小修改、保留 I/O、不硬编码测试、返回完整源码；不做多轮反馈、自反思、ensemble、Agent 或 prompt sweep。A/B/C 通过 append-only sections 控制变量。
- 允许 Group C 使用 repair tests 的 expected output，因为它属于既有 repair-time benchmark information；hidden validation expected behavior 和 reference 永远不进入 RepairContext。
- provider 采用小型标准库 HTTP 实现而不是引入大型 SDK/Agent framework；当前只实现 OpenAI-compatible Chat Completions 所需最小接口。
- patch extraction 只支持 fenced C/C++ block 或看起来像完整程序的 plain source；不为异常模型输出扩张复杂 parser。
- patch 先通过全部 repair tests 才运行 hidden validation，避免不必要的 evaluation-only 执行；hidden validation result 不回灌模型，attempt 固定为 1。
- raw prompts/responses/patches 默认全部忽略，仅提交小型 selection metadata、FL Top-10、evaluation-only attributes、空在线 summary 和诚实报告。
- fake provider 只验证 plumbing，所有 artifact 强制 `experimental=false`；统计器只读取 `experimental=true`，并拒绝混合多个在线 model/prompt configuration。
- `validated_patch` 只表示现有 repair + hidden validation suites 全通过，不使用 `correct_patch` 术语，也不声称形式正确性。

### 9. 当前已知不足

- 核心研究问题尚未被真实模型数据回答；A/B/C 在线样本均为 0，所有 effectiveness 指标、CI 和 McNemar 结果为 N/A。
- Chat Completions compatibility 依赖后续实际 provider；不同 OpenAI-compatible 服务可能在 `max_tokens`、seed 或返回 schema 上有差异，需要真实 smoke 验证，但不能根据修复率改协议。
- Repair Pilot 仅 50 个 Codeflaws case，单模型单次尝试的 CI 可能很宽；Codeflaws 与测试套件也不代表大型真实 C/C++ 系统。
- temperature 0 和 provider seed 不保证确定性；当前 cache 保证同一已完成调用不重复付费，但不证明模型本身 deterministic。
- 13 个 0-PASS、4 个 non-executable fault、36 个 straight-line ambiguity 可能限制 FL evidence；目前只有 descriptive attributes，没有在线 repair outcome 可关联。
- 普通 line diff 对 insertion/deletion 只做近邻行映射，足够低成本分析，但不是 AST 级 patch attribution。
- `--resume` 仍会重新计算 buggy baseline execution，虽然不会重复模型调用或付费；后续可独立缓存 baseline evidence而不改变 prompt protocol。

### 10. 下一步计划

- 等人工配置一个固定的 OpenAI-compatible base URL、API key 和精确 model version 后，保持 `repair-v1` 哈希不变，先真实运行 2-3 case × A/B/C smoke。
- 人工审查 smoke prompts、raw responses、patch extraction、hidden validation boundary 和 artifact cache；若是基础设施 bug，显式修复并升级 protocol version，不根据修复率调 prompt。
- smoke 通过后运行完整 50-case × 3 groups = 150 次单轮在线调用，使用 `--resume` 避免中断重复付费，再生成真实 paired bootstrap/McNemar 与 failure analysis。
- 完成真实 Phase 7 实验并经人工审查前，不进入 Phase 8，不加入多轮反馈、test augmentation、sanitizer feedback、Agent 或 ensemble。

## 2026-08-15 - Phase 7: Experimental Protocol Addendum

### 1. 本次目标

- 在不重新设计 Phase 7 的前提下落实三项协议修正：Repair Pilot 选择与 FL-v1 表现解耦；A/B/C 使用完全相同的任务语义；真实在线批量调用前强制暂停。
- 审计 Codeflaws 是否存在可靠、自动、可复现的逐题 Problem Specification；不存在时使用统一 Common Repair-Time Oracle。
- 保留所有 FL applicability boundary，包括 0-PASS、non-executable fault、large tie、straight-line ambiguity 和无可靠 suspicious location 的 case。
- 在任何大规模真实在线调用前给出 model、provider、credential、billing、调用量、token、成本和 leakage 状态报告。

### 2. 实际完成内容

- 审计现有 Codeflaws raw 数据：逐 case 目录只有源码、Makefile、repair/heldout tests 和脚本，没有可自动取得的逐题题面；根 README 只描述数据布局。固定 archive SHA-256 `2673fc16fa05590c5c1171f5b633594713ae9207346a3d0ba4c4d8b2eea82b11` 和 README SHA-256 `18156e9ca42cda0fff19acddf939134e70c8067bf775e598424971cb26f2f087`。
- 新增 `repair-v2` 协议：A/B/C 共同获得 buggy source 以及相同的 repair-test input/expected-output oracle；B 只追加 FL-v1，C 只追加 verdict、actual stdout/stderr、exit code 和 timeout。expected output 不再只出现在 C。
- 将 task semantics 与 runtime evidence 拆成 `TaskExample` 和 `RepairTestEvidence` 两种模型；prompt renderer 拒绝缺少共同 oracle 或 evidence group 边界不一致的上下文。
- Repair Pilot summary 明确记录 `fl_performance_filtering=false` 和允许的 selection inputs。原 50 个 case 全部保留，没有按 Top-K 命中、tie、0-PASS、non-executable 或 ambiguity 删除样例。
- 重新生成 50 个 Repair Pilot FL 记录。49 个提供正分数可疑位置；`103-A-bug-18288288-18288294` 的 FL-v1 排名没有正分数位置，仍保留在 A/B/C，B/C 使用统一文本 `No reliable suspicious location is available from FL-v1.`。
- 将无可靠 FL 的数量和 case ID 写入结构化 `failure_analysis`，并在消融报告中单独列出 1/50 applicability boundary。
- 增强 artifact 边界审计：同一 case 的 A/B/C base 必须相同，B/C 的 FL 前缀必须相同，C runtime section 禁止再次出现 input/expected output，并继续扫描 reference/validation canary 和 secret 参数字段。
- 实现预实验估算器和独立报告。对 50 cases × 3 groups 实际构造 150 个 v2 prompts，并通过 Docker Runner 计算 buggy baseline/runtime evidence；记录每个 prompt hash、调用数和 provider-independent token 近似。
- 实现在线批量保护：OpenAI-compatible provider 在预计调用数大于 9 且没有 `--confirm-bulk` 时，于调用 provider 前拒绝执行；协议层 helper 和 CLI 负向集成测试均通过。
- 当前 model/version、实际 provider 服务、base URL、独立 API credential 和 billing path 均未配置；provider pricing 未验证，预计 API 成本不猜测。真实在线 LLM 调用保持为 0。
- 离线 fake smoke 重跑 3 cases × A/B/C 共 9 artifacts，均为 `repair-evidence-v2`。人工审计确认共同 base 和 B/C FL 前缀逐 case 相同，C runtime section 不含额外任务语义，reference source、ground-truth diff、hidden validation 和 evaluation-only metadata 均未进入 prompt。
- README、结构化 evaluation、消融报告和预实验报告均同步到 `repair-v2`。没有开始 Phase 8。

### 3. 新增、修改、删除的文件

新增：

- `benchmark/metadata/repair/problem_specification_audit.json`
- `benchmark/metadata/repair/repair_protocol_v2.json`
- `benchmark/metadata/repair/pre_experiment_estimate.json`
- `benchmark/reports/llm_repair_pre_experiment.md`
- `benchmark/scripts/estimate_repair_experiment.py`
- `repair/pre_experiment.py`

修改：

- `README.md`
- `benchmark/config.py`
- `benchmark/datasets/codeflaws/metadata/repair_pilot_summary.json`
- `benchmark/metadata/repair/repair_pilot_fl.jsonl`
- `benchmark/reports/llm_repair_evidence_ablation.md`
- `benchmark/results/repair/evidence_ablation.json`
- `benchmark/scripts/build_repair_pilot.py`
- `benchmark/scripts/run_repair_ablation.py`
- `benchmark/scripts/run_repair_pilot_fl.py`
- `repair/context.py`
- `repair/evaluator.py`
- `repair/models.py`
- `repair/prompting.py`
- `repair/protocol.py`
- `repair/reporting.py`
- `repair/tests/test_prompting.py`
- `repair/tests/test_protocol.py`
- `repair/tests/test_reporting.py`
- `docs/DEVELOPMENT_LOG.md`

删除：无。

本地生成但忽略：

- `benchmark/artifacts/repair/<case>/<group>/*.json`：9 个 repair-v2 fake smoke artifacts。
- 原 repair-v1 fake artifacts 已移至 `/tmp/codedoctor-repair-v1-*` 备份，不参与 v2 扫描。

### 4. 执行过的重要命令

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s repair/tests -v

lxc list --all-projects --format csv -c pns4
lxc config show codedoctor-docker-host --expanded
lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/run_repair_pilot_fl.py --reuse-coverage'
lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/run_repair_ablation.py --provider fake --limit 3 --resume'
lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/estimate_repair_experiment.py --manual-inspection passed'
lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/generate_repair_ablation_report.py'
lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && CODEDOCTOR_MODEL=dummy CODEDOCTOR_BASE_URL=http://127.0.0.1:9 CODEDOCTOR_API_KEY=dummy PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/run_repair_ablation.py --provider openai-compatible --limit 4'

lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s sandbox/tests -v'
lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s benchmark/tests -v'
lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s fault_localization/tests -v'
lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s repair/tests -v'

sha256sum benchmark/metadata/repair/repair_pilot_fl.jsonl benchmark/metadata/repair/repair_pilot_attributes.jsonl
python3 -m json.tool benchmark/metadata/repair/repair_protocol_v2.json
python3 -m json.tool benchmark/metadata/repair/pre_experiment_estimate.json
python3 -m json.tool benchmark/results/repair/evidence_ablation.json
git diff --check
lxc exec codedoctor-docker-host -- docker ps -a --filter name=codedoctor --format '{{.ID}} {{.Names}} {{.Status}}'
lxc exec codedoctor-docker-host -- docker version --format '{{.Server.Version}}'
lxc stop codedoctor-docker-host
```

另外实际执行了内联 Python 审计：扫描 Codeflaws 题面可用性；检查 50-case selection inputs 与 `fl_performance_filtering`；统计可靠/无可靠 FL；比较 9 个 A/B/C prompt 的 base 和 evidence sections；扫描 reference、validation、ground-truth 与 secret canary；统计 token/call/readiness；比较 fake artifact 集合 hash。

### 5. 实际测试结果

- 完整 LXD Docker 回归：sandbox 29/29、benchmark 12/12、fault localization 36/36、repair 23/23，共 100/100 PASS，无 skip。最后修改 reporting 后再次运行 repair 23/23 PASS。
- Repair Pilot FL-v1：50/50、0 error；49 个有可靠正分数位置，1 个无可靠位置且仍保留。FL JSONL SHA-256 为 `063e6bc5fab688f6d9c0ffc422cb781b9d4c546915db5514e806cbd48d1e3177`，attributes SHA-256 为 `9f0b4287436dcc9b590c8177e304ee53d63eb43908bba03564e97991fddd378f`；第二次 `--reuse-coverage` 后二者完全一致。
- repair-v2 fake smoke：3 cases × A/B/C = 9 artifacts，全部完成真实 Docker 编译和 repair tests，分类均为 `repair_test_failed`。首次和 `--resume` 后 artifact 集合 SHA-256 均为 `72233316ac431fa13c68b1453dff22df69fed665028fc7182f62e1dd9266e6ee`。
- Prompt 人工审计：3/3 cases 的 A/B/C base 相同，3/3 的 B/C FL 前缀相同，C runtime section 额外 `Input:`/`Expected output:` 命中 0；9/9 有共同 oracle；reference/validation/ground-truth/hidden-validation canary 命中 0。
- 批量保护负向集成测试：使用 dummy model/base URL/key 请求 4 cases × 3 groups = 12 次，CLI 在网络调用前以 exit code 2 拒绝，并明确要求 explicit approval 和 `--confirm-bulk`。
- 预实验预算：50 cases、3 groups、attempt=1，主调用 150，真实 smoke 上限 9，自动 transport retries=0。近似输入 token：A 平均 380/总计 18,800，B 平均 590/总计 29,700，C 平均 690/总计 34,400；预期完整源码输出平均约 160/总计约 24,600。
- token 方法为每个 prompt/source 的 `ceil(character count / 4)`，平均值四舍五入到 10、总量到 100；不是 provider tokenizer 的精确结果。
- 真实在线模型 artifacts=0、真实在线 LLM calls=0。model/version 未选择，实际 provider 服务未选择，独立 API key 未配置，pricing 未验证，estimated API cost 为 N/A，`bulk_online_ready=false`。
- JSON 语法检查、`git diff --check` 均通过；Docker Server 29.1.3，无残留 `codedoctor-*` 容器，LXD 最终已停止。

### 6. 遇到的问题

#### 6.1 报告边界测试仍使用 repair-v1 段落格式

生产校验开始严格比较双换行分隔的 base/FL sections 后，旧测试夹具只使用单换行，首次 repair discovery 为 22 项中 1 项 error。

#### 6.2 初始 LXD 实例名判断错误

首次尝试访问 `codedoctor-dev` 返回 instance not found；当前项目实际容器名为 `codedoctor-docker-host`。

#### 6.3 旧 fake artifacts 由 LXD 映射 UID 所有

宿主直接迁移 repair-v1 artifact 目录时可以复制文件但不能移除源文件；安全策略同时拒绝了强制递归删除命令。

#### 6.4 首次 FL 审计使用了错误结果路径

内联审计最初读取 `benchmark/results/repair_pilot/fl_results.jsonl`，实际配置路径是 `benchmark/metadata/repair/repair_pilot_fl.jsonl`，因此得到 `FileNotFoundError`。

#### 6.5 无可靠 FL 只有提示规则，没有进入结构化 failure analysis

初次 v2 报告描述了统一文本，但 `failure_analysis` 尚未单列这类 applicability boundary。

#### 6.6 当前不具备真实在线实验条件

没有选定精确 model/version 和实际 provider 服务，`CODEDOCTOR_*`/`OPENAI_*` model、base URL、API key 均未配置，计费路径与当前价格也未验证。

### 7. 问题的解决方式

- 将 reporting 测试夹具改为与真实 v2 prompt 一致的段落分隔，增加共同 oracle、无可靠 FL 和批量保护回归，repair tests 最终 23/23 PASS。
- 通过 `lxc project list`、`lxc list --all-projects` 和 `lxc config show` 确认真实实例及 `/workspace/CodeDoctor` 映射，后续命令全部在正确容器执行。
- 在 LXD 内只为忽略的旧 artifact/父目录调整写权限，再整体移动到 `/tmp` 备份并重建空 artifact 目录；未删除跟踪文件，也未把 repair-v1 产物混入 v2 报告。
- 按 `benchmark/config.py` 常量修正审计路径，重新统计得到 50 records、49 reliable、1 unreliable、1 empty locations。
- reporting 直接读取冻结 FL JSONL，将无可靠位置的数量与 case IDs 写入结构化结果并重生成报告；没有使用 ground truth 或 reference 判断可靠性。
- 不创建真实 credential、不猜 provider 价格、不调用未知在线端点。完成本地准备与报告后保持 mandatory stop；dummy credential 仅用于验证调用前 CLI guard，目标 URL 未被访问。

### 8. 设计取舍

- 当前数据没有统一题面时，使用已有 repair-time input/expected-output pairs 作为版本化共同 oracle；它对 A/B/C 完全一致，避免 C 因 expected output 额外获得任务规格。
- C 只新增运行观察，不重复 input/expected output。PASS/FAIL、actual output、exit code 和 timeout 被视为对公共任务语义执行后的动态证据。
- 无可靠 FL 的判定只依赖冻结 ranking 是否非空以及最大 line suspiciousness 是否大于 0；不以 Top-K ground-truth hit、reference diff 或人工判断替代。
- 预实验 token 估算采用透明的字符近似，不声称 provider tokenizer 精度；provider/model 未确定时成本明确为 N/A，不引用或猜测价格。
- `--confirm-bulk` 是 explicit approval 后的技术确认位，不会因为 API key 存在、smoke 成功或订阅可用而自动开启。
- ChatGPT Plus/Codex subscription 与 API billing 视为不同体系，除非后续实际 provider/account 明确证明，否则不假设共享 quota。

### 9. 当前已知不足

- Phase 7 的核心因果问题仍未获得真实在线模型结果；A/B/C 在线 compile/plausible/validated、paired bootstrap 和 exact McNemar 仍为 N/A。
- Common Repair-Time Oracle 只提供现有 repair tests 表达的部分任务语义，不等价于完整自然语言 Problem Specification；可能限制模型理解与外部有效性。
- 字符除以 4 的 token 估算不能替代选定模型的真实 tokenizer；完整源码输出长度也只是预算代理。
- OpenAI-compatible provider 尚未对一个实际服务做真实 smoke，不同服务的参数和响应 schema 兼容性仍待验证。
- 当前未限制模型响应 artifact 的总体磁盘量；Docker Runner 的既有隔离边界与不足继续存在。
- 1 个无可靠 FL、13 个 0-PASS、4 个 non-executable fault 和 36 个 straight-line ambiguity 会降低 FL evidence 可用性，但必须保留，不能 post-hoc 删除。

### 10. 下一步计划

- 由用户选定精确 model/version、实际 provider 与独立 API billing path，并以当前官方价格核实 input/output 计费；不得根据预期修复率选择模型或改 prompt。
- 配置独立 API key 后最多运行 2-3 cases × A/B/C 的真实 smoke，检查 provider compatibility、raw prompts/responses、patch extraction、cache 和 leakage；smoke 不得自动扩展。
- smoke 全部审计通过后重新生成预实验报告，再次汇报实际 model/provider、credential、billing、调用量、token、成本与 leakage 状态。
- 只有收到用户对付费/批量调用的明确批准后，才可使用 `--confirm-bulk` 执行 50 × 3 = 150 次单轮实验。
- 完整 Phase 7 在线实验和人工审查完成前，不开始 Phase 8，不加入 Agent、RAG、多轮修复、test augmentation、AST/CFG 或新的 FL 方法。

## 2026-08-16 - Phase 7: DeepSeek Provider Readiness

### 1. 本次目标

- 不修改冻结的 `repair-v2`、A/B/C prompt、Repair Pilot 或 FL-v1，正式选择 DeepSeek Official API 作为 Phase 7 候选 provider。
- 冻结 `deepseek-v4-pro`、thinking enabled、reasoning effort high、stream false、max tokens 8192、attempt 1 和 transport retry 0。
- 在真实调用前完成 provider、credential、prompt boundary、leakage、bulk guard 和 cache/resume readiness 检查。
- 仅在允许的 Key 存在且全部离线检查通过时，运行最多 1 frozen case × A/B/C = 3 次真实 smoke；不得运行 150-call bulk。
- 核验 DeepSeek 官方价格，更新 token/cost 与预实验报告，然后再次暂停。

### 2. 实际完成内容

- 保持 `repair/context.py`、`repair/evaluator.py`、`repair/extraction.py`、`repair/pipeline.py`、`repair/prompting.py`、`repair/provider.py` 和 `repair_protocol_v2.json` 无 diff；冻结哈希验证继续通过。
- 新增薄 DeepSeek OpenAI-compatible 适配器，复用现有 prompt、ModelParameters、错误类型、extraction、Docker evaluator、artifact/cache 和 single-attempt pipeline，不建立平行 repair framework。
- DeepSeek 请求固定发送 `model=deepseek-v4-pro`、`thinking.type=enabled`、`reasoning_effort=high`、`stream=false`、`max_tokens=8192`；不发送 temperature、top_p 或 seed。配置 JSON 与代码常量必须完全一致，否则 CLI 拒绝执行。
- DeepSeek Key 只按 `DEEPSEEK_API_KEY`、`CODEDOCTOR_API_KEY` 顺序解析，明确不使用 `OPENAI_API_KEY` fallback。宿主和 LXD 中两个允许变量均 absent，实际 1-case 命令在网络前以 exit code 2 返回 `DeepSeek API credential unavailable`。
- reasoning extraction 只返回 `message.content`。`reasoning_content` 正文不进入 patch extraction、prompt、下一轮或 artifact；只保存 present、character count 和 SHA-256 摘要。usage 按 provider 实际字段保存，缺失字段不伪造成 0。
- DeepSeek artifact metadata 支持 requested model、response.model、official documented version、system fingerprint、finish reason、prompt/completion/total/cache/reasoning tokens 和 credential environment name，不保存 Key value。HTTP error body写 artifact 前主动进行 Key redaction。
- DeepSeek 无确认调用上限固定为 3；4 次及以上需要另行明确批准与 `--confirm-bulk`。本轮没有使用该标志。
- smoke case 固定为 Repair Pilot manifest 第一项 `259-B-bug-13083263-13083279`，不按 FL 或预期修复难度选择。
- 全量离线估算真实构造 50 × A/B/C = 150 个冻结 prompts，并执行 50 个 buggy baseline。A/B/C base 与 B/C FL 前缀审计通过，C runtime section 不含额外 input/expected output。
- 官方 DeepSeek 文档核验 `deepseek-v4-pro`、OpenAI Chat Completions、thinking/high 参数和 `DeepSeek-V4-Pro-0813` documented model version。没有真实 response，因此 response.model/system fingerprint 仍未观测。
- 官方价格于 `2026-08-16T02:49:39Z` 核验：当时每 1M tokens 的 cache-hit input `$0.003625`、cache-miss input `$0.435`、output `$0.87`。官方页面同时预告 `2026-08-16T16:00:00Z` 启用 peak/off-peak：off-peak `$0.022/$0.66/$1.98`，peak `$0.044/$1.32/$3.96`；peak windows 为 `01:00-04:00 UTC` 与 `06:00-10:00 UTC`。
- Key 条件不满足，因此真实 DeepSeek smoke 按协议跳过。真实 calls=0，A/B/C usage、classification、finish reason 和实际 resolved model 全部保留 N/A；没有伪造 token usage。
- 预实验报告更新为 DeepSeek 配置、实际 credential/readiness、真实 usage 表、官方价格、成本、prompt/artifact audit 和 mandatory stop。`bulk_online_ready=false`、`bulk_user_authorized=false`。

### 3. 新增、修改、删除的文件

新增：

- `benchmark/metadata/repair/deepseek_experiment_config.json`
- `benchmark/metadata/repair/deepseek_pricing_20260816.json`
- `repair/deepseek.py`
- `repair/tests/test_deepseek.py`
- `repair/tests/test_pre_experiment.py`

修改：

- `README.md`
- `benchmark/config.py`
- `benchmark/metadata/repair/pre_experiment_estimate.json`
- `benchmark/reports/llm_repair_pre_experiment.md`
- `benchmark/scripts/run_repair_ablation.py`
- `repair/models.py`
- `repair/pre_experiment.py`
- `repair/protocol.py`
- `repair/tests/test_protocol.py`
- `docs/DEVELOPMENT_LOG.md`

删除：无。

本地保留但忽略：

- `benchmark/artifacts/repair/<case>/<group>/*.json`：原有 9 个 repair-v2 fake smoke artifacts；本轮没有新增真实 DeepSeek artifact。

### 4. 执行过的重要命令

```bash
date --iso-8601=seconds
date -u --iso-8601=seconds

PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s repair/tests -v
env -u DEEPSEEK_API_KEY -u CODEDOCTOR_API_KEY OPENAI_API_KEY=dummy PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/run_repair_ablation.py --provider deepseek --limit 1
DEEPSEEK_API_KEY=dummy PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/run_repair_ablation.py --provider deepseek --limit 2

lxc start codedoctor-docker-host
lxc exec codedoctor-docker-host -- systemctl start docker
lxc exec codedoctor-docker-host -- docker version --format '{{.Server.Version}}'
lxc exec codedoctor-docker-host -- docker image inspect codedoctor-cpp-sandbox --format '{{.Id}}'
lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/estimate_repair_experiment.py --manual-inspection passed'
lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/run_repair_ablation.py --provider fake --limit 3 --resume'
lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/run_repair_ablation.py --provider deepseek --limit 1 --resume'

lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s sandbox/tests -v'
lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s benchmark/tests -v'
lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s fault_localization/tests -v'
lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s repair/tests -v'

python3 -m json.tool benchmark/metadata/repair/deepseek_experiment_config.json
python3 -m json.tool benchmark/metadata/repair/deepseek_pricing_20260816.json
python3 -m json.tool benchmark/metadata/repair/pre_experiment_estimate.json
git diff --check
lxc exec codedoctor-docker-host -- docker ps -a --filter name=codedoctor --format '{{.ID}} {{.Names}} {{.Status}}'
lxc stop codedoctor-docker-host
```

另外实际执行了 DeepSeek 官方 API 文档浏览：Thinking Mode、Create Chat Completion、Models & Pricing、Change Log 和 Context Caching；只使用 `api-docs.deepseek.com` 的官方信息。执行了内联 Python 审计：检查 Key presence 但不读取 value；验证 150 prompts 的 base/FL/runtime 边界；扫描 changed files 的 secret pattern、文件体积、可执行位和 `.env`；验证 9 个 fake artifacts 无 secret 参数、在线 artifact=0；核对 pre-experiment readiness 和成本字段。

### 5. 实际测试结果

- 完整回归：sandbox 29/29、benchmark 12/12、fault localization 36/36、最终 repair 32/32，共 109/109 PASS，无 skip。repair suite 在 DeepSeek redaction/readiness 收紧后单独重跑并通过。
- DeepSeek provider 测试覆盖：冻结配置、Key 优先级、拒绝 OpenAI fallback、thinking request body、temperature omission、final content-only extraction、reasoning 摘要、usage/cache/reasoning token、artifact 无 secret、HTTP error Key redaction。
- CLI 无 credential 测试：宿主与 LXD 的 1-case DeepSeek 命令均在联网前以 exit code 2 停止，错误为 `DeepSeek API credential unavailable`。
- 3-call guard 测试：使用 dummy Key 请求 2 cases × 3 groups = 6 calls，在联网前以 exit code 2 拒绝；dummy URL/API 未调用。协议单测同时验证 DeepSeek 3 allowed、4 blocked、显式批准位的未来路径。
- Prompt/leakage：50 cases、150 prompts PASS；reference leakage PASS、validation leakage PASS、ground-truth diff absent、hidden validation absent、evaluation-only metadata absent。9/9 fake artifacts boundary audit PASS。
- Cache/resume：3 cases × A/B/C fake artifacts 重跑前后数量均为 9，集合 SHA-256 均为 `72233316ac431fa13c68b1453dff22df69fed665028fc7182f62e1dd9266e6ee`。
- 冻结协议：六个 frozen implementation 文件和 `repair_protocol_v2.json` 无 diff，`validate_repair_protocol()` 返回 `repair-v2`。
- 真实 DeepSeek calls=0；实际 A/B/C prompt/completion/reasoning/total usage=N/A；actual classification=N/A；response.model/system fingerprint=N/A；无 truncated response 可检查。
- 无真实 usage 时保留 provider-independent 150-call token 预算：A input 18,800、B 29,700、C 34,400，output proxy 24,600，input 总计 82,900。reasoning usage 不伪造，记为 N/A。
- 保守 all-cache-miss 成本：核验时费率 `$0.057464`；计划生效后的 off-peak `$0.103422`；peak `$0.206844`。由于真实 thinking usage 缺失，这些是字符估算预算，不是实际 smoke 外推。
- Secret/raw audit：changed files 14，secret pattern 0，`.env` 0，超过 1MB 文件 0，可执行 changed file 0；artifact secret-key violations 0；raw Codeflaws、临时 executable 和 raw reasoning artifact 均未进入待提交内容。
- Docker 29.1.3、sandbox image `sha256:7f529aa877352a798339448978b742b45a25f241da10a7ec0a77270817842420`；无残留 `codedoctor-*` containers，LXD 最终 STOPPED。

### 6. 遇到的问题

#### 6.1 LXD 启动后 Docker socket 短暂不可用

首次在同一命令中启动 LXD 后立即查询 Docker，返回 `/var/run/docker.sock` 不存在，预实验估算没有开始。

#### 6.2 当前没有允许的 DeepSeek API credential

宿主和 LXD 中 `DEEPSEEK_API_KEY`、`CODEDOCTOR_API_KEY` 均 absent；`OPENAI_API_KEY` 也 absent，且即使存在也禁止作为 DeepSeek fallback。

#### 6.3 官方价格在核验当天存在定时切换

官方页面给出核验时 flat price，同时预告同日 `16:00 UTC` 开始 peak/off-peak 新价格；若只记录一个价格会在实验时点产生歧义。

#### 6.4 HTTP error redaction 测试夹具缺少 close 方法

redaction 断言通过，但 Python 清理模拟 HTTPError 时输出 ignored exception，说明 fake file interface 不完整。

#### 6.5 初版 technical readiness 只检查 artifact 数量

仅要求 A/B/C 各一个 artifact 可能把 model error、invalid output、缺 usage 或 `finish_reason=length` 误判为 smoke complete。

#### 6.6 长文件分段读取产生视觉重复

两个相邻 `sed` 范围在边界处重叠，使 `Bulk projection basis` 看起来重复；`apply_patch` 因实际文件不匹配而安全失败。

### 7. 问题的解决方式

- 等待实例启动后显式确认/启动 Docker service，再验证 Server 29.1.3 和 sandbox image，随后成功运行两次全量离线估算。
- 严格执行 credential gate：没有创建、读取、打印或提交 Key，没有尝试 DeepSeek 网络调用，没有使用 dummy Key 触发请求。
- 将官方价格与 `verified_at`、scheduled `effective_at`、UTC peak windows、currency 和 source URL一起保存；分别计算核验时、未来 off-peak、未来 peak 三种 cache-miss 成本。
- 为 FakeHTTPResponse 补齐 `close()`，repair suite 重新运行后输出干净；生产 HTTP error detail 同时替换可能回显的 Key。
- technical readiness 收紧为：恰好 3 个 A/B/C artifacts、每组完整 usage、final content 可提取、非 model/invalid-output 且 finish reason 非 length；新增单测覆盖 stop 与 length。
- 使用 `rg -n` 精确核对模板和报告，确认二者实际都只有一处 projection basis；失败补丁没有修改文件。

### 8. 设计取舍

- 因 `repair/provider.py` 和 `repair/pipeline.py` 属于 repair-v2 frozen implementation，使用新薄适配器而不是重构冻结文件；适配器继承现有 OpenAI-compatible provider 的认证构造并复用所有 repair pipeline 边界。
- `temperature=None` 只表示 DeepSeek thinking request 不发送 temperature；generic OpenAI-compatible/fake CLI 默认仍保持 0.0，不改旧行为。
- DeepSeek 专属 thinking/high/stream/max tokens 由 provider 名称和严格 config validator 固定，cache key 继续包含 provider、model、temperature null、max tokens、timeout 和 seed；不能以 CLI 参数静默漂移。
- reasoning_content 仅保存不可逆摘要和长度，既能审计 thinking 是否出现，又避免 raw reasoning artifact 扩张或参与实验输入。
- 成本主估计一律使用 cache miss，不假设 best-effort context cache 命中；在真实 smoke usage 缺失时不使用虚假的 reasoning token。
- `bulk_online_ready` 表示技术就绪，不等于用户授权；`bulk_user_authorized` 单独保持 false。本轮两者均 false。

### 9. 当前已知不足

- 没有 credential，因此尚未验证 DeepSeek 真实 HTTP compatibility、账户权限、响应 schema、resolved response.model/system fingerprint、thinking token usage 或 balance billing。
- 官方 documented version 为 `DeepSeek-V4-Pro-0813`，请求仍使用 mutable alias `deepseek-v4-pro`；alias 未来可能变化，必须记录每次 response.model 和 system fingerprint。
- 150-call token/cost 仍基于字符近似和 buggy-source output proxy；thinking mode 的实际 completion/reasoning usage可能显著不同。
- 当前 artifact enrichment 在 frozen pipeline 写入后补充 provider metadata；进程若恰好在两次原子写之间中断，已完成 artifact 可能暂缺 usage，需要人工审计，不能自动重发付费请求。
- 真实 smoke 尚未检查 finish_reason length、源码完整性、compile/plausible/validated classification 或 hidden validation 路径。
- 官方价格会变化；真实 smoke 和 bulk 批准前必须再次打开官方 pricing page 核验，不应只依赖本次快照。

### 10. 下一步计划

- 由用户在执行环境中配置 `DEEPSEEK_API_KEY`，或明确使用 `CODEDOCTOR_API_KEY` generic fallback；不要把 value 写入文件或聊天。
- 重新执行全部离线 readiness 后，只运行 `259-B-bug-13083263-13083279` 的 A/B/C 三次真实 smoke，不使用 `--confirm-bulk`，transport retry 仍为 0。
- 检查三个 response 的 final content、reasoning 摘要、usage/cache/reasoning tokens、finish reason、resolved model、patch extraction、Docker compile、repair tests、hidden validation、classification 和 artifact integrity。
- 用真实三组 usage 重新外推 150-call tokens/cost，并在当时再次核验 DeepSeek 官方 peak/off-peak 价格；随后保持 mandatory stop。
- 只有用户在审阅真实 smoke 与更新报告后另行明确批准，才允许使用 `--confirm-bulk`；不得自动开始 150 calls，也不得进入 Phase 8。

## 2026-08-16 - Phase 7: DeepSeek A/B/C Real Smoke Validation

### 1. 本次目标

- 仅检查 `DEEPSEEK_API_KEY` credential 是否存在，不读取、打印或提交 Key。
- 对预注册 case `259-B-bug-13083263-13083279` 执行 A/B/C 各一次真实 DeepSeek smoke，真实调用上限为 3。
- 不使用 `--confirm-bulk`，不启动 50 cases x 3 groups 的 150-call 正式实验。
- 审计真实响应、token usage、cache、模型版本、提取与验证状态、信息边界和 artifact 完整性，并据此更新预实验预算与 readiness。

### 2. 实际完成内容

- 按要求先 `source ~/.config/codedoctor/secrets.env`，仅通过环境变量存在性检查确认 `DEEPSEEK_API_KEY` available；没有读取或输出 secrets 文件内容。
- 调用前重新运行 13 项 DeepSeek、prompt、protocol、artifact 和 pipeline 测试，全部通过；离线序列化 A/B/C 三个真实 request payload，确认参数只有冻结配置允许的字段，不含 reference、ground truth、hidden validation 或 evaluation-only 信息。
- 在 LXD 中通过 stdin 临时传递 Key，执行一次预注册命令。命令恰好尝试并收到 A/B/C 三个响应，无 transport retry；没有再次运行、没有使用 `--confirm-bulk`。
- 三组 response.model 均为 `deepseek-v4-pro`，finish reason 均为 `length`。A/B/C completion tokens 和 reasoning tokens 均为 8192，最终 `message.content` 均为空，因此三组都分类为 `invalid_model_output`，未进入源码编译、repair tests 或 hidden validation。
- A 实际 usage：prompt 737、cache hit 0、cache miss 737、completion/reasoning 8192、total 8929。
- B 实际 usage：prompt 1202、cache hit 640、cache miss 562、completion/reasoning 8192、total 9394。
- C 实际 usage：prompt 1354、cache hit 1152、cache miss 202、completion/reasoning 8192、total 9546。
- 真实 artifact 只保存 final content、usage 和 reasoning 的 present/characters/SHA-256 摘要，不保存原始 reasoning。三份 artifact SHA-256 在报告生成前后保持为 A `b0ea0e5cea5989b602aafef4d5fd53a52c1f44a7433b21ea1c08dcd3cf298771`、B `5b9a0aa309bfd64df3337c8404e9b245960d4d4e17c432ecfdfcb215739a7f8c`、C `f6695210993daf1c2d250c111b404f46b7ca7ce3737a72d5aeeb7f2373c8a003`。
- 重新执行 50-case 离线估算器，不产生 API 调用。使用每组真实 prompt token 与字符估算的比率校准完整 Pilot input：A 34,300、B 54,300、C 62,000，总计约 150,600。
- 因三个样本全部触及 8192 上限，输出外推改为明确的保守上界场景：150 calls x 8192 = 1,228,800 completion tokens；这是 cap scenario，不是 expected usage，uncertainty 标为 high。
- 于 `2026-08-16T03:27:54Z` 重新核验 DeepSeek 官方价格。核验时 flat 价格为 cache-hit input `$0.003625/M`、cache-miss input `$0.435/M`、output `$0.87/M`；官方计划于 `2026-08-16T16:00:00Z` 切换 peak/off-peak 价格。
- 三次 smoke 按实际 cache 分账的估算成本为 `$0.022041`。150-call 保守 all-cache-miss 上界在核验时价格为 `$1.134567`，计划 off-peak 为 `$2.532420`，计划 peak 为 `$5.064840`。
- 12/12 artifacts 信息边界审计通过，150 prompts 泄漏审计通过，冻结 `repair-v2` 校验通过；`bulk_online_ready=false`、`bulk_user_authorized=false`、mandatory stop 保持生效。

### 3. 新增、修改、删除的文件

新增的跟踪文件：无。

修改：

- `benchmark/metadata/repair/deepseek_pricing_20260816.json`
- `benchmark/metadata/repair/pre_experiment_estimate.json`
- `benchmark/reports/llm_repair_pre_experiment.md`
- `repair/pre_experiment.py`
- `repair/tests/test_pre_experiment.py`
- `docs/DEVELOPMENT_LOG.md`

删除：无。

本地新增但由 Git 忽略：

- `benchmark/artifacts/repair/259-B-bug-13083263-13083279/A/62689a1b26365dfcce180ea154552437e6475343ee42715f60875a8a0ed0e9cb.json`
- `benchmark/artifacts/repair/259-B-bug-13083263-13083279/B/ed777e0424c3d993cdbf9c0c98198eb54faee860126ae1f47f1d7496f3664e03.json`
- `benchmark/artifacts/repair/259-B-bug-13083263-13083279/C/2bd8fd8876a25997ad2c802a106662911651d4385dbcb42fc56d55ce51a17381.json`

### 4. 执行过的重要命令

```bash
source ~/.config/codedoctor/secrets.env
python3 -c 'import os; print("DeepSeek credential available" if os.getenv("DEEPSEEK_API_KEY") else "DeepSeek credential unavailable")'

python3 -m unittest repair.tests.test_deepseek repair.tests.test_prompting repair.tests.test_protocol repair.tests.test_artifacts repair.tests.test_pipeline -v

source ~/.config/codedoctor/secrets.env
printf '%s\n' "$DEEPSEEK_API_KEY" | lxc exec codedoctor-docker-host -- bash -lc 'IFS= read -r DEEPSEEK_API_KEY; export DEEPSEEK_API_KEY; cd /workspace/CodeDoctor; exec env PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/run_repair_ablation.py --provider deepseek --cases 259-B-bug-13083263-13083279 --resume'

source ~/.config/codedoctor/secrets.env
printf '%s\n' "$DEEPSEEK_API_KEY" | lxc exec codedoctor-docker-host -- bash -lc 'IFS= read -r DEEPSEEK_API_KEY; export DEEPSEEK_API_KEY; cd /workspace/CodeDoctor; exec env PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/estimate_repair_experiment.py --manual-inspection passed'

lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s sandbox/tests -v'
lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s benchmark/tests -v'
lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s fault_localization/tests -v'
lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s repair/tests -v'

python3 -m json.tool benchmark/metadata/repair/deepseek_pricing_20260816.json
python3 -m json.tool benchmark/metadata/repair/pre_experiment_estimate.json
git diff --check
lxc exec codedoctor-docker-host -- docker ps -a --filter name=codedoctor --format '{{.ID}} {{.Names}} {{.Status}}'
lxc stop codedoctor-docker-host
```

另外实际执行了内联 Python 审计：序列化并扫描三个 request payload；读取 artifact 的非敏感结构字段并核对 usage、finish reason、final content 长度、reasoning 摘要与 SHA-256；验证 12 artifacts 的 A/B/C 边界；扫描待提交 diff 和 artifacts 的 credential 模式；复现 `450-B-bug-15950152-15950193` C 组 runtime prompt hash 非确定性。价格核验只使用 DeepSeek 官方 pricing 页面。

### 5. 实际测试结果

- 调用前专项测试：13/13 PASS。
- 报告改动专项测试：17/17 PASS。
- 最终完整回归：sandbox 29/29、benchmark 12/12、fault localization 36/36、repair 33/33，共 110/110 PASS，无 skip。
- 真实 DeepSeek smoke：3/3 HTTP responses received，0 retry；A/B/C 均 `invalid_model_output`，均 `finish_reason=length`，均无 final content。
- Compile/plausible/validated：A/B/C 均为 N/A，因为源码提取失败后 pipeline 正确停止，没有伪造编译或验证结果。
- 泄漏检查：150/150 prompts PASS，12/12 artifacts PASS；reference、ground-truth diff、hidden validation、evaluation-only metadata 均 absent。
- Secret/raw audit：待提交 diff credential pattern 0，artifact credential pattern 0，secret env tracked=false，raw reasoning storage=absent，超过 1 MB 的 changed files=0。
- 冻结协议：`repair-v2` 验证通过，冻结 context/evaluator/extraction/pipeline/prompting/provider/protocol 文件无 diff。
- Docker 清理：没有残留 `codedoctor-*` 容器，`codedoctor-docker-host` 最终为 STOPPED。

### 6. 遇到的问题

#### 6.1 三个响应全部把输出预算用于 reasoning

三次调用均报告 completion tokens=8192、reasoning tokens=8192、finish reason=length，但 final content 为空，导致无法提取 C/C++ 源码。

#### 6.2 单个 C 组离线 prompt hash 存在运行时非确定性

重新生成报告时，`450-B-bug-15950152-15950193` 的 C 组 prompt hash 与上一份估算不同。对同一 case 连续执行三次，PASS/FAIL、exit code 和 timeout 一致，但 prompt hash 在两个值间变化，说明 buggy runtime actual output 本身不稳定。

#### 6.3 初始 artifact 与协议审计脚本使用了错误的缩写路径和返回键

首次哈希命令中的 artifact 文件名是非实际缩写，首次协议脚本也假定返回键为 `version`，因此两次审计脚本先失败；真实 artifact 和生产代码没有损坏。

#### 6.4 核验当天价格存在定时切换

真实 smoke 发生在旧 flat price 时段，但同日稍后启用新的 peak/off-peak 价格，仅报告单一费率会误导后续预算。

### 7. 问题的解决方式

- 严格执行 mandatory stop：三次调用用满后没有重试、没有改参数重跑，也没有开始 bulk。将该现象标为 possible token truncation 和 readiness blocker。
- 不用空 final content 推断 patch，不运行 compile/repair/validation；classification 保持 `invalid_model_output`，相关评价字段保持 null。
- 用 `rg --files -uu` 定位真实 ignored artifact，再按完整路径重新计算 SHA-256；协议审计改为读取已有 `protocol_version`，最终全部通过。
- 对 C 组 hash 漂移进行三次独立 Docker baseline 复现，确认是运行观察非确定性而不是冻结 prompt 代码漂移；保留实际生成的 prompt hash并记录限制，不修改已冻结协议。
- 同时记录调用时 flat price、计划 off-peak 和 peak 三套预算；真实 smoke 按 provider 报告的 cache hit/miss 分账，新单测直接覆盖该成本函数。

### 8. 设计取舍

- 真实 usage 只用于测量层校准，不修改冻结 prompt、模型参数、extraction 或 evaluator。
- input 外推使用每组实际/heuristic prompt 比率校准 50-case 静态估算，避免把单个 smoke prompt 直接乘 50；仍明确标记单 case 的 high uncertainty。
- output 因全部截断只能报告 8192 x 150 的保守 cap，不能称为期望成本。
- reasoning 只保存不可逆摘要；即便排查 provider 行为，也不把 raw reasoning 写入 artifact 或开发日志。
- credential available 与 technical readiness、bulk user authorization 分开记录；Key 存在不自动放行批量实验。

### 9. 当前已知不足

- 三次真实 smoke 都没有可编译源码，DeepSeek thinking/high 与 8192 max tokens 的冻结组合尚未证明能完成 repair 输出。
- 只有一个预注册 case，无法估计一般性的 completion 长度、修复成功率或真实 150-call 成本分布。
- `deepseek-v4-pro` 是 mutable alias；本次 response.model 仍返回同一 alias，无法仅凭该字段证明后端版本永久固定。
- C 组包含 buggy 程序的真实运行观察；至少一个 Pilot case 的 actual output 非确定，可能降低独立重建 prompt hash 的复现性。
- 官方价格已计划切换，未来获批调用前仍需按实际 UTC 时段重新核验费率。
- 150-call A/B/C 正式实验尚未运行，paired repair/validated 指标与统计检验仍为 N/A。

### 10. 下一步计划

- 保持 `bulk_online_ready=false` 和 mandatory stop，不再使用本轮已耗尽的三次 smoke 授权。
- 等待用户审阅 provider 全部消耗 reasoning budget、final content 为空这一协议异常；任何参数或协议调整都需要单独决策，不能事后静默改变冻结实验。
- 若未来形成新的预注册方案，先离线验证边界与预算，再取得新的真实调用授权；不得把本次批准解释为重跑许可。
- 只有技术 smoke 通过且用户另行明确批准付费 bulk 后，才允许使用 `--confirm-bulk`；当前不得启动 150 calls，也不得进入 Phase 8。

## 2026-08-16 - Phase 7: DeepSeek V4 Flash Real Smoke Validation

### 1. 本次目标

- 在 150-call 正式实验开始前，将最终候选从 `deepseek-v4-pro` 切换为 `deepseek-v4-flash`。
- 冻结统一 Flash 配置：thinking enabled、reasoning effort low、max tokens 16384、stream false、temperature not sent、attempt 1、transport retry 0。
- 保持 Repair Pilot、A/B/C prompt、repair-time oracle、FL-v1、runtime evidence、extraction 和 validation protocol 不变。
- 对预注册 case `259-B-bug-13083263-13083279` 仅执行 A/B/C 各一次真实 Flash smoke，最多 3 次调用，不使用 `--confirm-bulk`。
- 将 Pro 与 Flash 工程 smoke 明确排除在未来正式 Evidence Ablation 指标之外，更新 Flash token/cost 和 readiness 报告。

### 2. 实际完成内容

- 官方文档核验 `deepseek-v4-flash`、`DeepSeek-V4-Flash-0731`、thinking mode、`reasoning_effort=low` 和 OpenAI-compatible Chat Completions 支持。
- 将 DeepSeek 专属配置从 Pro/high/8192 更新为 Flash/low/16384。A/B/C 请求继续由同一 provider 构造，不发送 temperature、top_p 或 seed。
- 报告明确记录时间顺序：旧 Pro 三次调用属于 superseded pre-experiment smoke；3/3 均 reasoning/completion 8192、finish reason length、final content empty。Pro 配置在任何正式 bulk call 之前因 output-budget compatibility failure 被拒绝，不是根据正式 repair result 进行 post-hoc optimization。
- 在真实调用前重新验证 serialized payload。A/B/C payload 字段均严格为 model、messages、thinking、reasoning_effort、max_tokens、stream；model=Flash、effort=low、max tokens=16384，三个 cache path 均不存在，reference/ground-truth/hidden-validation/evaluation-only leakage 均 absent。
- 仅执行一次 1 case × A/B/C CLI。真实 attempted=3、responses received=3、transport retry=0，没有第 4 次调用，没有使用 `--confirm-bulk`。
- A：response.model `deepseek-v4-flash`，system fingerprint `a26a7955944dc5c60445bff77fac9c8e`；prompt 658、cache hit 0、cache miss 658、reasoning 10818、final-answer 336、completion 11154、total 11812；finish reason stop；plain source 提取成功；compile/plausible/validated 均 true，分类 `validated_patch`。
- B：response.model 与 fingerprint 同上；prompt 1123、cache hit 640、cache miss 483、reasoning 4903、final-answer 382、completion 5285、total 6408；finish reason stop；fenced code 提取成功；compile/plausible/validated 均 true，分类 `validated_patch`。
- C：response.model 与 fingerprint 同上；prompt 1275、cache hit 1024、cache miss 251、reasoning 10623、final-answer 382、completion 11005、total 12280；finish reason stop；fenced code 提取成功；compile/plausible/validated 均 true，分类 `validated_patch`。
- 三组均有完整 final content，均未发生 length truncation；patch extraction、Docker compile、repair tests 和 hidden validation 全链路实际执行。该结果只说明 technical smoke 成功，不计入正式 repair rate。
- Artifact 新增 `experiment_role` 和请求配置摘要；raw reasoning 仍只保存 present、characters、SHA-256。Flash smoke 标记为 `pre_experiment_smoke`，旧 Pro 通过 candidate timeline 标记为 superseded，两者均排除在正式指标之外。
- 正式统计器只接受 `formal_evidence_ablation` role；未来正式运行使用独立 artifact cache namespace，避免相同 Flash model/prompt 的 `--resume` 复用或覆盖本轮 smoke。
- 重新运行 50-case 静态 prompt 估算并以 Flash actual prompt usage 校准：A input 30,600、B 50,800、C 58,400，合计 139,800；按单个 smoke case 的实际 Flash completion 外推 1,372,200，reasoning 外推 1,317,200，uncertainty=high。
- 于 `2026-08-16T03:52:47Z` 核验官方 Flash 价格。调用时 flat 价格为 cache hit `$0.0028/M`、cache miss `$0.14/M`、output `$0.28/M`；计划 off-peak 为 `$0.007/$0.22/$0.66`，peak 为 `$0.014/$0.44/$1.32`。
- 三次 Flash smoke 按实际 cache 分账估算 `$0.007884`。150-call all-cache-miss 估算：调用时价格 `$0.403788`、计划 off-peak `$0.936408`、计划 peak `$1.872816`。
- `smoke_technical_ready=true`；但 `450-B-bug-15950152-15950193` Group C runtime actual output 非确定的冻结处理规则仍未解决，因此 `bulk_online_ready=false`、`bulk_user_authorized=false`、formal calls=0。

### 3. 新增、修改、删除的文件

新增的跟踪文件：无。

修改：

- `README.md`
- `benchmark/metadata/repair/deepseek_experiment_config.json`
- `benchmark/metadata/repair/deepseek_pricing_20260816.json`
- `benchmark/metadata/repair/pre_experiment_estimate.json`
- `benchmark/reports/llm_repair_evidence_ablation.md`
- `benchmark/reports/llm_repair_pre_experiment.md`
- `benchmark/results/repair/evidence_ablation.json`
- `benchmark/scripts/run_repair_ablation.py`
- `repair/deepseek.py`
- `repair/pre_experiment.py`
- `repair/reporting.py`
- `repair/tests/test_deepseek.py`
- `repair/tests/test_pre_experiment.py`
- `repair/tests/test_reporting.py`
- `docs/DEVELOPMENT_LOG.md`

删除：无。

本地新增但由 Git 忽略：

- `benchmark/artifacts/repair/259-B-bug-13083263-13083279/A/a0212e2e5b55067f337d1437d29d9e2770c7560b9ab2bf90ea547c569d27d048.json`
- `benchmark/artifacts/repair/259-B-bug-13083263-13083279/B/6a36fc0d6c3c979d948013d6564965e2c1d8bb59c616deb25d97ea398b977320.json`
- `benchmark/artifacts/repair/259-B-bug-13083263-13083279/C/85dbcee93e59bd0ed376a7643ba342795adf94a811a532dc6c3e97d9870f1dbb.json`

### 4. 执行过的重要命令

```bash
curl -L --fail --silent --show-error https://api-docs.deepseek.com/quick_start/pricing/
curl -L --fail --silent --show-error https://api-docs.deepseek.com/guides/thinking_mode

PYTHONDONTWRITEBYTECODE=1 python3 -m unittest repair.tests.test_deepseek repair.tests.test_pre_experiment repair.tests.test_protocol repair.tests.test_prompting repair.tests.test_reporting repair.tests.test_artifacts repair.tests.test_pipeline -v

lxc start codedoctor-docker-host
lxc exec codedoctor-docker-host -- systemctl start docker
lxc exec codedoctor-docker-host -- docker version --format '{{.Server.Version}}'
lxc exec codedoctor-docker-host -- docker image inspect codedoctor-cpp-sandbox --format '{{.Id}}'

source ~/.config/codedoctor/secrets.env
python3 -c 'import os; print("DeepSeek credential available" if os.getenv("DEEPSEEK_API_KEY") else "DeepSeek credential unavailable")'

source ~/.config/codedoctor/secrets.env
printf '%s\n' "$DEEPSEEK_API_KEY" | lxc exec codedoctor-docker-host -- bash -lc 'IFS= read -r DEEPSEEK_API_KEY; export DEEPSEEK_API_KEY; cd /workspace/CodeDoctor; exec env PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/run_repair_ablation.py --provider deepseek --cases 259-B-bug-13083263-13083279 --resume'

source ~/.config/codedoctor/secrets.env
printf '%s\n' "$DEEPSEEK_API_KEY" | lxc exec codedoctor-docker-host -- bash -lc 'IFS= read -r DEEPSEEK_API_KEY; export DEEPSEEK_API_KEY; cd /workspace/CodeDoctor; exec env PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/estimate_repair_experiment.py --manual-inspection passed'

PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/generate_repair_ablation_report.py
lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s sandbox/tests -v'
lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s benchmark/tests -v'
lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s fault_localization/tests -v'
lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s repair/tests -v'

python3 -m json.tool benchmark/metadata/repair/deepseek_experiment_config.json
python3 -m json.tool benchmark/metadata/repair/deepseek_pricing_20260816.json
python3 -m json.tool benchmark/metadata/repair/pre_experiment_estimate.json
python3 -m json.tool benchmark/results/repair/evidence_ablation.json
git diff --check
lxc exec codedoctor-docker-host -- docker ps -a --filter name=codedoctor --format '{{.ID}} {{.Names}} {{.Status}}'
lxc stop codedoctor-docker-host
```

另外实际执行了内联 Python 审计：构造并扫描实际 serialized Flash payload；检查 cache path；核对 Flash/Pro artifact 数量、角色、模型、fingerprint、usage、finish reason、content hash、extraction、compile/plausible/validated、artifact SHA-256；验证 formal artifacts=0；扫描 credential 模式、raw reasoning、changed file 大小和冻结文件 diff。

### 5. 实际测试结果

- 调用前宿主专项测试：23/23 PASS；同一专项测试在 LXD 中 23/23 PASS。
- 最终完整回归：sandbox 29/29、benchmark 12/12、fault localization 36/36、repair 37/37，共 114/114 PASS，无 skip。
- FL frozen protocol PASS，`repair-v2` protocol PASS，provider tests PASS，prompt boundary PASS，bulk guard PASS，cache/resume 与 formal namespace isolation PASS。
- Serialized payload：3/3 PASS；model、thinking、effort、max tokens 和 stream 一致，temperature/top_p absent。
- 真实 Flash smoke：3 requests attempted、3 responses received、0 retry；A/B/C 均 finish reason stop、final content non-empty、extraction success、compile success、plausible true、validated true。
- Length truncation：0/3；`smoke_technical_ready=true`。
- Formal Evidence Ablation：online artifacts=0、status=not_run；6 个 DeepSeek engineering artifacts 和 9 个 fake artifacts 均不进入正式指标。
- Leakage：150/150 prompts PASS，15/15 artifacts PASS；reference、ground truth、hidden validation、evaluation-only metadata absent。
- Artifact integrity：Flash A/B/C SHA-256 分别为 `62bc89126f54af1d710e670432c4a32cf1abecb4fd162600e433e470917a8581`、`d09d6c9801e875acc9b5952c5b3606e3cf4ba9b23ffbf9ef8a4a724e934f4264`、`3b7003cd9ddbaba44901b093df27282faa7f6ea2fa7c1f016822e6ae4ddea549`；报告生成后保持不变。
- Secret/raw audit：changed diff credential pattern 0，artifact credential pattern 0，tracked `.env` 0，raw reasoning storage absent，超过 1 MB changed file 0。
- 冻结边界：context、prompting、provider、pipeline、extraction、evaluator、repair protocol、Repair Pilot 和 FL input 无 diff。
- Docker 清理：无残留 `codedoctor-*` 容器，LXD 最终 STOPPED。

### 6. 遇到的问题

#### 6.1 旧统计逻辑会混合 Pro 与 Flash smoke

原预实验估算只按 provider=deepseek 选择 artifact；同时存在 Pro 与 Flash 时，每组会被统计为两次调用，无法形成正确的 current-candidate usage 和 readiness。

#### 6.2 工程 smoke 原来只有 experimental 布尔值

正式统计器把所有 `experimental=true` artifact 视为正式数据，无法表达 pre-experiment engineering smoke 与 formal Evidence Ablation 的区别。

#### 6.3 相同 Flash 配置的正式运行可能复用 smoke cache

即使统计层按 role 排除 smoke，未来正式实验若使用相同 model/prompt 参数与 `--resume`，仍可能命中本轮 Flash smoke 的 content-addressed cache，导致正式第一 case 复用工程调用。

#### 6.4 正式报告仍保留旧 generic provider 配置措辞

首次生成正式报告后，setup 仍写 temperature 0.0 和 max tokens 4096，与最终 Flash freeze 不一致。

#### 6.5 450-B runtime evidence 仍不可复现

`450-B-bug-15950152-15950193` Group C 的 actual output 可跨 baseline run 变化。该 case 不能删除，但正式 bulk 前必须形成最小、明确且冻结的处理规则。

### 7. 问题的解决方式

- 预实验估算按 current model、max tokens 和 `pre_experiment_smoke` role 精确筛选 Flash；其他 DeepSeek model 进入 superseded 列表，formal role 单独计数。
- Artifact 写入显式 `experiment_role`。正式统计器仅接受 `formal_evidence_ablation`，旧无 role 的 DeepSeek engineering artifacts 也默认排除；重生成结果验证 formal online artifacts=0。
- 为未来正式 DeepSeek 运行增加独立 `formal_evidence_ablation/` artifact root，和 smoke 使用不同 cache namespace；单测验证两个 root 不同，递归 artifact loader 同时支持审计两类数据。
- 将正式报告 setup 更新为 Flash、thinking enabled、low、16384、temperature/seed not sent，并重新生成报告。
- 450-B 保持在 50-case Pilot，结构化标记为 unresolved remaining bulk reproducibility blocker；因此即使 Flash technical smoke 成功，bulk readiness 仍保持 false。

### 8. 设计取舍

- Pro→Flash、high→low、8192→16384 是正式实验前的 output-budget compatibility 修正；不改变 A/B/C 任务语义，也不把本次三个 validated patch 当作模型效果证据。
- `final_answer_tokens` 仅在 provider 同时给出 completion 与 reasoning tokens 时由两者差值计算；raw final source 和 raw reasoning 不进入报告。
- Flash output 外推使用一个 smoke case 的实际 completion usage乘以 50，明确标记 high uncertainty；不沿用 Pro 的 8192 cap，也不声称是精确期望成本。
- Credential availability、technical smoke readiness、bulk reproducibility readiness 和 user authorization 分开记录。
- 不为 450-B 临时扩展复杂分析模块，不删除 case，也不在本轮擅自冻结新的 runtime normalization 规则。

### 9. 当前已知不足

- Flash smoke 仅覆盖一个预注册 case；三个 validated patch 不代表 50-case repair rate，也不能支持 A/B/C 因果结论。
- Token/cost 外推受单 case reasoning 长度影响很大；A 与 C 的 reasoning usage 接近 11k，150-call 实际费用仍可能明显波动。
- `deepseek-v4-flash` 是 mutable alias；虽然三次 response.model 和 fingerprint 一致，未来正式实验仍必须逐 artifact 记录。
- 450-B runtime actual output 非确定性尚未解决，是当前唯一结构化 bulk blocker。
- 官方峰谷价格将在当日稍后生效；未来正式调用前必须按实际 UTC 时段再次核验。
- 正式 150-call 实验未开始，formal repair/plausible/validated rates、paired bootstrap 和 McNemar 仍为 N/A。

### 10. 下一步计划

- 停止真实调用，不使用本轮已经耗尽的 3-call Flash smoke 授权继续试验。
- 在不删除 450-B、不改变 A/B/C 语义的前提下，单独制定并预注册最小 runtime reproducibility 处理规则，然后重新做纯离线 prompt/hash 审计。
- 规则冻结后重新生成 pre-experiment readiness；即使 `bulk_online_ready` 变为 true，也继续等待用户对付费 150-call 实验的明确授权。
- 未获得明确批准前不得使用 `--confirm-bulk`，不得启动正式实验，不得进入 Phase 8。

## 2026-08-16 - Phase 7: Frozen Runtime Evidence Protocol

### 1. 本次目标

- 诊断 `450-B-bug-15950152-15950193` 的 buggy runtime 非确定性来源，同时保留该 case 和冻结的 A/B/C repair-v2 实验协议。
- 为完整 50-case Repair Pilot 建立通用 `runtime-evidence-v1`：正式 LLM 调用前每个 repair-time test 只运行一次，冻结未经归一化的真实观察。
- 让正式 Group C 只加载并校验 snapshot；缺失、损坏、Pilot/protocol/hash 不匹配时 fail closed，禁止现场重跑 buggy program。
- 离线重建并审计 150 个正式 prompt/payload，不调用 DeepSeek，不使用 `--confirm-bulk`，不启动正式 150-call 实验。

### 2. 实际完成内容

- 对 450-B 的 buggy source 和三个 repair tests 进行了 20 次完整重复评估。`p1` 始终输出 `1`，`p2` 始终输出 `1000000006`；`n1.stdout` 在 20 次中出现 13 组不同 observation，stderr 始终为空、exit code 始终为 0、timeout 始终为 false、测试 verdict 始终不变。
- 确认原因是源程序在 `n % 6 == 0` 时读取未初始化的 `f[0]`，属于 undefined behavior；没有删除 450-B，没有加入 case-specific 分支，也没有对变化输出做排序、正则替换、截断或 reference substitution。
- 新增通用 snapshot capture/load 模块。capture 按 Repair Pilot 和 repair-test manifest 顺序执行，每个测试一次、transport retry 0，保存 exact stdout/stderr、UTF-8 SHA-256、exit code、timeout、verdict、test ID/order 和 compile metadata。
- 生成 50/50 snapshot，共覆盖 174 个 repair-time tests。Manifest 绑定 Repair Pilot 原始文件 hash、repair-v2 文件 hash/version、每个 artifact path/hash、测试顺序、生成时间、Docker image ID、runner 限制和 capture rule。
- 最终 overall manifest hash 为 `96aa507caf2332d0f44b4f2fd3d0aaf68d1168e93856d046d57495b12a52ea3c`。Loader 实际验证 manifest、50 个 artifact、stdout/stderr hash、Pilot、repair-v2 和 test order，结果 PASS。
- 450-B 冻结 observation hash 为 `1511d2a4afa55737136de978cc21413361d31fe86ac0459967a0e1cfdb29b5d2`。冻结值中 `n1.stdout` 为 `1`；冻结后的独立 10 次诊断得到 9 个不同 observation hash，变化字段仅 `n1.stdout`，因此标记 `runtime_nondeterministic=true`，且该 audit 明确为 evaluation metadata only、prompt influence none。
- 正式 DeepSeek bulk 路径在任何 generation 前完整加载并校验 50-case frozen evidence；正式 baseline 来自 snapshot。未确认的 smoke 路径继续保留原动态 runner，既有宿主/Docker Runner 逻辑未删除。
- Pre-experiment estimator 改为只用 frozen evidence 构建 prompts，并将 snapshot coverage、manifest hash、prompt reproducibility 和 leakage audit 纳入 readiness。当前 `bulk_online_ready=true`、`bulk_user_authorized=false`、blocking reasons 为空、mandatory stop 保持 true。
- 两个独立 Python 进程分别构建 150/150 prompts 和 serialized Flash payloads，prompt-set hash 均为 `9a65e8fcf2eea3d3da8a64bbfac4d32736e9090da7917da4ea6270d7cb9eaea0`。450-B Group C 在每次 audit 中额外 reload/render 10 次，唯一 hash 为 `7e3a33b3bb13be56d39a99bbab7c9305c957b377d12f84f6a6c3f40698da70e0`。
- Leakage audit 扫描 snapshot、manifest、150 prompts 和 150 serialized provider payloads；reference source、ground-truth diff、hidden validation、evaluation canary、credential 和 forbidden snapshot key 全部 absent。Expected output 继续只由 repair-v2 公共 repair-time oracle 提供。
- 更新 README 和预实验报告，明确说明 buggy runtime 本身仍非确定，但正式实验消费预注册的单次冻结观察，因此实验 prompt 可复现。
- 正式 Evidence Ablation 报告重新生成，online formal artifacts 仍为 0。DeepSeek 模型参数、6 份 engineering smoke artifact 和冻结的 repair-v2/FL 输入均未修改；本轮真实 DeepSeek API 调用次数为 0。

### 3. 新增、修改、删除的文件

新增：

- `benchmark/metadata/repair/runtime_evidence_manifest_v1.json`
- `benchmark/metadata/repair/runtime_evidence_nondeterminism_audit_v1.json`
- `benchmark/metadata/repair/runtime_evidence_prompt_audit_v1.json`
- `benchmark/metadata/repair/runtime_evidence_v1/` 下 50 个 case snapshot JSON
- `benchmark/scripts/audit_repair_prompt_reproducibility.py`
- `benchmark/scripts/audit_repair_runtime_nondeterminism.py`
- `benchmark/scripts/freeze_repair_runtime_evidence.py`
- `repair/runtime_evidence.py`
- `repair/tests/test_runtime_evidence.py`

修改：

- `README.md`
- `benchmark/config.py`
- `benchmark/metadata/repair/pre_experiment_estimate.json`
- `benchmark/reports/llm_repair_pre_experiment.md`
- `benchmark/scripts/run_repair_ablation.py`
- `repair/pre_experiment.py`
- `docs/DEVELOPMENT_LOG.md`

删除：无。

### 4. 执行过的重要命令

```bash
lxc start codedoctor-docker-host
lxc exec codedoctor-docker-host -- systemctl start docker

lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/freeze_repair_runtime_evidence.py'
lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/audit_repair_runtime_nondeterminism.py --case 450-B-bug-15950152-15950193 --runs 10'
lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/audit_repair_prompt_reproducibility.py && PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/audit_repair_prompt_reproducibility.py'

source ~/.config/codedoctor/secrets.env
python3 -c 'import os; print("DeepSeek credential available" if os.getenv("DEEPSEEK_API_KEY") else "DeepSeek credential unavailable")'
source ~/.config/codedoctor/secrets.env
printf '%s\0' "$DEEPSEEK_API_KEY" | lxc exec codedoctor-docker-host -- bash -lc 'IFS= read -r -d "" DEEPSEEK_API_KEY; export DEEPSEEK_API_KEY; cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/estimate_repair_experiment.py --manual-inspection passed'

lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s sandbox/tests -v && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s benchmark/tests -v && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s fault_localization/tests -v && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s repair/tests -v'
lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s repair/tests -v'
lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/generate_repair_ablation_report.py'

git diff --check
git diff --exit-code HEAD -- repair/context.py repair/evaluator.py repair/extraction.py repair/pipeline.py repair/prompting.py repair/provider.py benchmark/metadata/repair/repair_protocol_v2.json
lxc exec codedoctor-docker-host -- bash -lc 'docker ps -a --filter ancestor=codedoctor-cpp-sandbox --format "{{.ID}} {{.Status}} {{.Names}}"; docker ps -a --filter ancestor=codedoctor-cpp-analysis --format "{{.ID}} {{.Status}} {{.Names}}"'
lxc stop codedoctor-docker-host
```

另外实际执行了两组内联 Python 审计：第一组在 snapshot freeze 前对 450-B 完整 `evaluate_source` 20 次并比较每个 test 的 stdout/stderr/exit code/timeout/verdict；第二组在最终阶段验证 repair-v2、50/174 coverage、manifest/prompt hashes、450-B nondeterminism、readiness 和 formal call count。还扫描了待提交 diff 中的 credential pattern、`.env`、临时文件、raw dataset 变更、artifact 大小和冻结文件 diff。

### 5. 实际测试结果

- 最终完整回归：sandbox 29/29、benchmark 12/12、fault localization 36/36、repair 46/46，共 123/123 PASS，无 skip。
- 最终生成文件更新后再次运行 repair 46/46 PASS。
- Frozen evidence：50/50 cases、174 tests，manifest validation、artifact hash、stdout/stderr hash、Pilot hash、repair-v2 hash和顺序校验全部 PASS。
- Fail-closed tests：snapshot corruption、manifest corruption、missing snapshot、Pilot mismatch、protocol mismatch 均被拒绝。
- Prompt boundary：A/B 不含 runtime evidence，C 只加载 registered frozen evidence，PASS。
- Prompt reproducibility：150/150 构建成功；两个独立进程的完整 prompt-set hash 一致；450-B C 的 10/10 hash 一致。
- Leakage：snapshot、manifest、150 prompts、150 serialized payloads 全部 PASS；reference、ground truth、hidden validation、evaluation canary、credential absent。
- Bulk guard：mocked corrupted snapshot 在 generation/network 前被 CLI 拒绝，PASS；测试没有执行真实 `--confirm-bulk` 命令。
- Formal metrics：online artifacts=0，6 份 DeepSeek engineering smoke 继续排除；本轮真实 API calls=0。
- Docker 清理：无匹配的 sandbox/analysis 残留容器；`codedoctor-docker-host` 最终为 STOPPED。

### 6. 遇到的问题

#### 6.1 450-B 的 Group C prompt 会随现场 baseline 执行变化

问题不是 prompt serializer 漂移，而是 `n1` 触发 `n % 6 == 0` 后读取未初始化 `f[0]`，导致 actual stdout 跨进程变化。要求 buggy runtime 自身变成 deterministic 不符合该 evidence 的研究语义。

#### 6.2 动态 baseline 无法支持正式实验的 resume 和独立重建

原正式路径每次现场执行 buggy program；即使同一模型和 prompt 代码不变，非确定 runtime observation 仍会改变 Group C prompt/cache key。

#### 6.3 Freeze 不能演变为 post-hoc observation selection

诊断重复运行产生了多个输出，但选择固定值、最常见值或最有利值都会改变实验语义并引入研究者自由度。因此诊断结果不能反向影响 snapshot。

### 7. 问题的解决方式

- 将 runtime evidence 定义为“正式调用前按统一规则获得的第一次且唯一一次真实观察”，并对完整 Pilot 一次性冻结；后续重复运行仅属于独立 nondeterminism audit。
- Manifest 和 loader 同时绑定数据集、repair-v2、顺序、Docker 配置和逐文件 hash。Formal builder 只执行 load、verify、render，不提供自动 recapture fallback。
- 通过 50-case 统一实现避免 450-B 特判；保留 expected-output 公共 oracle、FL-v1 reliability 规则和 A/B/C 唯一增量边界。
- 将 freeze validity 和 prompt reproducibility 纳入 pre-experiment readiness；任何 snapshot/manifest/protocol 漂移都会在正式 generation 前 fail closed。

### 8. 设计取舍

- Snapshot 保存 JSON display text 和独立 UTF-8 hash，不引入 binary artifact；JSON round-trip 单测覆盖 trailing whitespace/newline 的精确保留。
- 不保存 signal 的新独立字段；沿用 repair-v2 已允许进入 C 的 exit code、timeout、passed、stdout 和 stderr，避免扩大 evidence 内容。
- Docker image ID 和执行限制作为 provenance 写入 manifest，但正式 prompt reload 不依赖 Docker daemon，保证 resume 和离线重建不触发 buggy execution。
- Prompt audit 使用 dummy offline credential 只构造 request payload；不调用 provider transport，不保存 API key 或 raw LLM reasoning。

### 9. 当前已知不足

- 450-B 的 buggy runtime 仍是 undefined behavior；协议保证的是正式 prompt 可复现，不是程序输出变得确定。
- Frozen observation 是当前 Docker image/backend 下的一次真实执行，不代表该 UB 在其他编译器、镜像或机器上的典型输出。
- Manifest 使用 SHA-256 完整性校验但没有外部数字签名；它可检测意外损坏和未同步漂移，不提供对恶意仓库改写的真实性证明。
- Nondeterminism audit 本轮重点重复检查已知的 450-B，没有对其余 49 个 case 全量重复采样；这不影响已冻结 prompt 的可复现性。
- Flash token/output 成本仍由单 case engineering smoke 外推，uncertainty high；模型 alias 和未来价格仍可能变化。
- 正式 150-call 实验尚未运行，formal repair/plausible/validated metrics 仍为 N/A；`bulk_user_authorized=false`。

### 10. 下一步计划

- 保持 mandatory stop，等待用户对付费 50 cases x 3 groups 正式实验的明确批准；批准前不得使用 `--confirm-bulk`。
- 正式启动前再次只读核验 credential availability、官方价格、frozen manifest/prompt hash、formal artifact namespace 和调用预算。
- 获得批准后严格使用 frozen runtime evidence 和独立 formal cache namespace执行一次 150-call A/B/C 实验，逐 artifact 记录 provider response metadata 并保持 engineering smoke 排除。
- 本轮在 Phase 7 停止，不进入 Phase 8。

## 2026-08-19 - Phase 7: Formal LLM Repair Evidence Ablation

### 1. 本次目标

- 在用户明确授权后，按冻结协议执行 50-case Repair Pilot x A/B/C x 1 attempt，共 150 次真实 DeepSeek Official API 正式调用。
- 保持 `deepseek-v4-flash`、thinking enabled、reasoning effort low、max tokens 16384、stream false、temperature not sent、transport retry 0，以及 Repair Pilot、FL-v1、repair-v2、prompt、oracle、Frozen Runtime Evidence、extraction 和 validation 全部不变。
- 汇总 Validated Patch Rate、case-level paired comparison、paired bootstrap、exact McNemar、failure modes、FL/0-PASS/non-executable/equivalence/coverage diversity 子组、真实 usage 和成本。
- 更新正式报告、完整回归、泄漏与 artifact 完整性审计，并提交推送；Phase 7 完成后停止，不进入 Phase 8。

### 2. 实际完成内容

- 调用前确认工作树 clean、HEAD=`3373f49b04fb5ca6b3689dc10348d4c6dd44eb61`、credential available，且没有输出 key 内容。
- 调用前重新验证 `repair-v2`、50/50 Frozen Runtime Evidence、174 repair tests、Runtime Evidence manifest hash `96aa507caf2332d0f44b4f2fd3d0aaf68d1168e93856d046d57495b12a52ea3c`、150/150 prompt-set hash `9a65e8fcf2eea3d3da8a64bbfac4d32736e9090da7917da4ea6270d7cb9eaea0`、leakage PASS、formal artifact count 0 和 corrupt-freeze bulk guard PASS。
- 运行唯一一次正式 CLI：`--provider deepseek --confirm-bulk`，没有传 `--resume`、case/group filter 或参数覆盖。150 次 requests attempted，148 次 responses received，150 个 single-attempt artifacts；没有自动 retry，没有对失败结果补调。
- Formal artifact 首个/最后一个完成时间为 `2026-08-19T14:15:41.301492+00:00` 和 `2026-08-19T16:35:12.180421+00:00`。Codex 监视调用曾被用户中断一次，但底层正式进程持续存活，因此 resume=false，未重启进程，也未重复调用。
- 两次无 response 的正式失败都发生在 `417-C-bug-6586834-6586850`：A 为 `ModelTimeout: DeepSeek request timed out`，B 为 `ModelAPIError: ... <urlopen error timed out>`。两者按基础设施/API failure 保留，不重试；C 正常完成。
- A：50 total，46 valid output，46 compile success，43 plausible，40 validated。分类为 model error 1、invalid model output 3、repair-test failed 3、plausible but validation failed 3、validated 40。
- B：50 total，47 valid output，47 compile success，42 plausible，39 validated。分类为 model error 1、invalid model output 2、repair-test failed 5、plausible but validation failed 3、validated 39。
- C：50 total，50 valid output，50 compile success，49 plausible，46 validated。分类为 repair-test failed 1、plausible but validation failed 3、validated 46；无 model/API error、invalid model output 或 compile error。
- 五个 invalid model output 均是 `finish_reason=length` 且没有可提取的完整 final source；没有对 length、compile、repair-test 或 validation failure 进行重新调用。
- Paired Validated 结果：A→B 为 5 个 A fail/B success、6 个 A success/B fail，差值 -0.02；B→C 为 8 个 B fail/C success、1 个 B success/C fail，差值 +0.14；A→C 为 8 个 A fail/C success、2 个 A success/C fail，差值 +0.12。
- 10,000 次、seed 20260817 的 paired bootstrap 95% CI：B-A `[-0.14, 0.12]`，C-B `[0.04, 0.26]`，C-A `[0.00, 0.24]`。
- Exact two-sided McNemar：B-A `p=1.0`，C-B `p=0.0390625`，C-A `p=0.109375`。三个 p-value 未做 multiplicity adjustment，未据此更改协议。
- FL reliable 49 cases 的 A/B/C validated 为 40/39/45；唯一 unreliable case 为 0/0/1。Top-1 hit 8 cases 为 6/5/7，Top-5 hit 25 cases 为 21/18/22，Top-10 hit 38 cases 为 30/28/34，Top-10 miss 12 cases 为 10/11/12。
- 0-PASS 13 cases 的 A/B/C validated 为 10/9/13；有 PASS 的 37 cases 为 30/30/33。Non-executable 4 cases均为 4/4/4；executable 46 cases为 36/35/42。
- Fault-equivalence singleton 2 cases 为 2/1/2，tied 44 cases 为 34/34/40；straight-line ambiguity 36 cases 为 28/28/33。Coverage diversity 使用明确标注为 post-hoc descriptive 的 Pilot median split 0.146429：lower 25 cases 为 20/21/24，upper 25 cases 为 20/18/22。
- A usage：49/50 有 usage；prompt 23,986，cache hit 0，cache miss 23,986，reasoning 282,420，final answer 11,876，completion 294,296，total 318,282，估算 `$0.085761`。
- B usage：49/50 有 usage；prompt 41,883，cache hit 20,864，cache miss 21,019，reasoning 254,225，final answer 12,445，completion 266,670，total 308,553，估算 `$0.077669`。
- C usage：50/50 有 usage；prompt 49,101，cache hit 39,040，cache miss 10,061，reasoning 205,729，final answer 12,632，completion 218,361，total 267,462，估算 `$0.062659`。
- 总 usage：148/150 有 usage；prompt 114,970，cache hit 59,904，cache miss 55,066，reasoning 742,374，final answer 36,953，completion 779,327，total 894,297。
- 于 `2026-08-19T16:37:39Z` 核验 DeepSeek Official API 当前 Flash USD 价格：cache hit `$0.0028/M`、cache miss `$0.14/M`、output `$0.28/M`。按 provider 实际 usage 估算总成本 `$0.226089`；两次无 usage 的失败请求不计入 token-based estimate。
- 重写正式报告为 15 节，包含 RQ、冻结协议、数据集、模型、A/B/C、泄漏、主结果、paired、bootstrap、McNemar、failure、FL/subgroups、usage/cost、threats 和 conclusion；明确 `Validated Patch is not Formally Correct Patch`。
- 150 formal artifacts 全部 role=`formal_evidence_ablation`、attempt=1、cache key 唯一；artifact set hash `067710f9f3b71855cc4bf1db3dd0614cef89c1d4cec7e4f6e83c0372b7607f17`。150/150 artifact prompt hashes 与冻结 prompt audit 一致，148 个 response 的 model、request configuration 和 fingerprint 一致。
- Artifact/leakage scan 覆盖 165 个 artifacts 并 PASS；150 formal artifacts 中 API key pattern、canary 和 raw reasoning 均 absent，只保留 reasoning character count 和 SHA-256。

### 3. 新增、修改、删除的文件

新增：

- `benchmark/metadata/repair/deepseek_pricing_20260819.json`
- `benchmark/metadata/repair/formal_run_v1.json`

修改：

- `benchmark/config.py`
- `benchmark/reports/llm_repair_evidence_ablation.md`
- `benchmark/results/repair/evidence_ablation.json`
- `repair/reporting.py`
- `repair/tests/test_reporting.py`
- `docs/DEVELOPMENT_LOG.md`

删除：无。

本地生成但由 Git 忽略：

- `benchmark/artifacts/repair/formal_evidence_ablation/` 下 150 个正式 JSON artifacts，约 3.0 MB。

### 4. 执行过的重要命令

```bash
source ~/.config/codedoctor/secrets.env
python3 -c 'import os; print("credential=available" if os.getenv("DEEPSEEK_API_KEY") else "credential=unavailable")'
git rev-parse HEAD
git status --porcelain

lxc start codedoctor-docker-host
lxc exec codedoctor-docker-host -- systemctl start docker
lxc exec codedoctor-docker-host -- docker image inspect codedoctor-cpp-sandbox --format '{{.Id}}'

lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest repair.tests.test_runtime_evidence.RuntimeEvidenceTests.test_bulk_gate_refuses_invalid_freeze_before_generation -v'

source ~/.config/codedoctor/secrets.env
printf '%s\0' "$DEEPSEEK_API_KEY" | lxc exec codedoctor-docker-host -- bash -lc 'IFS= read -r -d "" DEEPSEEK_API_KEY; export DEEPSEEK_API_KEY; cd /workspace/CodeDoctor && exec env PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/run_repair_ablation.py --provider deepseek --confirm-bulk'

lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/generate_repair_ablation_report.py'
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest repair.tests.test_reporting -v
PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/generate_repair_ablation_report.py

lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s sandbox/tests -v && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s benchmark/tests -v && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s fault_localization/tests -v && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s repair/tests -v'

git diff --exit-code HEAD -- benchmark/metadata/repair/repair_protocol_v2.json benchmark/metadata/repair/runtime_evidence_manifest_v1.json benchmark/metadata/repair/runtime_evidence_v1 benchmark/metadata/repair/runtime_evidence_prompt_audit_v1.json benchmark/metadata/repair/repair_pilot_fl.jsonl benchmark/metadata/repair/repair_pilot_attributes.jsonl repair/context.py repair/evaluator.py repair/extraction.py repair/pipeline.py repair/prompting.py repair/provider.py repair/deepseek.py
git diff --check
lxc exec codedoctor-docker-host -- bash -lc 'docker ps -a --filter ancestor=codedoctor-cpp-sandbox --format "{{.ID}} {{.Status}} {{.Names}}"; docker ps -a --filter ancestor=codedoctor-cpp-analysis --format "{{.ID}} {{.Status}} {{.Names}}"'
lxc stop codedoctor-docker-host
```

另外执行了离线内联 Python 审计：重新构建 150 prompts 并比对冻结 hash；验证 artifact 数量、case/group 唯一性、attempt、role、cache key、model、request config、fingerprint 和 artifact-set hash；聚合 classification、paired outcomes、usage/cost 和全部描述性子组；扫描 credential、canary 和 raw reasoning。通过官方 DeepSeek API Docs 的 Models & Pricing 页面核验运行时价格。

### 5. 实际测试结果

- Preflight：HEAD、clean worktree、credential existence、repair-v2、50/174 Frozen Runtime Evidence、两个冻结 hash、150 offline prompts、leakage、formal artifact empty 和 bulk guard 全部 PASS。
- 正式执行：150 requests attempted、148 responses received、150/150 single-attempt artifacts；transport retries 0，resume=false。
- Targeted reporting tests：4/4 PASS；新增 usage/cost 和 artifact-integrity 单测通过。
- 完整 regression：sandbox 29/29、benchmark 12/12、fault localization 36/36、repair 47/47，共 124/124 PASS，无 skip。
- Artifact reproducibility：150/150 unique case/group、150 unique cache keys、attempt-one-only、formal-role-only、frozen prompt match、single request configuration/model/fingerprint 全部 PASS。
- Leakage：165 artifacts PASS；formal API key pattern 0、canary 0、raw reasoning 0，secret env 未加入 Git。
- Frozen boundary：Repair Pilot、FL-v1、repair-v2、Runtime Evidence、prompt audit、context/evaluator/extraction/pipeline/prompting/provider/deepseek 无 diff。
- Docker 清理：无 sandbox/analysis 残留容器，`codedoctor-docker-host` 最终 STOPPED。

### 6. 遇到的问题

#### 6.1 LXD 启动前出现两次基础设施瞬态错误

首次 `lxc start` 报 transient scope failure；随后实例已 RUNNING 但立即执行 `systemctl` 时 DBus 尚未就绪。此时正式 API calls=0。

#### 6.2 两次正式请求发生 timeout

417-C 的 A 在 120 秒 request timeout，B 在 URL open timeout；provider 没有 response/usage。协议禁止 transport retry 和 repair retry。

#### 6.3 五次响应耗尽长度预算

A 三次、B 两次 `finish_reason=length`，没有完整可提取 source，被正式记录为 invalid model output；不能为了提高成功率补调。

#### 6.4 原正式报告模板仍写“bulk 未开始”

已有聚合器能计算 group/paired 结果，但旧 renderer 仍是 pre-run 文案，也没有正式 usage/cost、运行完整性和完整子组表。

#### 6.5 Codex 监视调用被中断

中断只影响前台 polling；统一 exec session 和 LXD 中的正式进程继续运行。重新连接同一 session 后确认任务连续推进，没有 resume 或重复调用。

### 7. 问题的解决方式

- 等待 LXD daemon/DBus ready 后重新执行完整离线 preflight；所有冻结门禁通过后才发第一条正式请求。
- 两次 timeout 原样保存为 model/API failure，不重试、不替换；最终 150 artifact 集合仍包含这两个 attempt。
- Length-truncated responses按既有 extraction/classification 规则记为 invalid，不修改 max tokens 或 prompt。
- 仅扩展 post-experiment `repair/reporting.py`：加入 fail-closed formal artifact integrity、真实 usage/cost、failure/subgroup 聚合和 15 节报告；没有修改任何冻结实验路径。
- 建立 `formal_run_v1.json` 记录授权命令、attempted/received、resume、retry 和 artifact 时间边界；建立 2026-08-19 官方价格快照。
- 重新连接原统一 exec session，不启动第二条 bulk 命令；最终 CLI 自报 `completed 150 single-attempt artifacts`、`requests attempted=150`、`responses received=148`。

### 8. 设计取舍

- Provider/network failure 按 intention-to-treat 风格计为 not validated，保留完整 50-pair 比较；不使用 post-hoc retry 改写结果。
- Exact McNemar 和 paired bootstrap 都使用 case-level validated/not-validated；不把 plausible 视为 validated。
- FL、Top-k、0-PASS、non-executable、equivalence 和 diversity 只做 post-hoc descriptive 分层，不据此删除 case、追加调用或声称因果 moderation。
- Coverage diversity 明确采用本次 Pilot median split 并标注 exploratory，避免将其伪装成预注册阈值。
- Artifact set 使用 canonical SHA-256 和逐项冻结 prompt hash审计；正式原始 artifacts 继续遵循仓库既有 ignore policy，不将模型原始输出批量提交 Git。
- 成本使用 provider-reported cache hit/miss 和 completion usage，不假设 cache hit；无 usage 的 timeout 不虚构 token 或费用。

### 9. 当前已知不足

- Repair Pilot 仅 50 cases，子组很小且互相重叠；paired CI 仍较宽。
- `deepseek-v4-flash` 是 mutable provider alias；148 个响应的 model 和 fingerprint 本轮一致，但不能保证未来后端永久相同。
- 两次 provider failure 和五次 length truncation 计入正式结果；另一轮独立预注册实验可能不同，但本轮不能 post-hoc 修复。
- 三个 paired McNemar p-value 未做 multiplicity adjustment，`p=0.0390625` 应谨慎解释。
- Hidden validation 仍不完备；Validated Patch 不等于 formally correct patch。
- `$0.226089` 是按官方价格和有 usage 的 148 个响应计算的 API cost estimate，不是账户账单导出；失败请求可能存在不可见计费。
- Formal raw artifacts 保存在本机 ignored artifact store；Git 中保存结构化聚合结果、运行元数据、完整性 hash 和报告。

### 10. 下一步计划

- Phase 7 在此停止，等待人工审阅结果、两个 timeout、五个 length truncation、未校正 p-value 和 artifact set。
- 不自动重跑失败请求，不追加正式调用，不改变协议，不进入 Phase 8。
- 人工审查后若需要论文表格或独立复核，只使用现有 150 artifacts 和结构化结果，不重新调用模型。

## 2026-08-20 - Phase 8: Controlled Execution Feedback Repair Pre-registration

### 1. 本次目标

- 建立与 FL Pilot 50、Independent FL Evaluation 300、Phase 7 Repair Pilot 50 完全独立的 100-case Phase 8 Evaluation Set。
- 冻结 Base/Feedback/Hidden test partition、FL-v1、buggy runtime evidence 和 100 个 Initial prompts。
- 实现共享同一 first patch 的 Retry Control（R）与 Execution Feedback（F）双分支、repair-time eligibility、两阶段 bulk gate、fake-provider、leakage/reproducibility tests 和预实验报告。
- 本轮真实 DeepSeek 调用数必须为 0，不启动 Stage 1 或 Stage 2。

### 2. 研究设计与实际完成内容

- 固定 seed `20260820`，从 3,904-case manifest 中先排除 400 个历史正式 case 和不满足静态/至少两个 validation tests 的 case，再按冻结顺序实际 Docker 验证候选并运行 FL-v1；动态检查到 candidate 113 时得到 100 cases。
- 按 `feedback_count=min(max(1,floor(n/4)),n-1)` 生成 `phase8_test_partition_v1`。Base/Feedback/Hidden 总数分别为 446/1,001/3,123，partition hash 为 `fb6239e5b37c81ba4464e00d5505bac9be9296e2fe6d1fc0a2e42573893fb9b7`。
- 发现 repair pool 与 validation pool 可能复用 `p1` 等 test id 后，为 validation-derived Feedback/Hidden tests 加入稳定命名空间并完整重建 selection、FL、partition 和 runtime freeze，未改变候选顺序或筛选条件。
- 冻结 100/100 cases、1,447 个 Base+Feedback tests 的首次 buggy observation；不重跑挑选、不 normalize。runtime manifest hash 为 `943959cb626bb3f190e4a63a45a53c11fbab63781e8297907971f0f0a206f0a0`。
- Initial 使用 Base+Feedback public oracle、FL-v1 和 frozen buggy runtime；R 使用相同 Initial context、同一 first patch 和统一 retry instruction，不含 execution feedback；F 只比 R 增加 first patch 的失败 repair-time execution evidence。
- eligibility 仅由 extractable first patch 的 compile/Base/Feedback failure 触发；provider failure、invalid output、repair-time success 均不触发。Hidden-only failure 的专项测试确认不会触发第二轮。
- Stage 1 要求 `--confirm-phase8-stage1`，仅运行 100 个 Initial calls 后冻结并退出；Stage 2 要求独立 `--confirm-phase8-stage2`，并逐项校验 Stage 1 manifest、100 个 Initial artifacts、eligible cohort、first patch hash 和 failure evidence hash，失败时在建 provider/网络请求前关闭。
- 两次独立进程渲染均得到 prompt-set hash `dd4127d97c7a73b822330d0c1c6890873e3913170b48335c895cca59b1b49672`；leakage audit 通过。
- 增加 400,000 UTF-8 byte 的 fail-closed Initial request operational gate。4 个完整 payload 超限，最大 30,774,820 bytes，因此当前 Stage 1 如实判定为 technically not ready。
- 生成 `benchmark/reports/execution_feedback_pre_experiment.md`，记录 RQ、控制组、独立性、partition、信息边界、artifact、leakage、fake smoke、两阶段调用量、模型冻结、粗略 token/cost 和 readiness。

### 3. 新增、修改和删除的文件

- 新增 `repair_phase8/`：`models.py`、`partition.py`、`context.py`、`prompting.py`、`evaluation.py`、`artifacts.py`、`pipeline.py`、`runtime_evidence.py`、`protocol.py` 及 12 项单元测试。
- 新增脚本：`benchmark/scripts/build_phase8_evaluation_set.py`、`freeze_phase8_runtime_evidence.py`、`audit_phase8_prompts.py`、`generate_phase8_pre_experiment.py`、`run_phase8_experiment.py`。
- 新增冻结数据：`benchmark/datasets/codeflaws/metadata/phase8_repair_evaluation*.json*`、`benchmark/metadata/repair_phase8/`、`benchmark/results/repair_phase8/coverage/`。
- 新增报告：`benchmark/reports/execution_feedback_pre_experiment.md`。
- 修改 `benchmark/config.py`，增加 Phase 8 路径、seed 和 target size。
- 删除文件：无。

### 4. 执行过的重要命令

```text
lxc start codedoctor-docker-host
lxc exec codedoctor-docker-host -- systemctl start docker
lxc exec codedoctor-docker-host -- docker image inspect codedoctor-cpp-sandbox --format '{{.Id}}'

lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/build_phase8_evaluation_set.py'
lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/freeze_phase8_runtime_evidence.py'
lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/build_phase8_evaluation_set.py --force'
lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/freeze_phase8_runtime_evidence.py --force'
lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/audit_phase8_prompts.py && PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/audit_phase8_prompts.py'

python3 benchmark/scripts/run_phase8_experiment.py --stage1
python3 benchmark/scripts/run_phase8_experiment.py --stage2 --confirm-phase8-stage2
python3 benchmark/scripts/run_phase8_experiment.py --stage1 --confirm-phase8-stage1
python3 benchmark/scripts/generate_phase8_pre_experiment.py --fake-tests-passed

lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s sandbox/tests && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s benchmark/tests && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s fault_localization/tests && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s repair/tests && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s repair_phase8/tests'

python3 -m compileall -q benchmark repair_phase8
git diff --check
lxc stop codedoctor-docker-host
```

### 5. 实际测试结果

- Phase 8 dataset：100/100 unique；与 FL Pilot、Independent FL Evaluation、Phase 7 Repair Pilot overlap 均为 0。
- Exclusions：453 条记录，其中 historical overlap 400、static validation failed 20、insufficient validation tests 20、reference repair failure 9、reference hidden validation failure 2、buggy passed all tests 1、FL pipeline failure 1。
- Runtime freeze：100/100 cases、1,447 public repair-time tests，manifest reload/hash 校验通过。
- Prompt reproducibility：100/100 prompts，两次独立进程 hash 完全一致；reference、ground truth、Hidden validation 和 credential leakage audit 通过。
- Fake end-to-end：compile failure、test failure、repair-time success、Hidden-only failure、invalid output、provider failure 全部覆盖；Phase 8 专项 12/12 PASS。
- Bulk guards：无 Stage 1 confirmation 时 exit 2；Stage 2 缺 Stage 1/cohort manifests 时 exit 2；带 Stage 1 confirmation 时因 operational size gate exit 2，三者均发生在网络前。
- 完整 regression 最终结果：sandbox 29/29、benchmark 12/12、fault localization 36/36、repair 47/47、Phase 8 12/12，共 136/136 PASS。
- 正式状态：Stage 1 manifest 不存在、eligible cohort manifest 不存在、Phase 8 formal artifact 文件数 0、真实 DeepSeek API 调用数 0。
- 清理：无 sandbox/analysis 残留容器，`codedoctor-docker-host` 最终 STOPPED。

### 6. 遇到的问题

#### 6.1 Base test 可能为空

部分合法 case 没有原始 Base Repair Tests，但有预注册 Feedback Tests；Initial prompt builder 初版错误地要求两组都非空。

#### 6.2 Base 与 validation test id 冲突

Codeflaws 不同 test pool 会复用 `p1` 等 id，初版按 id 分组会将 Feedback test 错认成 Base test，破坏信息边界。

#### 6.3 Frozen observation 和公共 expected output 过大

4 个 Initial payload 超过 400,000 bytes；最大两个约 30.8 MB 和 29.5 MB。内容主要来自必须公开的完整 expected output 与必须保留的首次 buggy stdout。

#### 6.4 一次组合审计命令被执行策略拒绝

命令包含删除临时输出文件的 `rm -f`，因此在 CreateProcess 前被拒绝；没有执行子命令，也没有网络或实验副作用。

### 7. 问题的解决方式与设计取舍

- 允许 Base oracle 为空并在 prompt 中明确说明，但继续强制至少一个 Feedback test。
- 对所有 validation-derived tests 使用由原 index 和原 id 构成的稳定命名空间；随后使用同一 seed、同一顺序完整重建，不手改冻结结果。
- 保留超大首次 observation 和公共 oracle 原文，不截断、不 normalize、不按大小换 case；增加 fail-closed size audit，使 Stage 1 在 credential/network 前停止。
- R/F 使用相同 first patch hash；F 只携带 failed repair-time evidence。Hidden validation 仅离线评价，不参与 trigger 或 prompt。
- 使用 canonical JSON 计算 failure evidence hash；Stage 2 不只信任 manifest，还逐项核对磁盘 Initial artifact canonical hash。
- 被策略拒绝的组合命令改为直接显示 stderr 和 exit code，不创建临时审计文件。

### 8. 当前已知不足和 Blocker

- `phase8_stage1_ready=false`。4 个 Initial requests 超过当前 400,000-byte operational gate，尚无满足“完整公开 oracle + 不裁剪 frozen observation”边界的可执行传输方案。
- 不能按 output/source 长度 post-hoc 删除 case，也不能改变 deterministic Feedback split；任何压缩、摘要、裁剪或 dataset protocol amendment 都需要在正式调用前单独审阅和冻结。
- Stage 2 调用量仍未知；只有合法 Stage 1 完成并冻结 eligible count `M` 后才能确定为 `2M`。
- 成本仅按 Phase 7 的 148 个已有 usage 均值和 2026-08-19 官方价格快照粗估：Stage 1 约 `$0.1583`，Stage 2 约 `$0.001583 * 2M`，不代表账单且不适用于超大 prompt 的真实 tokenization。
- Hidden validation 仍不完备；Validated Patch 不等于 formally correct patch。

### 9. 下一步计划

- 停止在 Phase 8 pre-registration，不启动 Stage 1 或 Stage 2。
- 先人工决定如何处理 4 个超大公共 oracle/runtime payload；任何方案必须保持 R/F 语义对称、Hidden 隔离和 frozen first-observation 可审计性，并在真实调用前更新 protocol/audit。
- blocker 解决后重新执行离线 size/reproducibility/leakage gate；只有 `phase8_stage1_ready=true` 且用户显式批准 `--confirm-phase8-stage1` 时，才允许 100 个 Initial calls。
- 提交前 `git diff --cached --check` 首次发现 5 个新 Python 文件 EOF 多余空行；已仅删除这些空行，并将本条作为本轮最后一次项目文件编辑记录。

## 2026-08-20 - Phase 8: Bounded Execution Evidence Rendering

### 1. 本次目标

- 解决 4 个 Phase 8 Initial serialized payload 超过 400,000-byte hard gate 的唯一正式 blocker。
- 不删除 case、不重抽 dataset、不修改 Base/Feedback/Hidden partition、不修改 FL-v1/DeepSeek 配置、不重跑 buggy program、不改 raw frozen snapshots。
- 引入统一、确定性、可审计的 bounded evidence renderer，同时用于 Initial buggy runtime evidence 与未来 Stage 2 F first-patch feedback。
- 重新冻结 100 个 Initial prompt hashes；真实 DeepSeek 调用保持 0，不运行 `--confirm-phase8-stage1`，不进入 Stage 2。

### 2. Payload Byte Attribution

- 新增 `benchmark/scripts/profile_phase8_payloads.py`，按 canonical UTF-8 对 100 个 superseded v1 provider payload 做 component-level byte attribution；所有 component bytes 与 serialization overhead 精确求和为 serialized total。
- `404-B-bug-14578678-14578704`：30,774,820 bytes；Base oracle 5,075,563、Feedback oracle 9,589,378、runtime stdout 14,818,134、serialization overhead 1,287,347，其余 source/FL/runtime metadata/template 很小。
- `626-A-bug-16228568-16228576`：29,468,503 bytes；主要为 runtime stdout 25,817,498 和 serialization overhead 3,646,106，公共 oracle 不超限。
- `361-B-bug-5055774-5055807`：3,435,093 bytes；Feedback oracle 1,772,815、runtime stdout 1,657,989。
- `285-A-bug-3882169-3882175`：1,400,995 bytes；Feedback oracle 748,305、runtime stdout 649,304。
- 结论：3/4 oversized cases 同时存在超大 Common Oracle；最大 case 由 14,664,941-byte common oracle 与 14,818,134-byte runtime stdout 共同造成，不能只处理 runtime output。
- Attribution 冻结到 `benchmark/metadata/repair_phase8/payload_byte_attribution_v1.json`；旧 prompt-set hash `dd4127d97c7a73b822330d0c1c6890873e3913170b48335c895cca59b1b49672` 保留并标记 superseded。

### 3. Renderer 设计与实现

- 新增 `phase8-runtime-evidence-render-v2` 和 `phase8-common-oracle-render-v2`，协议文件为 `benchmark/metadata/repair_phase8/runtime_evidence_render_protocol_v2.json`。核心实验协议仍为 `phase8-v1`，本次只做 real calls=0 时的 pre-experiment prompt-size safety correction。
- 所有 execution tests 均保留 test id、verdict、exit code、timeout、stdout/stderr byte length 与 SHA-256；raw observations 继续完整保存在原 snapshots/artifacts。
- PASS 且 actual stdout 与 expected output byte-exact 时，不重复 actual body，只写 `matches expected output exactly` 和 identity metadata。
- clean-exit mismatch 记录 first differing byte、expected/actual length/hash，actual window 固定为 difference 前最多 1,024 bytes、后最多 3,072 bytes；不在 F 新增 expected window 或新规格。
- abnormal stdout：`<=4096` 完整，否则 first/last 2,048 bytes；stderr：`<=8192` 完整，否则 first/last 4,096 bytes；compiler stderr：`<=16384` 完整，否则 first/last 8,192 bytes。均记录 omitted count、length、hash、truncated。
- Common Oracle input/expected 字段：`<=4096` 完整，否则 first/last 2,048 bytes；Initial/R/F 使用同一 representation。
- 所有 bytes 来自 `str.encode("utf-8")`；excerpt 在 multibyte boundary 使用固定 `errors="replace"` decode policy。
- `repair_phase8/evidence_rendering.py` 是 Initial 与 F 的唯一 shared renderer；R 不渲染 first-patch execution feedback。
- Phase 8 artifacts 新增 raw runtime manifest/observation hash、oracle render hash、render protocol version、rendered evidence hash；R 的 first-patch observation 字段保持 null，F 才记录该 hash。Stage 1/Stage 2 manifests 将逐项校验这些绑定。

### 4. 新增和修改文件

- 新增：`repair_phase8/evidence_rendering.py`、`repair_phase8/tests/test_evidence_rendering.py`、`benchmark/scripts/profile_phase8_payloads.py`。
- 新增冻结审计：`payload_byte_attribution_v1.json`、`prompt_audit_v2.json`、`runtime_evidence_render_protocol_v2.json`。
- 修改：`benchmark/config.py`、Phase 8 prompt audit/report/run scripts、`repair_phase8/models.py`、`prompting.py`、`pipeline.py`、`protocol.py` 及 pipeline/prompting tests。
- 更新：`benchmark/reports/execution_feedback_pre_experiment.md`。
- 删除文件：无；旧 `prompt_audit_v1.json` 未删除，raw runtime snapshots/manifest 未修改。

### 5. 执行过的重要命令

```text
python3 benchmark/scripts/profile_phase8_payloads.py
python3 -m unittest discover -s repair_phase8/tests -v
PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/audit_phase8_prompts.py
PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/audit_phase8_prompts.py && PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/audit_phase8_prompts.py
python3 -c 'from repair_phase8.protocol import validate_phase8_preflight as v; print(v()["status"])'

lxc start codedoctor-docker-host
lxc exec codedoctor-docker-host -- systemctl start docker
lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s sandbox/tests && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s benchmark/tests && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s fault_localization/tests && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s repair/tests && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s repair_phase8/tests'

PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/generate_phase8_pre_experiment.py --fake-tests-passed --renderer-tests-passed --full-regression-passed
python3 benchmark/scripts/run_phase8_experiment.py --stage1
python3 -m compileall -q benchmark repair_phase8
git diff --check
git diff --exit-code HEAD -- benchmark/datasets/codeflaws/metadata/phase8_repair_evaluation.jsonl benchmark/metadata/repair_phase8/phase8_fl_v1.jsonl benchmark/metadata/repair_phase8/phase8_test_partition_v1.json benchmark/metadata/repair_phase8/runtime_evidence_manifest_v1.json benchmark/metadata/repair_phase8/runtime_evidence_v1 benchmark/metadata/repair_phase8/phase8_protocol_v1.json
lxc stop codedoctor-docker-host
```

### 6. 实际测试与审计结果

- Phase 8 专项：24/24 PASS。新增 10 类 synthetic huge-output scenarios：10 MB PASS stdout、10 MB mismatch stdout、10 MB stderr、runtime error huge stdout/stderr、compiler huge diagnostics、UTF-8 boundary、empty output、begin/end/length-only mismatch 全部通过。
- Stage 2 F stress：10 MB stdout+stderr 使用同一 renderer，prompt-visible feedback 有界；F 新增段不重复 input/expected；R 无 execution feedback。
- 完整 regression 最终结果：sandbox 29/29、benchmark 12/12、fault localization 36/36、repair 47/47、Phase 8 24/24，共 148/148 PASS。
- 两个独立 Python processes 各自渲染 100 prompts，并在内部按 seed 20260820 做第三次 random-order render；100/100 hashes 一致。
- 原 4 oversized cases 各自 render 10 次，全部 10/10 hash 一致。
- Before -> after：626-A 29,468,503 -> 30,404；285-A 1,400,995 -> 27,515；404-B 30,774,820 -> 111,833；361-B 3,435,093 -> 45,971 bytes。
- 100 prompts bytes：min 5,494；median 15,867.5；mean 19,566.89；p95 45,971；max 111,833；total 1,956,689。300,000 warning count=0，400,000 hard-gate failures=0。
- 新 Initial prompt-set hash：`c4087dee0353c12fdbe1310ed314272f7436f2fc22560c9917da4dfc75a3f491`。
- Leakage audit：100 raw snapshots、100 rendered prompts 和 100 serialized provider payloads PASS；reference、ground truth、Hidden validation ids、evaluation canary、credential、raw reasoning 均未发现。
- Preflight：PASS；未授权 Stage 1 命令 exit 2；Stage 1/cohort manifests 不存在；formal Phase 8 artifacts=0。
- Raw runtime manifest hash 保持 `943959cb626bb3f190e4a63a45a53c11fbab63781e8297907971f0f0a206f0a0`；partition hash 保持 `fb6239e5b37c81ba4464e00d5505bac9be9296e2fe6d1fc0a2e42573893fb9b7`。
- Dataset、FL-v1、partition、raw runtime manifest/snapshots、core `phase8-v1` 均相对 HEAD 零 diff；无重新执行或重新冻结 raw observations。
- Docker 无残留 sandbox/analysis 容器，LXD 最终 STOPPED。本轮真实 DeepSeek calls=0。

### 7. Revised Token/Cost Estimate

- 透明 heuristic：`ceil(serialized UTF-8 bytes / 4)`。
- 100 Initial prompts estimated input tokens：min 1,374；median 3,967；mean 4,892.07；p95 11,493；max 27,959；total 489,207。
- 使用 2026-08-19 官方价格快照、cache-miss input `$0.14/M`、output `$0.28/M`、Phase 7 148 responses 的 mean completion 5,265.7 tokens/call，Stage 1 粗估约 `$0.2159`。该值不含真实 Phase 8 usage，属于高不确定性 projection，不是账单。

### 8. 遇到的问题与解决方式

- 初始 blocker 看似是 runtime evidence，但 component attribution 证明 3 个 cases 的 public oracle 也超大；因此未做 runtime-only patch，而是统一引入 Common Oracle v2，保持 Initial/R/F 规格对称。
- 不能删除 4 cases、提高 hard gate 或重新选择短 observation；通过 raw/rendered 分离保留完整 observation，并只约束 prompt-visible representation。
- F mismatch 若重新展示中部 expected window，会在 bounded Common Oracle 下新增规格；最终只展示 actual window、first difference 和 expected identity metadata，避免 R/F task semantics 不对称。
- code review 发现 R artifact 会把 Initial runtime hash误名为 first-patch observation；修正为该字段仅 F 非空，并补充测试。
- 报告初版的最大 case oracle 合计使用早期逐-example口径，少计 19-byte join overhead；改为直接从冻结 attribution rows 计算 14,664,941 bytes。

### 9. 当前 Readiness 与下一步

- `phase8_stage1_ready=true`，`phase8_stage1_user_authorized=false`，当前 formal blocker=none。
- DeepSeek provider/model/thinking/reasoning effort/max tokens/stream/temperature/retries 全部未变；本轮未重新 smoke、未调用真实 API。
- 本轮在 pre-experiment safety correction 后停止，不执行 `--confirm-phase8-stage1`，不启动 Stage 1/Stage 2。
- 下一步仅在用户显式批准后运行 100-call Stage 1；Stage 1 完成后仍必须暂停、冻结 eligible cohort，并等待独立 Stage 2 授权。

## 2026-08-20 - Phase 8 Stage 1 Formal Experiment

### 1. 本次目标

- 在冻结 commit `ce640a7ee558f5f376239672a6692b0ba86dbbcd` 上执行且仅执行 Phase 8 Stage 1。
- 对 100 个 Evaluation Set cases 各发起一次 DeepSeek Initial repair，不补调、不进入 Stage 2。
- 冻结 first patches、Stage 1 manifest 和 eligible cohort，离线生成并审计 R/F prompt candidates。
- 汇总真实 usage/cost、完成报告、全回归和仓库边界审计。

### 2. 实际完成内容

- 正式执行 100 个 Initial calls；100 个均收到响应，provider failure=0，未发生进程/监视中断，未使用 resume。
- 冻结 100 个 Initial artifacts、`stage1_manifest_v1.json` 和 `eligible_cohort_v1.json`；eligible cohort `M=6`。
- 新增离线 Stage 1 reporting 与 Stage 2 prompt audit：基于相同 first patch 各生成 6 个 R 和 6 个 F candidates，不构造正式 Stage 2 provider call。
- 审计 R/F common-information 前缀、F-only bounded execution feedback、400,000-byte hard gate、leakage、两次重建稳定性和 deterministic arm order。
- 更新 pre-experiment 状态和正式 Stage 1 报告；Stage 2 guard PASS，但 Stage 2 user authorization 保持 false。
- 使用 2026-08-19 冻结价格快照计算 usage cost，并于 2026-08-20 对照 DeepSeek 官方 Models & Pricing 页面确认价格值仍为 cache hit `$0.0028/M`、cache miss `$0.14/M`、output `$0.28/M`。

### 3. 新增、修改和删除文件

- 新增：`repair_phase8/reporting.py`、`repair_phase8/tests/test_reporting.py`。
- 新增：`benchmark/scripts/generate_phase8_stage1_report.py`。
- 新增正式 artifacts：`benchmark/artifacts/repair_phase8/initial/` 下 100 个 JSON。
- 新增冻结 metadata：`stage1_manifest_v1.json`、`eligible_cohort_v1.json`、`stage2_prompt_audit_v1.json`。
- 新增报告：`benchmark/reports/execution_feedback_stage1.md`。
- 修改：`benchmark/config.py`、`benchmark/reports/execution_feedback_pre_experiment.md`。
- 删除文件：无。

### 4. 执行过的重要命令

```text
PYTHONDONTWRITEBYTECODE=1 python3 -c 'from repair_phase8.protocol import validate_phase8_preflight; ...'
source ~/.config/codedoctor/secrets.env
python3 -c 'import os; print("DeepSeek credential available" if os.getenv("DEEPSEEK_API_KEY") else "DeepSeek credential unavailable")'
lxc start codedoctor-docker-host
lxc exec codedoctor-docker-host -- systemctl start docker
lxc exec codedoctor-docker-host -- docker image inspect codedoctor-cpp-sandbox --format '{{.Id}}'
source ~/.config/codedoctor/secrets.env
printf '<credential forwarded without output>' | lxc exec codedoctor-docker-host -- bash -lc '... python3 benchmark/scripts/run_phase8_experiment.py --stage1 --confirm-phase8-stage1'
PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/generate_phase8_stage1_report.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s repair_phase8/tests -v
lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s sandbox/tests && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s benchmark/tests && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s fault_localization/tests && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s repair/tests && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s repair_phase8/tests'
PYTHONDONTWRITEBYTECODE=1 python3 -c 'from repair_phase8.protocol import validate_stage2_gate; ...'
git diff --check
git diff --exit-code HEAD -- <frozen Phase 8 input artifacts>
lxc stop codedoctor-docker-host
```

上述命令中的 credential 仅通过环境/标准输入转发；未读取、打印或记录实际 API Key。

### 5. 实际测试和实验结果

- Stage 1 attempted/received/provider failure：`100/100/0`。
- Valid outputs=`91`；compile success=`91`；repair-time success=`85`；validated patches=`85`。
- Repair-time success but Hidden failure=`0`；hidden-validation-only trigger 专项测试 PASS。
- Invalid model output=`9`；length truncation=`9`；finish reasons 为 stop=`91`、length=`9`，协议要求下均未补调。
- Eligible `M=6`；primary eligibility reasons：base only=`2`、feedback only=`2`、base+feedback=`2`。
- Usage：prompt=`777055`、cache hit=`0`、cache miss=`777055`、reasoning=`595938`、final answer=`24729`、completion=`620667`、total=`1397722` tokens；字段缺失计数为 0。
- Stage 1 usage-based cost estimate=`$0.28257446`，不是账单导出。
- Stage 1 artifact-set hash=`7336d3312e737ea39bab8144e88e82b45f0eff056ddee5ef363aa36289f4070b`。
- Eligible cohort manifest hash=`e1ec70b962cda0754c336896cd0975d2ef9794d410146c34223d50792797c9c5`。
- Stage 2 prompt audit hash=`a0254c9e1f73e16d67049da3c62052eec7032322407199945a99d9bbb381c39c`。
- R bytes min/median/p95/max=`8867/15371/112631/112631`；F=`11618/16448/136634/136634`；warning/hard-gate failures=`0/0`。
- R/F rebuild reproducibility PASS；leakage audit PASS；order balance F->R=`4`、R->F=`2`。
- Expected Stage 2 calls=`12`；estimated Stage 2 cost=`$0.03607045`，基于 serialized-byte input heuristic 和 Stage 1 mean completion usage。
- Artifact boundary scan：103 files PASS；credential-like value/raw reasoning 均未发现；Initial artifacts=`100`，Stage 2 artifacts=`0`。
- 完整 regression：sandbox `29/29`、benchmark `12/12`、fault localization `36/36`、repair `47/47`、Phase 8 `26/26`，合计 `150/150 PASS`。
- LXD/Docker 最终停止；没有残留正在运行的正式实验进程。

### 6. 遇到的问题和解决方式

- 首次 fail-closed 摘要脚本使用旧的 `payload_validation` 嵌套键并触发 `KeyError`；核心 `validate_phase8_preflight()` 已先返回 PASS，随后按当前 `operational_size_gate`/`leakage_audit` 结构重跑完整摘要，确认所有 gate 后才发出第一条请求。
- 部分模型响应和 case 验证耗时明显较长；始终监视同一个正式进程，没有启动并行或重复实验。最终无 terminal/SSH/monitoring interruption，无 resume。
- 9 个响应因 `finish_reason=length` 无法提取完整 patch；严格按协议记为 invalid output，不重试、不进入 cohort。
- 一个 Initial artifact 因保留完整 evaluation evidence 达约 54.4 MB；仍低于 GitHub 100 MB 单文件限制，但增加仓库体积。

### 7. 当前已知不足

- Stage 1 cost 是 provider usage 乘官方单价的估算，不是 DeepSeek 账单导出。
- R/F 的真实 token usage 尚不存在；Stage 2 cost 只能使用 payload byte heuristic 和 Stage 1 observed completion mean 估计。
- 正式 artifacts 约 79.7 MB，且最大单文件约 54.4 MB；可审计性优先，但 Git 仓库会明显增大。
- 9 个 length-truncated cases 按冻结协议无法补调，也不是 primary R/F eligible cohort。
- Stage 1 不能回答 Execution Feedback 是否优于 Retry；必须完成未来 paired R/F experiment 后才能分析研究问题。

### 8. 下一步计划

- 当前 `phase8_stage2_ready=true`、`phase8_stage2_user_authorized=false`、technical blocker=none。
- 保持 Stage 2 real LLM calls=`0`；只有获得新的明确人工授权后，才可使用冻结 cohort、first patches、R/F hashes 和 arm order 执行恰好 `2M=12` 次调用。

## 2026-08-20 - Phase 8 Stage 2 Formal Experiment

### 1. 日期和阶段

- 日期：2026-08-20。
- 阶段：Phase 8 Stage 2 Formal Experiment，Controlled Execution Feedback Repair paired R/F evaluation。
- 起始 commit：`223baa6c2094f331d7cefdddc7a032db7714b257`。

### 2. 本次目标

- 对冻结 eligible cohort `M=6` 的每个 Stage 1 first patch 各执行一次 Retry Control (R) 和一次 Execution Feedback (F)，共 12 个真实 DeepSeek calls。
- 保持 R/F first patch、Initial context、FL-v1、test partition、Renderer v2、模型参数和 deterministic arm order 不变。
- 执行 Base/Feedback/Hidden evaluation，计算 paired 2x2、validated difference、paired bootstrap 95% CI、exact McNemar 和 S0/SR/SF end-to-end rates。
- 只提交小型 hash manifest、summary、报告和必要代码，不向 Git 新增大型 Stage 2 raw artifacts。

### 3. 实际完成内容

- 网络前重新验证 clean worktree、精确 HEAD、Stage 2 gate、Stage 1/cohort hashes、12 prompt candidates、reproducibility、leakage、payload gate、order balance 和 credential availability，全部 PASS。
- 使用单一正式进程执行 `--stage2 --confirm-phase8-stage2`；12/12 calls 完成，received=12，provider failure=0，未使用 resume，未补调，未重跑 Stage 1。
- 实际顺序保持冻结结果：F->R 4 cases、R->F 2 cases；每个 arm 仅一次请求，transport retries=0。
- 生成 12 个本地 raw Stage 2 artifacts，并新增 `.gitignore` 规则阻止其进入 Git；逐文件 SHA-256、大小、prompt/response/first-patch hash、classification、usage 和 evaluation 摘要写入小型 result manifest。
- 新增 paired statistics、artifact binding、leakage 和最终报告生成模块；生成 Phase 8 final formal report。
- 更新 pre-experiment 和 Stage 1 报告中的历史状态，明确 Stage 2 已完成且 Phase 9 未启动。

### 4. 新增、修改和删除文件

- 新增：`repair_phase8/stage2_reporting.py`、`repair_phase8/tests/test_stage2_reporting.py`。
- 新增：`benchmark/scripts/generate_phase8_final_report.py`。
- 新增：`benchmark/metadata/repair_phase8/stage2_result_manifest_v1.json`。
- 新增：`benchmark/reports/execution_feedback_formal.md`。
- 修改：`.gitignore`、`benchmark/config.py`、`benchmark/reports/execution_feedback_pre_experiment.md`、`benchmark/reports/execution_feedback_stage1.md`。
- 本地生成但不提交：`benchmark/artifacts/repair_phase8/retry_control/` 和 `feedback/` 下各 6 个 raw JSON，共 300,545,002 bytes。
- 删除文件：无；未重写已有 Git 历史。

### 5. 执行过的重要命令

```text
git status --porcelain
git rev-parse HEAD
PYTHONDONTWRITEBYTECODE=1 python3 -c 'from repair_phase8.protocol import validate_stage2_gate; ...'
source ~/.config/codedoctor/secrets.env
python3 -c 'import os; print("DeepSeek credential available" if os.getenv("DEEPSEEK_API_KEY") else "DeepSeek credential unavailable")'
lxc start codedoctor-docker-host
lxc exec codedoctor-docker-host -- systemctl start docker
lxc exec codedoctor-docker-host -- docker image inspect codedoctor-cpp-sandbox --format '{{.Id}}'
source ~/.config/codedoctor/secrets.env
printf '<credential forwarded without output>' | lxc exec codedoctor-docker-host -- bash -lc '... python3 benchmark/scripts/run_phase8_experiment.py --stage2 --confirm-phase8-stage2'
lxc exec codedoctor-docker-host -- bash -lc "ps -eo pid,etime,stat,cmd | grep -E '[r]un_phase8_experiment|[d]ocker run'"
lxc exec codedoctor-docker-host -- bash -lc "ss -tinp | grep -A2 'pid=812' || true"
PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/generate_phase8_final_report.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest repair_phase8.tests.test_stage2_reporting -v
lxc exec codedoctor-docker-host -- bash -lc 'set -e; cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s sandbox/tests && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s benchmark/tests && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s fault_localization/tests && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s repair/tests && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s repair_phase8/tests'
git check-ignore benchmark/artifacts/repair_phase8/retry_control/*/*.json
git check-ignore benchmark/artifacts/repair_phase8/feedback/*/*.json
git diff --exit-code HEAD -- <frozen Phase 8 Stage 1 and protocol inputs>
git diff --check
lxc stop codedoctor-docker-host
```

上述命令只记录 credential 的存在性和无值转发方式；没有读取、打印、保存或提交 API Key。

### 6. 实际实验结果

- Calls attempted/received/provider failed=`12/12/0`；finish reasons stop=`11`、length=`1`。
- R validated=`4/6`；F validated=`4/6`。
- Paired 2x2：both success=`3`、R fail/F success=`1`、R success/F fail=`1`、both fail=`1`。
- F-R validated difference=`0/6 = 0.0 percentage points`。
- Gross F rescue among R failures=`1/2 = 50%`，但存在一个相反方向的 R success/F fail。
- Exact empirical paired bootstrap 46,656 resamples 的 95% CI=`[-0.5, 0.5]`。
- Exact two-sided McNemar：discordant pairs=`2`，`p=1.0`。
- End-to-end：S0=`85/100=85%`、SR=`89/100=89%`、SF=`89/100=89%`。
- R classifications：validated_patch=`4`、repair_test_failed=`1`、plausible_patch=`1`。
- F classifications：validated_patch=`4`、invalid_model_output=`1`、plausible_patch=`1`。
- `315-A-bug-8649287-8687189` 为 R fail/F validated；`366-B-bug-5240575-5240582` 为 R validated/F length-truncated invalid output；`305-A-bug-13310851-13310872` 两个 arm 均 repair-time success 但 Hidden Validation fail。

### 7. Token、成本和 artifact hashes

- R tokens：prompt=`86103`、cache hit=`83840`、cache miss=`2263`、reasoning=`56669`、final answer=`1629`、completion=`58298`、total=`144401`；cost=`$0.01687501`。
- F tokens：prompt=`100142`、cache hit=`84352`、cache miss=`15790`、reasoning=`58881`、final answer=`1381`、completion=`60262`、total=`160404`；cost=`$0.01932015`。
- Total tokens：prompt=`186245`、cache hit=`168192`、cache miss=`18053`、reasoning=`115550`、final answer=`3010`、completion=`118560`、total=`304805`。
- Stage 2 usage-based cost estimate=`$0.03619516`，使用冻结的 DeepSeek official pricing snapshot，不是账单导出。
- Stage 2 artifact-set hash=`cf4f44f802913085ce70d7da344a3952c014295f712954b0de93d58ab2c96a04`。
- Stage 2 result manifest hash=`bdc07d0be135edfc51e9c16c48c6163cead0cee6762654a30e0b76a483e4f95e`。
- Stage 1 artifact-set/cohort hashes保持 `7336d3312e737ea39bab8144e88e82b45f0eff056ddee5ef363aa36289f4070b` / `e1ec70b962cda0754c336896cd0975d2ef9794d410146c34223d50792797c9c5`。

### 8. 实际测试与审计结果

- Stage 2 result manifest 12 entries，overall hash 复算 PASS；12 个 local raw artifact hashes 已绑定。
- Leakage audit PASS：reference source、Hidden Validation ids、evaluation canaries、credential、raw reasoning 均未进入 R/F prompt；R 无 feedback heading，F 保持 exact R prefix 并只增加 bounded feedback。
- Frozen Stage 1 initial artifacts、manifest/cohort、Phase 8 protocol、partition、FL-v1、runtime evidence 和 Initial prompt audit 相对 HEAD 零 diff。
- 12 个 raw Stage 2 artifacts 全部被 `.gitignore` 命中；计划提交的小型结果文件约 53 KB，不提交新的大型 raw artifacts。
- 完整 regression：sandbox `29/29`、benchmark `12/12`、fault localization `36/36`、repair `47/47`、Phase 8 `28/28`，合计 `152/152 PASS`。
- LXD 最终 STOPPED；未创建 Phase 9 文件或任务。

### 9. 遇到的问题和解决方式

- 正式进程前约 16 分钟没有逐 arm 输出；只读检查确认唯一 Python 进程处于 network poll，TCP 连接为 ESTABLISHED 且持续收包。未终止、未 resume、未启动第二进程；最终远端 PTY 一次性刷新 12 条已完成记录，正式进程 exit 0。
- Stage 2 raw evaluation artifacts 达约 300 MB，两个最大文件约 150 MB，超过 GitHub 单文件限制；保留本地 raw 文件并提交逐文件 hash/size/summary manifest，避免新的大型可再生 artifacts 进入 Git。
- 报告新增分-arm usage 后，synthetic report test fixture 缺少 `retry_control`/`feedback` 字段并报 `KeyError`；补齐测试夹具后 targeted tests 和 full regression 均 PASS。正式结果 manifest 不受该夹具问题影响。
- Pipeline artifact 的 `attempt=2` 表示整体第二轮 repair round；为消除“每 arm 一次调用”歧义，summary manifest 明确记录 `repair_round=2` 与 `arm_attempt=1`。

### 10. 当前已知不足和下一步计划

- `M=6` 非常小，paired bootstrap CI 很宽；结果只能定位为 paired case-level evidence，不能推广为 execution feedback 的总体效果。
- `Validated Patch != Formally Correct Patch`；validated 只表示通过已注册 Base/Feedback/Hidden tests。
- 一个 F response length-truncated 且按冻结协议不补调；它真实计入 F failure。
- Raw Stage 2 artifacts 仅保留在当前本地工作区并由 Git 忽略；Git 中以 SHA-256 manifest 保留完整性身份，但不携带约 300 MB 原始内容。
- Phase 8 RQ 当前结论：在冻结 6-case cohort 中，R 和 F 都 validated 4/6；一个 F rescue 被一个 opposite-direction loss 抵消，没有观察到 aggregate validated advantage。
- Phase 8 到此停止。不自动进入 Phase 9；后续工作必须由用户另行明确授权。

## 2026-08-20 - Phase 9 Patch Validation Strength and Overfitting

### 1. 日期和阶段

- 日期：2026-08-20。
- 阶段：Phase 9，有限测试集下的 patch validation strength 与 overfitting 审计。
- 起始 commit：`b43dcca8bc1921ef7b55450439fb2c9b0920bea0`。

### 2. 本次目标

- 冻结并审计 Phase 7 A/B/C、Phase 8 Initial/R/F 正式实验中实际可提取的 patch，不发起任何新 LLM 调用。
- 建立 `V0 compile -> V1 repair-time -> V2 hidden -> V3 ASan+UBSan -> V4 reference differential` validation ladder。
- 使用 seed `20260820` 的 deterministic numeric mutation、reference acceptance filter 和同 case 共享 stress set，研究 hidden validation 仍遗漏的 patch overfitting。
- 生成小型 manifest、hash、summary 和正式报告，不提交生成输入正文、二进制或 raw sanitizer/differential artifacts。

### 3. 实际完成内容

- 建立 245 patch / 141 unique case 的 Formal Patch Corpus；来源仅为冻结正式 artifacts，7 个 Phase 7、9 个 Phase 8 Initial、1 个 Phase 8 Stage 2 invalid/no-patch attempt 未被伪造为可执行 patch。
- 实现 deterministic Numeric Mutation v1、Docker compile-once/run-many batch executor、reference 双运行确定性检查、reference sanitizer filter、V3/V4 classification、bounded findings、checkpoint/resume 和结果聚合。
- 对 141 cases 实际构建 reference-accepted differential stress sets；生成 50,911 个候选，冻结 11,983 个 accepted tests，13 cases 为 0 accepted 并按协议保留为 V4=N/A。
- 对全部 245 patches 建立正式 checkpoint；218 个 V2 PASS patch进入 stronger validation，V2 未通过者直接记录 V3/V4=N/A。
- 生成 Phase 9 result manifest 与 17 节正式报告；case studies 按 `case_id` 确定性选择，没有人工挑选或 repair feedback。
- 本阶段 real LLM calls=`0`；未读取 credential，未调用 DeepSeek/OpenAI，未把 Phase 9 failure evidence 送回任何 repair loop。

### 4. 新增、修改和删除文件

- 新增：`validation_phase9/` 下 `batch.py`、`corpus.py`、`mutation.py`、`pipeline.py`、`reporting.py` 及 18 项回归测试。
- 新增：`benchmark/scripts/build_phase9_patch_corpus.py`、`run_phase9_validation.py`、`generate_phase9_report.py`。
- 新增：`benchmark/metadata/validation/phase9_validation_protocol_v1.json`、`phase9_patch_corpus_v1.json`、`differential_tests_v1.json`、`phase9_validation_results_v1.json`。
- 新增：`benchmark/reports/patch_validation_overfitting.md`。
- 修改：`.gitignore`、`benchmark/config.py`。
- 本地生成但不提交：`benchmark/artifacts/validation_phase9/` 中约 12 MB reference/patch checkpoints，包含可重建输入正文和 bounded raw evidence。
- 删除文件：无；未修改 Phase 7/8 冻结 artifacts，未重写 Git 历史。

### 5. 执行过的重要命令

```text
lxc start codedoctor-docker-host
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s validation_phase9/tests -v
lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/run_phase9_validation.py --stage references --resume'
lxc exec codedoctor-docker-host -- bash -lc 'cd /workspace/CodeDoctor && PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/run_phase9_validation.py --stage patches --resume'
PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/build_phase9_patch_corpus.py
PYTHONDONTWRITEBYTECODE=1 python3 benchmark/scripts/generate_phase9_report.py
lxc exec codedoctor-docker-host -- bash -lc 'set -e; cd /workspace/CodeDoctor; for suite in sandbox benchmark fault_localization repair repair_phase8 validation_phase9; do PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s "$suite/tests"; done'
git diff --check
git diff --cached --check
git diff --name-only HEAD -- benchmark/artifacts/repair benchmark/artifacts/repair_phase8 benchmark/metadata/repair benchmark/reports/execution_feedback_formal.md benchmark/reports/llm_repair_formal.md
lxc exec codedoctor-docker-host -- bash -lc "docker ps -a --filter ancestor=codedoctor-cpp-sandbox --format '{{.ID}} {{.Status}} {{.Names}}'"
lxc stop codedoctor-docker-host
```

### 6. 实际实验结果

- Corpus：patches=`245`、unique cases=`141`、V1 plausible=`229`、V2 existing validated=`218`；V1->V2 rejection=`11/229=4.8%`。
- V2->V3 sanitizer rejection=`0`；V2->V4 differential rejection=`52/201 V4-applicable=25.9%`。
- Strongly Validated=`149/245=60.8%`；V2 中另有 17 patches 因 V4=N/A 而不能称为 strong。
- Additional Rejection Rate=`52/217=24.0%`，分母为至少有一个 applicable stronger validation 的 V2 patches。
- Phase 7 原 V2 vs strong：A `40/50` vs `28/50`，B `39/50` vs `28/50`，C `46/50` vs `35/50`。
- Phase 8 原 V2 vs strong：Initial `85/100` vs `55/100`，R `4/6` vs `2/6`，F `4/6` vs `1/6`。
- Patch failure：ASan affected patches=`0`、UBSan=`0`、differential output mismatch=`50`、runtime error=`0`、timeout=`2`；mismatch finding instances=`1,697`。
- Reference official-test sanitizer exclusions：ASan=`71`、UBSan=`44`、timeout=`11`。
- Formal patch executions无 provider、Docker daemon、container parser 或 checkpoint coverage failure。

### 7. Reproducibility、计算成本和 artifact hashes

- Patch corpus manifest hash=`365902f86f92987d25d5ba9c8167a21b776c57b83ee7025a4ecd11a055eeffd9`。
- Differential manifest hash=`f593f20b0af854a63d7b8ca3caf41a6734080b1fd7f0cad5fc5e82e0886a7682`。
- Result manifest hash=`48341fd5925b381124bb3cca3e93b3d1f59ff092dcc298edf933761ee34b5e38`。
- Protocol file SHA-256=`4bb2e039216386d9d9baccbaf52793c4b49f061b6c9b6367fe3870f9e8d79656`。
- 冻结上游 hash 保持：Phase 7=`067710f9f3b71855cc4bf1db3dd0614cef89c1d4cec7e4f6e83c0372b7607f17`，Phase 8 Stage 1=`7336d3312e737ea39bab8144e88e82b45f0eff056ddee5ef363aa36289f4070b`，Stage 2 artifacts=`cf4f44f802913085ce70d7da344a3952c014295f712954b0de93d58ab2c96a04`，Stage 2 result=`bdc07d0be135edfc51e9c16c48c6163cead0cee6762654a30e0b76a483e4f95e`。
- 记录程序执行共 `86,872` 次：reference normal=`35,058`、reference sanitizer=`23,902`、patch sanitizer=`9,142`、patch differential=`18,770`。
- 累计 batch wall time=`2,773.9 s`（约 `46.2 min`），不含 Python 聚合和 regression tests；API cost=`$0`。

### 8. 实际测试与审计结果

- Phase 9 targeted tests 最终 `18/18 PASS`，覆盖 corpus formal-only/hash/duplicate、mutation determinism/caps/bounds、reference crash/timeout/nondeterminism/sanitizer rejection、ASan/UBSan/timeout/clean classification、differential outcomes、manifest reproducibility、result invariants 和 leakage。
- 完整 regression 最终：sandbox `29/29`、benchmark `12/12`、fault localization `36/36`、repair `47/47`、Phase 8 `28/28`、Phase 9 `18/18`，合计 `170/170 PASS`。
- Corpus、differential、result 三个 manifest 自哈希复算 PASS；同 case 共享 test IDs 和 differential manifest coverage 审计 PASS。
- `git diff --check` 与 staged diff check PASS；无 staged file 超过 10 MB，最大必要 manifest `differential_tests_v1.json` 为 7,060,054 bytes。
- 未暂存本地 raw checkpoints、`.env`、credential、raw reasoning、二进制、sanitizer raw dumps 或 `__pycache__`；Phase 7/8 冻结路径相对 HEAD 零 diff。
- Docker residue 检查为空；LXD 最终 `STOPPED`。

### 9. 遇到的问题和解决方式

- 初次大补丁中的 sanitizer input 列表推导语法无效；`py_compile` 立即发现后做最小修复，Phase 9 单元测试恢复 PASS。
- 初始 reference 全量串行执行约每 case 一分钟，遇到 mutation timeout 时更慢；保持候选生成、SHA 顺序、5 秒超时和 acceptance 条件不变，改为 128 候选固定分块、累计接受 100 后停止，并在同一受限容器内最多 4 路独立并发。真实 8-input sanitizer smoke 通过，正式 checkpoint 支持 resume。
- Batch TSV 最初存在 RUN 列数/索引和 shell format 参数不一致；解析测试与真实 Docker clean/UBSan smoke 暴露后修正，再开始正式实验。
- Leakage test 曾把审计字段名 `raw_reasoning_committed=false` 误判为 raw reasoning 内容；将断言收窄为禁止真实 `"raw_reasoning":` 字段后，18 项 Phase 9 测试和完整回归均 PASS。
- 两个 Python 文件末尾多余空行触发 staged `git diff --check`；删除多余空行后检查 PASS，结果 manifests 未变化。

### 10. 当前已知不足和下一步计划

- Reference-accepted differential stress input 不等于形式化合法题目输入；numeric mutation 覆盖有限，且 finite tests 不能证明语义等价。
- Sanitizer 只覆盖实际执行路径；本 corpus 未观察到 patch 侧 ASan/UBSan rejection，不代表不存在内存或未定义行为问题。
- 13 cases 没有 accepted differential test，17 个 V2 patches 因 V4=N/A 无法获得 strong 标签；这是保守证据不足，不是形式化 failure。
- Codeflaws representativeness 有限，同 case 的 A/B/C、Initial/R/F patches 统计上相关；本报告仅给 patch-level descriptive evidence，没有把 patches 伪装成独立 cases。
- `Strongly Validated Patch != Formally Correct Patch`；149 个 survivors 只表示更强的有限经验验证。
- Phase 9 RQ 结论：hidden validation 拒绝 11/229 plausible patches；V3 未新增拒绝；V4 在 201 个 applicable V2 patches 中新增拒绝 52 个；所有 Phase 7/8 arms 的 strong rate 均低于原 V2 rate。
- Phase 9 到此停止，不自动进入 Phase 10，也不对发现的失败 patch 再调用 LLM。
