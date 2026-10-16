# SAP BTP Cloud Foundry 部署指南

本项目于 2026-10-15 使用 Python buildpack 1.9.4、cflinuxfs5、Python 3.11.16 成功部署并完成真实 HTTP/WSS 和 XSUAA 验证。以下模板面向部署者自己的 BTP 环境，需替换示例值。公开版本的配置泛化不代表已在所有区域重部署。

## 1. 本地准备与平台检查

先完成 [README](../README.md) 的本地安装，下载并测试模型。安装 [Cloud Foundry CLI](https://github.com/cloudfoundry/cli#downloads)。本文终端示例为 Windows PowerShell；macOS/Linux 将 Python 路径替换为 `.venv/bin/python`。

```powershell
cf login -a https://api.cf.YOUR-REGION.hana.ondemand.com --sso
cf target -o YOUR_ORG -s YOUR_SPACE
cf target
cf buildpacks
cf stacks
cf marketplace -e xsuaa
cf domains
```

在 Cockpit 确认可用内存、应用实例和 disk 配额。模板需要 6G 内存/6G disk/1 实例，以及 `xsuaa` 的 `application` 计划。区域 API/domain 应从自己的 BTP 控制台取得，不要把示例字符串当成真实地址。

`runtime.txt` 固定 Python 3.11.16；目标 buildpack 必须提供该版本和 cflinuxfs5。若平台版本不同，先核对 buildpack 支持列表，再调整并重新测试。

## 2. 配置自己的路由和 XSUAA

```powershell
Copy-Item deployment.vars.example.yml deployment.vars.yml
Copy-Item xs-security.json xs-security.local.json
```

编辑 `deployment.vars.yml`：

- `app_name`：空间中属于本项目的应用名，默认 `sensevoice-asr`。
- `route`：可用且唯一的完整域名，例如 `my-team-sensevoice.<cf domains 中的域名>`，不要加 `https://`。
- `xsuaa_service`：本项目的服务名，默认 `sensevoice-xsuaa`。
- `docker_image`：只用于 Docker 部署，buildpack 可忽略。

编辑 `xs-security.local.json` 的 `xsappname`，把 `sensevoice-change-me` 换成子账户中唯一的名称，例如团队加环境名。其余 scope、authorities 和 role-template 保留。以上本地文件已被 `.gitignore` 排除。

```powershell
# 服务名必须与 deployment.vars.yml 的 xsuaa_service 一致。
cf create-service xsuaa application sensevoice-xsuaa -c xs-security.local.json
cf service sensevoice-xsuaa
```

等待服务创建成功再 push。若已有同名资源，确认归属和配置，避免复用其他项目的 XSUAA。修改服务名时，同步后续 helper / cloud_smoke 的参数。

## 3. 打包并部署（推荐 buildpack）

```powershell
.\.venv\Scripts\python.exe scripts/download_models.py --verify
.\.venv\Scripts\python.exe scripts/package_cf.py --stage-models dist/sensevoice-cf.zip
cf push -f manifest-buildpack.yml --vars-file deployment.vars.yml -p dist/sensevoice-cf.zip
cf app sensevoice-asr
```

`--stage-models` 上传精简源码包。`cf-model-stage` 是本仓库可审查的 pip 本地构建步骤，在 staging 下载锁定的官方模型，校验后封装进 droplet。依赖来自 PyPI/PyTorch CPU 源；目标环境需要相应出站网络。`PIP_NO_CACHE_DIR=1` 防止标记包缓存跳过下载。此路径依赖 pip 的原目录构建行为，升级 buildpack 后需要真实烟测。

如果 staging 无法访问模型源，使用本地已验证的模型完整打包：

```powershell
.\.venv\Scripts\python.exe scripts/package_cf.py dist/sensevoice-cf-offline-models.zip
cf push -f manifest-buildpack.yml --vars-file deployment.vars.yml -p dist/sensevoice-cf-offline-models.zip
```

完整包会移除 staging 的模型下载步骤；包大小实测约 872 MB。依赖安装仍需访问包源，因此这不是完全隔离网络的安装方案。两种方式启动时都校验哈希，模型缺失或不匹配会失败。打包器采用白名单，排除 token、虚拟环境、录音和本地部署变量。

CF 注入 `PORT`，程序监听 `0.0.0.0`。不要在 manifest 固定端口；HTTP/WSS 共用一个端口，外部走 HTTPS/WSS。健康检查为 `/health/ready`，冷启动超时配置 180 秒。默认一个 worker；增加 worker 会重复加载模型。

## 4. 认证、调用与回归

按照 [TOKEN-API.md](../TOKEN-API.md) 获取短期 XSUAA token。默认客户端凭据 token 包含 `<xsappname>.Transcribe` 权限。网页手工填入 token；如需完整用户登录，可另行集成 Approuter 和角色集合，当前项目未实现登录重定向流程。

可选：Cockpit → 应用 → User-Provided Variables 新建 **`ACCESS_TOKEN`**。建议随机值，例如本地执行 `python -c "import secrets; print(secrets.token_urlsafe(32))"` 生成。允许 32–256 位英文字母、数字和 `. _ ~ + / = -`，不能包含空格、中文、换行或 `Bearer `。

保存后 **Restart**，当前进程只在启动时读取变量。修改值并重启可轮换；删除/清空并重启可关闭。重启会中断识别请求。XSUAA 校验继续保留，`AUTH_MODE=xsuaa` 和 XSUAA 绑定仍必需。固定 token 不自动过期，不提供用户身份，所有持有者可调用；它不会限制来源网络。

`ACCESS_TOKEN` 故意不写入 manifest，后续 push 不用空值覆盖已配置值。变量可被有权限的管理员读取；不要把真实值写入仓库、CI 输出或导出的环境文件。[Cloud Foundry 环境变量说明](https://docs.cloudfoundry.org/devguide/deploy-apps/environment-variable.html)。

```powershell
# 获取自己的空间 GUID（只用于选择目标空间）：
cf space YOUR_SPACE --guid
.\.venv\Scripts\python.exe scripts/cloud_smoke.py --app sensevoice-asr --service sensevoice-xsuaa --space-guid YOUR_SPACE_GUID
```

烟测要求一个应用 route 和已下载的样例；真实执行 OAuth、中文/英文/拼接混合文件、静音、WSS 回放及鉴权拒绝检查。生成的 `reports/` 含部署地址和转写，默认忽略，不应直接发布。固定 token 可通过环境变量 `ASR_ACCESS_TOKEN` 传给 `scripts/smoke_test.py --url https://YOUR_ROUTE` 做正向验收；这个变量是**测试客户端**配置，与服务端 `ACCESS_TOKEN` 区分。

## 5. Docker 选项（尚未构建验证）

先在 Linux amd64 构建环境下载和校验模型，然后：

```bash
docker build --platform linux/amd64 -t registry.example.com/team/sensevoice-asr:1.0.0 .
docker push registry.example.com/team/sensevoice-asr:1.0.0
cf push -f manifest.yml --vars-file deployment.vars.yml
```

将 `docker_image` 改成实际镜像地址，并先创建上面的 XSUAA 服务。核实 CF 允许 Docker、仓库可访问；私有仓库使用 CLI 支持的凭据配置，凭据不要写入 Dockerfile。镜像包含模型，分发前需遵守上游模型协议。Docker manifest 以 6G 内存/4G disk 开始，需单独测量解压层与启动；buildpack 成功不等于 Docker 镜像验证成功。

## 资源与成本

| 项目 | 观察或默认配置 |
| --- | --- |
| CF 配置 | 1 实例、6G 内存、6G disk、2 个 PyTorch 线程 |
| CF 运行内存样本 | 约 1.38–1.4 GiB；不是容器峰值，不能据此保证缩容 |
| CF 运行磁盘 | 约 2.86–2.9 GiB；staging 压缩还需要临时空间 |
| 本地 Windows 峰值 | 约 3.12 GiB，进程及子进程工作集 |
| 云端 120 秒音频 | 一次测量推理 12.113 秒，RTF 0.101 |
| 费用估算输入 | 按平台的 6 GB 计费档 × 720 小时约 4,320 GB·小时/月，再乘合同单价并核对实例数、其他服务与实际运行时长 |

最初 4G staging disk 在压缩 droplet 时不足，因此 buildpack 模板改为 6G。SAP BTP 上传包与 disk 限制须以目标平台为准；打包器保留 1.5 GB 上传包上限检查。参考 [SAP BTP-specific configurations](https://help.sap.com/docs/BTP/65de2977205c403bbc107264b8eccf4b/9809fa4f02cb4696baea5c23d6eaac94.html)。

free tier 名称不代表该配置免费；以 BTP 合同、Entitlements 和账单为准。该配置也不是并发容量承诺，需要自己的负载测试。

## 常见问题

| 现象 | 检查 |
| --- | --- |
| `Bearer token required` | 网页只粘贴 token；API 加 Authorization Bearer；不要填 client secret |
| 固定 token 修改后无效 | 名称必须为 `ACCESS_TOKEN`，保存后 Restart；检查长度和允许字符 |
| 401 / 403 | token 是否过期、属于正确 XSUAA、具有 Transcribe scope；浏览器 Origin 是否为当前 route |
| 429 | 实例正在识别或麦克风会话未结束，稍后重试 |
| staging 磁盘不足 | 检查 6G disk 和平台配额，不只看最终运行目录大小 |
| 模型校验失败 | 重新下载锁定模型、重新打包；不要跳过哈希校验 |
| microphone 无法启用 | HTTPS/localhost、浏览器权限、输入设备及网络积压提示 |

平台配置方式参考 [CF manifest 文档](https://docs.cloudfoundry.org/devguide/deploy-apps/manifest-attributes.html)。
