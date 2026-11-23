# 1.0.0 参考配置

Windows、2×RTX 4070 SUPER 12 GiB、96 GiB RAM、PyTorch 2.8.0+cu129。权重目录下应有 diffusion_models、text_encoders、vae 三个子目录，文件名见工作流。主模型是 FL2VA pruned INT8 ConvRot。仅使用有权本地运行的权重。

| 组件 | 验证提交 |
|---|---|
| [ComfyUI](https://github.com/Comfy-Org/ComfyUI) | 0072b8680dd2db0b6d68c06f718fa33bd92a728c |
| [Comfy-H3-MultiStream](https://github.com/martonsagi/Comfy-H3-MultiStream) | f2a39fa5406163c30424831664b2d607c211357a |
| [minimax-h3-chunk-star7](https://github.com/star7code/minimax-h3-chunk-star7) | 404d319dc279cb80983cdaf2d33a5c63de849029 |

## 隔离启动

对已能运行 H3 的 Windows ComfyUI，复用同版本源码。在独立目录建立 venv，可用原解释器执行 `-m venv --without-pip <lab>/venv`，再在新环境 Lib/site-packages 中写入 .pth 文件，单独一行指向原环境 Lib/site-packages 的绝对路径。这样共享已安装的运行库，无需修改原环境。确认新解释器能 import torch、comfy_kitchen，以及 torch.cuda.device_count() 返回 2。

建立 lab/run/custom_nodes、lab/output、lab/nodes。把上述两个节点仓库克隆到 lab/nodes 下，保留仓库目录名，checkout 表中提交。新建 lab/nodes.yaml，将以下路径替换成实际绝对路径：

```yaml
lab:
  custom_nodes: D:/example/lab/nodes
```

在 ComfyUI 源码目录运行以下 PowerShell 命令；先设置 $lab 和 $models 为实际绝对路径。服务日志应为本次运行独有，比较基线时使用相同缓存状态。

```powershell
$env:CUDA_DEVICE_ORDER = 'PCI_BUS_ID'
& "$lab/venv/Scripts/python.exe" main.py --listen 127.0.0.1 --port 8199 --cuda-device all --base-directory "$lab/run" --extra-model-paths-config "$lab/nodes.yaml" --models-directory "$models" --output-directory "$lab/output" --disable-all-custom-nodes --whitelist-custom-nodes Comfy-H3-MultiStream minimax-h3-chunk-star7 --offline --disable-dynamic-vram --reserve-vram 4.5 2>&1 | Tee-Object "$lab/server.log"
```

## 验证记录

固定种子 260806，res_multistep / simple / BasicGuider，8 步。原生生成 1280×736、124 帧，上下各裁 8 像素并截取 120 帧；编码参数在脚本中。参考基线使用 Star7 激活分块 RoPE/MLP/QKV 2048/1024/2048，GPU 1 编码、GPU 0 扩散及 Star7 解码。双卡图只替换扩散节点，使用 host 交换、8 个交换分块、关闭稀疏注意力。

| 指标 | 单卡扩散基线 | 双卡扩散 |
|---|---:|---:|
| 8 步采样 | 528 s | 307 s |
| 端到端 | 660.70 s | 391.22 s |
| GPU 0 / GPU 1 峰值（MiB） | 8772 / 8960 | 7699 / 8851 |
| 整机物理内存峰值（GiB） | 68.77 | 83.65 |

一次实测中，50 个块各按 28/28 个注意力头分摊，每步搬运约 28.78 GiB。系统可用内存接近预留的 12 GiB 时，节点关闭权重缓存并继续流式加载。开启缓存的配置不能作为实际命中缓存的证据。上游列出的系统是 Linux；此 Windows 验证覆盖扩散拆分，解码走 Star7。基线和双卡成片的解码视频 SHA-256 均为 `947f2901432579e21555289b44b96263bcec7373918d3e0b9dbd2e5d7739eb10`。其他运行库和硬件的像素结果可能不同。

## Windows 1455 排查

若 safetensors.safe_open 报 Windows 错误 1455，先记录系统已提交内存和提交上限、可用物理内存、相关进程私有占用以及失败节点。即使显存有余量，权重映射也可能因系统提交空间不足而失败。核对当前作业的历史，关闭此次创建的测试实例以释放其缓存；其他模型服务和页面文件配置由其所有者决定。已有成功对照与本次失败应分别报告。
