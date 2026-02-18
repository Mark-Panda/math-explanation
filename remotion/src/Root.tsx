import { Composition } from "remotion";
import { MathExplanation, type MathExplanationProps, type StepInput } from "./MathExplanation";
import {
  MathExplanationGenerated,
  type MathExplanationGeneratedProps,
} from "./MathExplanation.generated";

const FPS = 30;
const WIDTH = 800;
const HEIGHT = 600;

const defaultProps: MathExplanationProps = {
  steps: [],
  audioFileNames: [],
};

const defaultPropsGenerated: MathExplanationGeneratedProps = {
  steps: [],
  audioFileNames: [],
};

const calculateDuration = (props: { steps?: StepInput[] }) => {
  const steps = props.steps;
  if (!steps?.length) return {};
  const durationInFrames = Math.ceil(
    steps.reduce((s, step) => s + step.durationSeconds, 0) * FPS
  );
  return { durationInFrames };
};

export const RemotionRoot = () => {
  return (
    <>
      <Composition
        id="MathExplanation"
        component={MathExplanation}
        durationInFrames={FPS * 60}
        fps={FPS}
        width={WIDTH}
        height={HEIGHT}
        defaultProps={defaultProps}
        calculateMetadata={({ props }) => calculateDuration(props)}
      />
      <Composition
        id="MathExplanationGenerated"
        component={MathExplanationGenerated}
        durationInFrames={FPS * 60}
        fps={FPS}
        width={WIDTH}
        height={HEIGHT}
        defaultProps={defaultPropsGenerated}
        calculateMetadata={({ props }) => calculateDuration(props)}
      />
    </>
  );
};
