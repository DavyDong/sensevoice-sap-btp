# Third-party software and model notices

The root [MIT License](LICENSE) applies to the original integration code in this repository. It does not relicense upstream frameworks, downloaded models, example recordings or their derivatives. No model weights or audio recordings are distributed in this Git repository.

| Component | Source / pinned reference | License information |
| --- | --- | --- |
| FunASR framework | [modelscope/FunASR](https://github.com/modelscope/FunASR), Python package 1.4.16 | [MIT](https://github.com/modelscope/FunASR/blob/main/LICENSE); retained copy: [licenses/FunASR-LICENSE.txt](licenses/FunASR-LICENSE.txt) |
| SenseVoiceSmall model | [FunAudioLLM/SenseVoiceSmall at 3847d57](https://huggingface.co/FunAudioLLM/SenseVoiceSmall/blob/3847d57b6bdf2dd8875cb1508d2af43d80a16bf7/README.md), [SenseVoice project](https://github.com/FunAudioLLM/SenseVoice) | Model card specifies `license: other` and links to the [FunASR Model License](https://github.com/modelscope/FunASR/blob/main/MODEL_LICENSE); retained copy: [licenses/SenseVoice-MODEL_LICENSE.txt](licenses/SenseVoice-MODEL_LICENSE.txt) |
| FSMN-VAD model | [funasr/fsmn-vad at df20e6b](https://huggingface.co/funasr/fsmn-vad/blob/df20e6b30c653645fa4ff125cacfcabd1020a669/README.md) | Pinned model card declares Apache-2.0; [license text](licenses/Apache-2.0.txt); preserve upstream notices when distributing the model |
| FastAPI | [fastapi/fastapi](https://github.com/fastapi/fastapi) | MIT; see upstream LICENSE |
| SAP XSUAA Python library (`sap-xssec`) | [SAP/cloud-pysec](https://github.com/SAP/cloud-pysec) | Apache-2.0; see upstream LICENSE |
| PyTorch / torchaudio and remaining dependencies | Versions in `requirements-*.lock`; official package distributions | Retain their own licenses and bundled notices; they are not covered by this repository's MIT grant |

The SenseVoice model agreement is a separate agreement with attribution and other terms; this repository does not describe those model weights as MIT-licensed or promise unrestricted use. Read the full upstream agreement before downloading, using, modifying or redistributing the model. The agreement copy was checked against upstream on 2026-10-16; upstream terms may change.

The downloader preserves model repository names and README files. Deployment packages and Docker images contain downloaded models, so redistribution of those artifacts requires their applicable licenses and notices too. The original integration license and notices are also included by the packager and Dockerfile.

SAP and other product/project names identify compatibility and dependencies; this is an independent community integration without an endorsement or affiliation claim.
