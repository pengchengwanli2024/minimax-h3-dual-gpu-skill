---
name: minimax-h3-dual-gpu
description: 在两张 NVIDIA GPU 上用 ComfyUI MultiStream 分摊同一条 MiniMax H3 视频的扩散采样，部署隔离环境、实跑并对照采样时间、显存和画质。适用于 Windows、现有 H3 FL2VA INT8 权重与低显存内存卸载调优。
metadata:
  version: "1.0.0"
---

# MiniMax H3 双卡采样

先读取同目录的 [环境与实测记录](reference.md)。确认两张物理卡的 PCI 总线与可用显存、可用物理内存、权重文件、ComfyUI 版本以及 ffmpeg / ffprobe / nvidia-smi。比较同一视频时保存原始 API 图，固定权重、提示词、种子、分辨率、帧数、采样器、步数、解码和编码选项。

1. 按参考记录启动独立的本地 ComfyUI 实例，使用单独的节点目录、输出目录和端口。保留原服务。核对 /object_info 中 H3MultiStream 和 MiniMaxH3ChunkedDecodeStar7 已实际注册。
2. 使用随附的 workflows/720p.json。节点 16 将扩散交给两卡；节点 15 只控制文本编码。MultiGPU CFG Split 无法拆分这里的单个正向条件。若用户要求其他提示词或种子，只修改工作副本。
3. 对已启动的实例执行 `python scripts/render.py --port 8199 --output <服务的输出目录>`。默认使用技能随附图，可用 --workflow 指定工作副本。脚本针对该 720p 基准图；新的画幅和时长需要相应更新裁剪与验证。记录返回的任务 ID；客户端断开后先查队列与历史，避免重复提交。
4. 检查该任务对应的服务日志。要求八个 step 都包含 cuda:0+cuda:1、50 blocks，且有 2 ranks 和实际注意力头分配。用 CSV 检查扩散区间两卡利用率。报告完整 8/8 进度行的采样耗时、提交至 MP4 的端到端耗时、两卡采样峰值及整机内存峰值。缓存退化或实际回退到单卡须说明。
5. 用 ffprobe 核实 1280×720、120 帧、24 fps 和五秒音轨。使用 `ffmpeg -v error -i FILE -map 0:v:0 -f hash -hash sha256 -` 比对基线和本轮全部解码帧。哈希相同时可报告像素一致；不同时做全片 SSIM、PSNR 和同帧抽查。单独说明音轨验证范围。
6. 结束本轮启动的服务，保留工作流、版本、日志和采样数据供复核。若上游版本、节点参数或卸载策略有变化，以新候选配置运行同一基准；有可复现收益或明确修复后更新技能与版本。未经实测的组合标为待验证。
