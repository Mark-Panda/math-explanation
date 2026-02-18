/**
 * 数学讲解 Composition：按步骤展示文案与公式，并同步播放 TTS 音频。
 * 实现遵循 remotion-dev/skills 的 compositions / sequencing / audio / animations 规则。
 */
import { interpolate, Series, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { Audio } from "@remotion/media";

export type StepInput = {
  stepId: number;
  description: string;
  mathFormula: string;
  voiceoverText: string;
  durationSeconds: number;
};

export type MathExplanationProps = {
  steps: StepInput[];
  /** 与 steps 顺序一致，如 ["step_1.mp3", "step_2.mp3"]，服务端渲染时文件在 public/audio/ 下 */
  audioFileNames?: string[];
  /** 浏览器播放时使用：与 steps 顺序一致的可访问音频 URL，优先于 audioFileNames */
  audioUrls?: string[];
};

function StepSlide({
  step,
  audioSrc,
}: {
  step: StepInput;
  audioSrc: string | undefined;
}) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const durationInFrames = Math.ceil(step.durationSeconds * fps);

  const opacity = interpolate(
    frame,
    [0, Math.min(0.3 * fps, durationInFrames - 1)],
    [0, 1],
    { extrapolateRight: "clamp" }
  );

  return (
    <div
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: 48,
        opacity,
        background: "#f6f8fa",
        color: "#1f2328",
        fontFamily: "system-ui, -apple-system, sans-serif",
      }}
    >
      {audioSrc ? <Audio src={audioSrc} volume={1} /> : null}
      <div style={{ fontSize: 14, color: "#57606a", marginBottom: 12 }}>
        步骤 {step.stepId}
      </div>
      {step.mathFormula ? (
        <div
          style={{
            fontSize: 28,
            fontWeight: 600,
            marginBottom: 16,
            textAlign: "center",
          }}
        >
          {step.mathFormula.replace(/\$/g, "").trim() || "—"}
        </div>
      ) : null}
      <div style={{ fontSize: 18, lineHeight: 1.6, textAlign: "center", maxWidth: 640 }}>
        {step.description}
      </div>
    </div>
  );
}

function getAudioSrc(
  i: number,
  audioUrls: string[] | undefined,
  audioFileNames: string[] | undefined
): string | undefined {
  if (audioUrls?.[i]) return audioUrls[i];
  if (audioFileNames?.[i]) return staticFile(`audio/${audioFileNames[i]}`);
  return undefined;
}

export const MathExplanation = ({
  steps,
  audioFileNames,
  audioUrls,
}: MathExplanationProps) => {
  const { fps } = useVideoConfig();

  if (!steps.length) {
    return (
      <div
        style={{
          flex: 1,
          alignItems: "center",
          justifyContent: "center",
          background: "#f6f8fa",
          color: "#57606a",
          fontFamily: "system-ui, sans-serif",
        }}
      >
        暂无步骤
      </div>
    );
  }

  return (
    <Series>
      {steps.map((step, i) => (
        <Series.Sequence
          key={step.stepId}
          durationInFrames={Math.ceil(step.durationSeconds * fps)}
          premountFor={5}
        >
          <StepSlide
            step={step}
            audioSrc={getAudioSrc(i, audioUrls, audioFileNames)}
          />
        </Series.Sequence>
      ))}
    </Series>
  );
};
