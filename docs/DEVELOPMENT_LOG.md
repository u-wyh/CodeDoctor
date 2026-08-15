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
