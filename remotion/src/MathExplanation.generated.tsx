/**
 * 大模型根据 Remotion skill 生成的数学讲解组件。
 * 流水线在开启 remotion_generate_code 时会用 LLM 生成的内容覆盖此文件；
 * 未覆盖时与默认 MathExplanation 行为一致，保证项目可构建。
 */
export {
  MathExplanation as MathExplanationGenerated,
  type MathExplanationProps as MathExplanationGeneratedProps,
  type StepInput,
} from "./MathExplanation";
