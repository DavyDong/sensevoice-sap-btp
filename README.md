# SenseVoice on SAP BTP

将 **FunASR + SenseVoiceSmall + FSMN-VAD + FastAPI** 部署到笔记本或 **SAP BTP Cloud Foundry**，提供中文、英文、中英混说语音识别、文件 API 和浏览器麦克风分段识别。

**已完成 Windows 本地运行和 SAP BTP Cloud Foundry 真实部署验证。** 云端验证包含实际模型推理、XSUAA OAuth2、可选固定 `ACCESS_TOKEN`、HTTP 文件识别和 WSS 音频回放。现在将集成代码、部署模板和测试公开，方便大家部署到自己的环境并参与改进。

This community project runs SenseVoiceSmall on CPU, locally or on SAP BTP Cloud Foundry, with a FastAPI service, browser UI, XSUAA authentication and segmented WebSocket transcription. See the [English quick start](docs/QUICKSTART.en.md).

这不是 SAP、FunAudioLLM 或 FunASR 官方产品。本项目提供服务与部署集成；语音模型和推理框架来自上游，详见[第三方说明](THIRD_PARTY_NOTICES.md)。仓库不提供共享的公共识别服务、模型权重或任何真实账号凭据。

## 能做什么

| 功能 | 实现与边界 |
| --- | --- |
| 语言 | `auto` / `zh` / `en`；中英混说使用 `auto` |
| 文件识别 | WAV、FLAC、OGG、MP3；8–48 kHz 单/双声道；最长 120 秒；整个请求最多 20 MiB |
| 麦克风 | 浏览器 AudioWorklet → 16 kHz PCM16 → WSS → FSMN-VAD → SenseVoiceSmall |
| 分段结果 | 约 600 ms 停顿或连续讲话约 10 秒后触发，再加推理和网络时间；不是逐 token 原生流式识别 |
| HTTP API | `POST /v1/audio/transcriptions`；另提供原始音频接口 `/v1/transcribe` |
| 云端鉴权 | XSUAA OAuth2 Bearer token；可额外配置固定 `ACCESS_TOKEN`，两者并存 |
| 并发 | 每实例一个识别请求或麦克风会话；忙时返回 429；麦克风会话最长 10 分钟 |
| 音频处理 | 模型在部署环境执行，应用不持久保存录音，不主动记录 token 或转写文本 |

麦克风需浏览器授权，以及 HTTPS 或 localhost 安全上下文。时间戳是 VAD/切段边界，不是逐词对齐。自然混说、口音、业务词和数字的准确率需用自己的音频验收。

文件上传由 FastAPI/Starlette 解析；较大的 multipart 文件可能使用临时磁盘文件，请按所在平台策略管理临时存储。云端识别会将音频发送到你部署的服务。

## 快速开始：本地运行

