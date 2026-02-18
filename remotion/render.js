/**
 * 程序化渲染入口：读取 remotion-input.json，调用 @remotion/renderer 输出 MP4。
 * 调用前需将 TTS 音频文件复制到 remotion/public/audio/（与 audioFileNames 对应）。
 *
 * 用法：node render.js --input <path-to-remotion-input.json> --output <path-to-video.mp4>
 * 或：npm run render -- --input ... --output ...
 */
const path = require("path");
const fs = require("fs");
const { bundle } = require("@remotion/bundler");
const { renderMedia, selectComposition } = require("@remotion/renderer");

const remotionDir = __dirname;
const entryPoint = path.join(remotionDir, "src/index.ts");

async function main() {
  const args = process.argv.slice(2);
  const inputIdx = args.indexOf("--input");
  const outputIdx = args.indexOf("--output");
  const compositionIdx = args.indexOf("--composition");
  if (inputIdx === -1 || !args[inputIdx + 1] || outputIdx === -1 || !args[outputIdx + 1]) {
    console.error("Usage: node render.js --input <remotion-input.json> --output <output.mp4> [--composition <id>]");
    process.exit(1);
  }
  const inputPath = path.resolve(args[inputIdx + 1]);
  const outputPath = path.resolve(args[outputIdx + 1]);
  const compositionId = compositionIdx >= 0 && args[compositionIdx + 1]
    ? args[compositionIdx + 1]
    : "MathExplanation";

  if (!fs.existsSync(inputPath)) {
    console.error("Input file not found:", inputPath);
    process.exit(1);
  }

  const inputProps = JSON.parse(fs.readFileSync(inputPath, "utf-8"));

  console.log("[remotion] Bundling...");
  const bundleLocation = await bundle({
    entryPoint,
    webpackOverride: (config) => config,
  });

  console.log("[remotion] Selecting composition:", compositionId);
  const composition = await selectComposition({
    serveUrl: bundleLocation,
    id: compositionId,
    inputProps,
  });

  console.log("[remotion] Rendering to", outputPath);
  await renderMedia({
    composition,
    serveUrl: bundleLocation,
    codec: "h264",
    outputLocation: outputPath,
    inputProps,
  });

  console.log("[remotion] Done.");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
