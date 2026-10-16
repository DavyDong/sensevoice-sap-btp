# 参与贡献

欢迎修复问题、完善安装步骤、补充平台验证和改进语音交互。提交 Issue 时说明操作系统、Python/依赖版本、部署方式、操作步骤、期望与实际结果；不要提交客户录音、真实 token、服务密钥或租户日志。

1. Fork 仓库并创建自己的分支。
2. 按 README 安装；不改依赖的接口开发可按 `requirements-test.txt` 安装轻量测试环境。
3. 改动鉴权/API/分段行为时，补充对应回归。运行 `python -m pytest -q`、`node tests/test_worklet.cjs`、`node tests/test_transport.cjs`。
4. 涉及模型/运行时/部署时，在自己的环境执行真实烟测。提交中明确哪些是模拟测试、真实模型、云端联调以及尚未执行的项目。
5. 发起 Pull Request，说明问题、行为变化、验证和兼容性影响；接口变更同步更新文档。

模型不提交到 Git，通过锁定 revision 下载。不要发布 `reports/`、`.cache/`、`models/`、本地部署配置、导出的 Postman 秘密或客户数据。测试中的 `unit-test-only` 值是无效测试夹具，不是部署凭据。

提交原创代码贡献时，需有权以仓库 MIT 许可证提供；第三方内容保留原始许可证和署名。请勿把模型的自定义许可改标为 MIT。