需要 Git、[uv](https://docs.astral.sh/uv/getting-started/installation/) 和下载依赖/模型的网络。安装脚本建立独立 Python 3.11 环境，使用 CPU，不要求 CUDA。模型文件约 0.94 GB；还需为 PyTorch、环境和下载缓存预留磁盘空间。实测 Windows 进程峰值约 3.12 GiB，运行前应有足够可用内存，建议从 8 GB 以上总内存的机器开始验收。

```bash
git clone https://github.com/DavyDong/sensevoice-sap-btp.git
cd sensevoice-sap-btp
```

Windows PowerShell：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start.ps1
```

macOS / Linux：

```bash
bash scripts/setup.sh
bash scripts/start.sh
```

打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)，本地令牌留空。上传音频或点击“开始录音”；用 Ctrl+C 停止服务。本地 API 文档在 `/docs`。匿名模式仅允许 loopback，不能用于 CF 公网部署。

Windows 已实测；Linux 依赖已在 BTP buildpack 部署验证。macOS 安装脚本已提供，尚未在 Mac 设备验证；Apple Silicon 使用平台对应的 PyTorch wheel，不使用 Linux 的 `+cpu` 锁文件。

## 部署到 SAP BTP

推荐使用已实测的 **Python buildpack** 路径。完整步骤见 **[SAP BTP 部署指南](docs/DEPLOYMENT.md)**，包括 XSUAA、路由、模型打包、变量配置、资源与故障排查。

1. 本地安装、下载模型并验证文件/接口。
2. 登录自己的 CF org/space，确认 Python buildpack、cflinuxfs5、XSUAA application 计划与配额。
3. 从 `deployment.vars.example.yml` 和 `xs-security.json` 创建自己的本地配置，设置唯一 route 和 xsappname。
4. 创建 XSUAA 服务，打包并 `cf push`；默认 1 实例、6G 内存、6G disk、2 个 PyTorch 线程。
5. 获取 XSUAA token，或在 Cockpit 配置大写 `ACCESS_TOKEN` 后重启；运行 HTTP/WSS 验收。

staging 可下载锁定的官方模型，校验后封装进 droplet；也可上传已预下载的完整模型包。运行时仅加载本地模型，不下载权重。程序监听平台注入的 `PORT`，HTTP 和 WSS 共用一个端口，并保持一个 Uvicorn worker，避免重复加载模型。

[Dockerfile](Dockerfile) 和 [Docker manifest](manifest.yml) 作为另一部署选项提供，**镜像尚未构建验收**。已验证的 BTP 部署采用 buildpack。

## Token 与 API

详细可复制示例见 **[TOKEN-API.md](TOKEN-API.md)**，包括令牌获取、HTTP、WebSocket、Postman 和 ABAP。

本地文件识别：

```powershell
curl.exe -F "file=@sample.wav" -F "language=auto" http://127.0.0.1:8000/v1/audio/transcriptions
```

云端使用相同 API，增加 `Authorization: Bearer <token>`；网页输入框只填 token 本身，不加 `Bearer `。仅路径与常见音频 API 相似，本项目没有实现其他平台完整的参数集或 SDK 兼容协议。

| 认证方式 | 获取与使用 |
| --- | --- |
| XSUAA | 从绑定获取客户端凭据，使用 `client_credentials` 获取短期 token；本模板有效期约 15 分钟 |
| 固定 `ACCESS_TOKEN` | 管理员在 BTP User-Provided Variables 配置，32–256 位合法 Bearer ASCII 字符；修改后 Restart 生效；为空时关闭 |

固定令牌没有自动过期时间，持有者拥有识别权限，不附带用户身份或 XSUAA scope。`AUTH_MODE` 仍为 `xsuaa`，绑定仍必需。公网 route 加固定 token 不会变成内网服务；如需只允许内部网络，须另外配置网络访问边界。真实 token 不写入 Git、manifest 或导出的 Postman 环境。

## 模型、版本与离线运行

`models.lock.json` 固定官方仓库 revision；下载器仅获取所列权重、配置、词表、模型说明和官方样例，不下载或执行远程 Python。大文件核对上游 LFS SHA256，小文件核对 Git blob SHA1，生成 `models/checksums.json` 后可再次验证：

```powershell
.\.venv\Scripts\python.exe scripts/download_models.py --verify
```

Hugging Face 权重下载慢时，可先运行 `scripts/download_modelscope_weight.py`，再运行 `scripts/download_models.py`。前者使用同一维护方的 ModelScope 权重源，必须与锁定版本 SHA256 一致；其余文件仍需访问 Hugging Face。不要同时运行两个权重下载器。

| 组件 | 已验证版本 |
| --- | --- |
| Python | 本地 3.11.15 / BTP buildpack 3.11.16 |
| FunASR | 1.4.16 |
| torch / torchaudio | 2.11.0+cpu（Windows / Linux） |
| FastAPI / Uvicorn | 0.143.1 / 0.54.0 |
| sap-xssec | 4.5.0 |
| NumPy / SciPy | 2.2.6 / 1.16.3 |

完整版本见 `requirements-windows.lock` / `requirements-linux.lock`。这些是测试过的版本快照；升级 Python、buildpack、模型或依赖后应重新验收。

## 测试与已验证结果

```powershell
.\.venv\Scripts\python.exe -m pytest -q
node tests/test_worklet.cjs
node tests/test_transport.cjs
# 需要已启动的本地服务及已下载模型：
.\.venv\Scripts\python.exe scripts/smoke_test.py
```

macOS/Linux 将 Python 路径替换为 `.venv/bin/python`。Node.js 仅用于浏览器音频算法测试，运行服务不依赖 Node。

[验证记录](docs/VALIDATION.md) 区分模拟接口测试与真实推理。2026-10-15 已在 Windows 和 BTP 完成中文、英文、拼接混合音频、静音、HTTP/WSS、鉴权和长度限制验证；120 秒云端音频样例推理约 12.113 秒。这是单次测量，不是准确率或吞吐量保证。

以下仍需部署者验收：真人麦克风硬件与权限、自然中英混说、业务准确率、macOS、Docker 镜像，以及 ABAP 示例在目标系统的激活和调用。欢迎用不含个人信息的复现步骤帮助改进。

## 项目结构

```text
app/                    FastAPI、鉴权、音频处理、分段与网页
scripts/                安装、模型下载/校验、CF 打包、取令牌与真实烟测
cf-model-stage/         buildpack staging 预下载模型的本地构建步骤
tests/                  Python API/鉴权回归、Node 音频与传输测试
examples/               Postman collection、环境模板、ABAP 调用示例
docs/                   部署、英文快速开始、验证记录
licenses/               上游 FunASR 代码与 SenseVoice 模型许可副本
```

## 许可证与参与贡献

本仓库原创的服务、网页、脚本和集成示例采用 **[MIT License](LICENSE)**。**MIT 不覆盖下载的模型、第三方依赖或其衍生内容**：SenseVoiceSmall 模型卡指定 FunASR 模型协议；FSMN-VAD 模型卡标注 Apache-2.0。使用或分发模型/镜像时请保留上游署名和相应许可证，详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

感谢 [FunASR](https://github.com/modelscope/FunASR)、[SenseVoice / FunAudioLLM](https://github.com/FunAudioLLM/SenseVoice)、[FSMN-VAD](https://huggingface.co/funasr/fsmn-vad)、[FastAPI](https://github.com/fastapi/fastapi) 和 [SAP cloud-pysec](https://github.com/SAP/cloud-pysec)。

欢迎提交 Issue 和 Pull Request；请先阅读 [贡献指南](CONTRIBUTING.md)。安全问题请参照 [SECURITY.md](SECURITY.md)，不要在公开 Issue 中粘贴 token、服务密钥或客户录音。
