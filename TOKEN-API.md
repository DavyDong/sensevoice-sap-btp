# Token 与 API 调用

将下文 `https://YOUR_ROUTE` 替换为你自己的部署地址。网页令牌框只粘贴 token 本身；HTTP 使用 `Authorization: Bearer <token>`。本地 loopback 匿名模式无需 token。

## 1. XSUAA：Windows 获取令牌

先使用 `cf login` 和 `cf target` 登录自己的应用空间，确认 `cf target` 输出正确。

```powershell
# 默认 app=sensevoice-asr、service=sensevoice-xsuaa；结果复制到剪贴板。
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/copy_cloud_token.ps1

# 自定义资源名称；返回 token 到变量，不改剪贴板，也不打印正文。
$token = & .\scripts\copy_cloud_token.ps1 -App my-asr -ServiceName my-xsuaa -PassThru
```

也可双击 `Copy-Cloud-Token.cmd`。`Show-Cloud-Token.cmd` 会额外显示完整 token；不要分享该窗口截图或将其输出录入日志。`-CheckOnly` 只测试获取，不打印 token、不写剪贴板。

脚本使用当前 CF target，读取指定应用的 XSUAA 绑定，在内存发起 OAuth 请求，不保存生成的 token。运行期间为隔离 CLI 状态临时复制本机 CF 登录配置，并在 finally 清理；`.cache/` 已忽略。不要并发修改该进程的 target，也不要把 `.cache` 发布出去。

## 2. 其他程序如何获取 token

从**自己的** XSUAA binding/service key 取得 `url`、`clientid` 和 `clientsecret`。令牌地址为 `url + /oauth/token`，方法 `POST`，HTTP Basic 认证，表单 `grant_type=client_credentials`。

PowerShell 示例：调用前通过本地安全配置设置三个环境变量；代码不输出凭据或 token 正文。

```powershell
$tokenUrl = $env:XSUAA_URL.TrimEnd('/') + '/oauth/token'
$basic = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(
    $env:XSUAA_CLIENT_ID + ':' + $env:XSUAA_CLIENT_SECRET))
$response = Invoke-RestMethod -Method Post -Uri $tokenUrl `
    -Headers @{ Authorization = ('Basic ' + $basic) } `
    -ContentType 'application/x-www-form-urlencoded' `
    -Body 'grant_type=client_credentials'
$token = $response.access_token
```

`access_token` 是 OAuth 响应的标准字段；服务端固定令牌配置变量叫 **`ACCESS_TOKEN`**。两者大小写不同是有意的。模板设置短期 token 有效期约 900 秒，客户端以响应 `expires_in` 为准缓存并刷新。不要把 client secret 交给浏览器。

## 3. 使用固定 ACCESS_TOKEN

管理员在 BTP 应用变量配置 **`ACCESS_TOKEN`** 并重启后，这个值可以直接作为网页、HTTP 和 WebSocket token，无需调用 OAuth。允许 32–256 个英文字母、数字和 `. _ ~ + / = -`；建议随机生成。

固定 token 不自动过期；轮换后重启使旧值失效；清空并重启关闭该方式。XSUAA token 继续可用，绑定仍必需。固定 token 是共享的识别权限，不限制来源网络。配置详情见[部署指南](docs/DEPLOYMENT.md)。

## 4. 文件识别

`POST /v1/audio/transcriptions`，`multipart/form-data`：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `file` | 文件，必填 | WAV、FLAC、OGG、MP3；8–48 kHz 单/双声道；最长 120 秒 |
| `language` | 字符串，可选 | `auto`（默认）、`zh`、`en`；混说用 `auto` |

PowerShell（使用上面取得的 `$token`）：

```powershell
$baseUrl = 'https://YOUR_ROUTE'
curl.exe -H "Authorization: Bearer $token" `
    -F "file=@sample.wav" -F "language=auto" `
    "$baseUrl/v1/audio/transcriptions"
```

Python（从调用方环境读取 token，本地安装已包含 httpx）：

```python
import os
from pathlib import Path
import httpx

