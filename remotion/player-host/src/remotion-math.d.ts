/** 仅类型声明，实际由 Vite alias 解析到 remotion/src/MathExplanation.tsx */
declare module "@remotion-math" {
  import type { ComponentType } from "react";
  export interface StepInput {
    stepId: number;
    description: string;
    mathFormula: string;
    voiceoverText: string;
    durationSeconds: number;
  }
  export interface MathExplanationProps {
    steps: StepInput[];
    audioFileNames?: string[];
    audioUrls?: string[];
  }
  export const MathExplanation: ComponentType<MathExplanationProps>;
}
