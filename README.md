## QQ to ComfyUI 自动图片转视频助手

该项目提供了一个纯 Python（仅使用标准库）实现的 QQ 消息监听与 ComfyUI 工作流调度服务，用于完成以下任务：

1. 监听 go-cqhttp（OneBot v11）推送的群消息，筛选出 `@机器人` 且包含图片的消息。
2. 将图片与可选提示词/分辨率参数送入本地运行的 ComfyUI，执行图片转视频工作流。
3. 长时间轮询（5-10 分钟或更久）等待视频生成完成，随后自动把视频回传至 QQ 群，并发送提示文本。

### 目录结构

```
.
├── README.md
├── config.example.json        # 配置示例，复制为 config.json 后自行修改
├── workflows/
│   └── image_to_video.example.json   # ComfyUI 工作流示例（需要根据自己实际工作流调整）
└── src/
    ├── main.py
    ├── server.py
    ├── task_runner.py
    ├── comfyui_client.py
    ├── qq_client.py
    ├── qq_events.py
    ├── config_loader.py
    └── utils.py
```

### 运行要求

- Python ≥ 3.10。
- 已部署并运行中的 ComfyUI，且开启了 HTTP API（默认 `http://127.0.0.1:8188`）。
- go-cqhttp（或其它 OneBot v11 兼容实现）配置了 HTTP POST 上报到本服务。

### 快速开始

1. **创建配置文件**

   ```bash
   copy config.example.json config.json
   ```

   根据实际情况修改字段：

   - `qq.bot_qq`：机器人 QQ 号，用于判断是否被 @。
   - `qq.api_base` 与 `qq.access_token`：go-cqhttp HTTP 服务地址及鉴权。
   - `qq.allowed_groups`：允许触发的群列表。
   - `comfyui.workflow_path`：本地 ComfyUI 工作流 JSON。
   - `comfyui.workflow_overrides`：指定需要注入图片、提示词和分辨率参数的节点信息（节点 id 可在 ComfyUI 导出的 workflow JSON 中查看）。

2. **准备数据目录**

   ```
   mkdir data\data_in
   mkdir data\data_out
   ```

   （或在 config.json 中自定义路径）

3. **启动服务**

   ```bash
   python -m src.main
   ```

### 处理逻辑概览

1. HTTP Server（`src/server.py`）接收 go-cqhttp 上报，校验签名后验证消息内容。
2. `task_runner.TaskQueue` 将任务写入队列，并发送“正在处理”的群消息。
3. `ComfyUIClient` 在独立线程中：
   - 下载 QQ 图片；
   - 上传至 ComfyUI `/upload/image`；
   - 按配置修改工作流参数（图片、提示词、分辨率）；
   - 调用 `/prompt` 并轮询 `/history/{id}`；
   - 下载生成的视频保存到 output 目录。
4. `QQClient` 将视频通过 `upload_group_file` 上传，并在群内回复完成提示。

### 消息格式

- 图片：必须至少包含一个 QQ 图片（`image` 消息段）。
- 提示词：其余文本片段自动拼接为提示词，可选。
- 分辨率：文本中若匹配 `数字x数字`（例如 `768x1344`），将覆盖默认宽高。

### 重要说明

- ComfyUI 工作流中必须存在可被配置字段的节点（例如 `LoadImage` 的 `image` 字段、 `KSampler` / `AnimateDiff` 等的 `width`/`height` 字段）。需根据自身 workflow 修改 `workflow_overrides`。
- 服务为长耗时任务设计，若在 `timeout_seconds` 内仍未完成会向群里返回失败信息。
- 项目未依赖第三方库，方便在受限环境下运行，但若可安装依赖，建议替换为 `FastAPI`、`requests` 等库以提升开发效率。

### 调试建议

1. 使用 go-cqhttp 的 HTTP 调试面板直接 POST 事件到 `server.host:server.port`，确认解析正常。
2. 先在 ComfyUI 面板手动执行 workflow，确认输出位于 `output` 子目录，并记录需要替换的节点 id。
3. 将 `config.json` 中 `processing.debug` 设为 `true`（如需），即可输出更多日志。

### 下一步

- 根据自己工作流完善 `workflows/image_to_video.example.json`。
- 根据群/机器人需求扩展命令，例如查询队列状态、取消任务等。
