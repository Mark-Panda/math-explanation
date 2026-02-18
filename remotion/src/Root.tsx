import { Composition } from "remotion";
import { MathExplanation, type MathExplanationProps, type StepInput } from "./MathExplanation";

const FPS = 30;
const WIDTH = 800;
const HEIGHT = 600;

const defaultProps: MathExplanationProps = {
  steps: [],
  audioFileNames: [],
};

export const RemotionRoot = () => {
  return (
    <Composition
      id="MathExplanation"
      component={MathExplanation}
      durationInFrames={FPS * 60}
      fps={FPS}
      width={WIDTH}
      height={HEIGHT}
      defaultProps={defaultProps}
      calculateMetadata={({ props }) => {
        const steps = props.steps as StepInput[];
        if (!steps?.length) {
          return {};
        }
        const durationInFrames = Math.ceil(
          steps.reduce((s, step) => s + step.durationSeconds, 0) * FPS
        );
        return { durationInFrames };
      }}
    />
  );
};