base_url = os.environ['ASR_BASE_URL'].rstrip('/')
token = os.environ['ASR_ACCESS_TOKEN']
with Path('sample.wav').open('rb') as audio:
    response = httpx.post(
        base_url + '/v1/audio/transcriptions',
        headers={'Authorization': 'Bearer ' + token},
        files={'file': ('sample.wav', audio, 'audio/wav')},
        data={'language': 'auto'},
        timeout=180,
    )
response.raise_for_status()
print(response.json()['text'])
```

响应字段：`text`、`segments[{start_ms,end_ms,text}]`、`audio_seconds`、`inference_seconds`、`rtf`、`language`。RTF = 推理时间 / 音频时长；空白音频返回空文字和空分段。响应不包含逐词对齐。

另外支持 `POST /v1/transcribe?language=auto`：请求体直接放音频二进制，适合 ABAP `XSTRING`；例如：

```powershell
curl.exe -H "Authorization: Bearer $token" -H "Content-Type: audio/wav" `
    --data-binary "@sample.wav" "$baseUrl/v1/transcribe?language=auto"
```

`/v1/transcriptions` 保留为 multipart 兼容别名。没有实现其他平台完整的音频 API 参数或 SDK 兼容性。

| 状态码 | 含义 |
| --- | --- |
| 400 | 音频无法解码、时长/采样格式不合法 |
| 401 | 令牌缺失、无效或过期 |
| 403 | 缺少 Transcribe scope，或 Origin 不允许 |
| 413 | 整个请求超过 20 MiB |
| 422 | 缺少必填字段或语言参数无效 |
| 429 | 当前实例已有识别任务/会话 |

`GET /health/live`、`GET /health/ready` 无需 token；云端不公开 `/docs` / `/openapi.json`。

## 5. WebSocket 麦克风协议

连接 `wss://YOUR_ROUTE/v1/stream`。第一条为 JSON 文本：

```json
{"type":"start","sample_rate":16000,"format":"pcm_s16le","language":"auto","token":"YOUR_TOKEN"}
```

非浏览器也可用握手 `Authorization` 头。不要把 token 放入 URL。

1. 等待服务返回 `ready`。
2. 发送裸 PCM16 little-endian 单声道二进制，16 kHz；每帧 2–3200 字节且长度为偶数。推荐 3200 字节 = 100 ms。不要发送 WAV 文件头、WebM 或 Opus。
3. 每帧返回 `ack`；每段识别返回 `segment`。浏览器采用最多 8 帧待确认窗口；未确认与待发合计超过 2 秒会停止提示，避免静默丢帧。
4. 结束时等待所有帧 ACK，再发送 `{"type":"stop"}`；服务返回尾段与 `done`。

最长会话 10 分钟，空闲 30 秒关闭，XSUAA token 到期关闭；重连不自动拼接之前会话。文件/麦克风共用实例识别容量。可用网页或 `scripts/smoke_test.py` 验证；Postman Collection Runner 不负责 PCM 音频回放。

## 6. Postman 与 ABAP

导入 `examples/SenseVoice.postman_collection.json` 和 `examples/BTP.postman_environment.example.json`。设置自己的 `baseUrl`、`tokenUrl`、`clientId`、`clientSecret`，执行 OAuth 请求；成功后脚本写入 collection 的 `token`。环境模板故意不定义同名 token，避免覆盖 collection 更新结果。

使用固定令牌时，跳过 OAuth 请求，把本地 token 变量设为配置值；分享前清除所有秘密。文件请求需选择本地音频。缺失/无效 token 的负向请求用于云端，匿名本地模式不应期望 401。

`examples/zcl_sensevoice_client.abap` 使用名为 `SENSEVOICE_API` 的 BTP Destination，认证 `OAuth2ClientCredentials`；URL、客户端凭据和 tokenServiceURL 在 Destination 配置。示例发送 WAV `XSTRING` 到原始音频接口，检查 HTTP 状态后由调用方解析 JSON。**示例尚未在 SAP 系统激活执行**；不同 ABAP 版本需要检查 released API 与方法签名。
