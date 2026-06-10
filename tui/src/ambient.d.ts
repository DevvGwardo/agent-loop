declare module "ink-gradient" {
  import type { ReactNode } from "react";
  interface GradientProps {
    name?: string;
    colors?: string[];
    children?: ReactNode;
  }
  const Gradient: (props: GradientProps) => JSX.Element;
  export default Gradient;
}

declare module "ink-big-text" {
  interface BigTextProps {
    text: string;
    font?: string;
    align?: "left" | "center" | "right";
    space?: boolean;
    colors?: string[];
    backgroundColor?: string;
    letterSpacing?: number;
    lineHeight?: number;
  }
  const BigText: (props: BigTextProps) => JSX.Element;
  export default BigText;
}
