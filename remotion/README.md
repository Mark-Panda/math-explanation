# 数学讲解 Remotion 子项目

本目录为项目内集成的 Remotion 模块，实现遵循 [remotion-dev/skills](https://github.com/remotion-dev/skills) 的 composition、sequencing、audio、animations 等规则。提供两种使用方式：

- **网页播放**：`player-host/` 为 Vite 构建的 Remotion Player 页面，读取 `results/{task_id}/remotion-props.json` 与音频，在浏览器中播放同一套 Composition。
- **MP4 渲染**：`src/` + `render.js`，由 Python 在 `REMOTION_ENABLED=true` 时调用，产出 `animation.mp4`。

## 目录说明

- `src/`：Composition 源码（`Root.tsx`、`MathExplanation.tsx`）
- `player-host/`：Remotion 网页播放器前端，构建后由主服务挂载到 `/player/`
- `public/audio/`：服务端渲染 MP4 时由 Python 复制 TTS 音频到此

## 网页播放器（Remotion 作为网页动画）

```bash
cd player-host
npm install
npm run build
cd ../..
```

主服务会挂载 `remotion/player-host/dist` 到 `/player/`。生成任务成功后，打开 `/player/?task_id=xxx` 即可在浏览器中播放（前端历史记录中有「Remotion 播放」入口）。

## 安装与 Studio 预览

```bash
npm install
npm run start   # 打开 Remotion Studio（需手动提供 inputProps 或使用默认）
```

## 程序化渲染 MP4（由 Python 调用）

流水线在 `REMOTION_ENABLED=true` 时会：

1. 将 steps、时长与音频文件名写入任务目录下的 `remotion-input.json`
2. 将 `work/audio/step_*.mp3` 复制到本目录 `public/audio/`
3. 执行 `node render.js --input ... --output ...` 生成 MP4

也可在项目根目录手动测试（需先有 `remotion-input.json` 与 `public/audio/` 内音频）：

```bash
cd remotion
npm install
node render.js --input /path/to/remotion-input.json --output /path/to/animation.mp4
```
