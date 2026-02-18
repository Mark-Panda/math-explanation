import React from "react";
import ReactDOM from "react-dom/client";
import { Player } from "@remotion/player";
import { MathExplanation, type MathExplanationProps } from "@remotion-math";

const FPS = 30;
const WIDTH = 800;
const HEIGHT = 600;

function getTaskId(): string | null {
  const params = new URLSearchParams(window.location.search);
  return params.get("task_id");
}

function App() {
  const taskId = getTaskId();
  const [props, setProps] = React.useState<MathExplanationProps | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    if (!taskId) {
      setError("请提供 task_id，例如 /player/?task_id=xxx");
      setLoading(false);
      return;
    }
    const url = `/results/${taskId}/remotion-props.json`;
    fetch(url)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => setProps(data as MathExplanationProps))
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [taskId]);

  if (loading) {
    return (
      <div style={{ padding: 24, fontFamily: "system-ui", color: "#57606a" }}>
        加载中…
      </div>
    );
  }
  if (error || !props) {
    return (
      <div style={{ padding: 24, fontFamily: "system-ui", color: "#f85149" }}>
        {error || "未获取到 remotion-props"}
      </div>
    );
  }

  const steps = (props.steps as Array<{ durationSeconds: number }>) ?? [];
  const durationInFrames = Math.ceil(
    steps.reduce((s, step) => s + step.durationSeconds, 0) * FPS
  ) || FPS * 60;

  return (
    <div style={{ padding: 16, maxWidth: 900, margin: "0 auto" }}>
      <Player
        component={MathExplanation as unknown as React.ComponentType<Record<string, unknown>>}
        inputProps={props as unknown as Record<string, unknown>}
        durationInFrames={durationInFrames}
        compositionWidth={WIDTH}
        compositionHeight={HEIGHT}
        fps={FPS}
        style={{ width: "100%", maxWidth: WIDTH }}
        controls
        loop={false}
      />
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
