import React, { useEffect, useRef, useState } from "react";
import { Box, Text, useInput } from "ink";

// Real-time 3D ASCII renderer — a shaded, z-buffered torus (the donut.c trick,
// a1k0n.net/2011/07/20/donut-math.html). It auto-rotates fluidly and the arrow
// keys steer the spin live, so the shape behaves like a turntable you can grab.

const LUM = ".,-~:;=!*#$@"; // dim → bright surface-normal shading ramp
const R1 = 1; // tube radius
const R2 = 2; // torus radius
const K2 = 5; // viewer distance

interface Props {
  width?: number;
  height?: number;
}

function renderTorus(A: number, B: number, w: number, h: number): string[] {
  const cosA = Math.cos(A);
  const sinA = Math.sin(A);
  const cosB = Math.cos(B);
  const sinB = Math.sin(B);

  const out: string[] = new Array(w * h).fill(" ");
  const zbuf = new Float32Array(w * h); // 1/z; 0 = infinitely far

  // Field-of-view scale; halve the vertical term so square-math reads round on
  // terminals where a cell is ~2x taller than wide.
  const K1 = (w * K2 * 3) / (8 * (R1 + R2));

  for (let theta = 0; theta < 6.283; theta += 0.07) {
    const ct = Math.cos(theta);
    const st = Math.sin(theta);
    for (let phi = 0; phi < 6.283; phi += 0.02) {
      const cp = Math.cos(phi);
      const sp = Math.sin(phi);

      const circleX = R2 + R1 * ct;
      const circleY = R1 * st;

      const x = circleX * (cosB * cp + sinA * sinB * sp) - circleY * cosA * sinB;
      const y = circleX * (sinB * cp - sinA * cosB * sp) + circleY * cosA * cosB;
      const z = K2 + cosA * circleX * sp + circleY * sinA;
      const ooz = 1 / z;

      const xp = Math.floor(w / 2 + K1 * ooz * x);
      const yp = Math.floor(h / 2 - K1 * 0.5 * ooz * y);
      if (xp < 0 || xp >= w || yp < 0 || yp >= h) continue;

      const L =
        cp * ct * sinB -
        cosA * ct * sp -
        sinA * st +
        cosB * (cosA * st - ct * sinA * sp);
      if (L <= 0) continue;

      const idx = xp + yp * w;
      if (ooz > zbuf[idx]) {
        zbuf[idx] = ooz;
        const lum = Math.min(LUM.length - 1, Math.max(0, Math.floor(L * 8)));
        out[idx] = LUM[lum];
      }
    }
  }

  const rows: string[] = [];
  for (let r = 0; r < h; r++) rows.push(out.slice(r * w, r * w + w).join(""));
  return rows;
}

// Depth-ish color band by row so the shape reads with a cool gradient.
const ROW_COLORS = ["blueBright", "cyan", "cyanBright", "cyan", "blue"];

export function Spinner3D({ width = 34, height = 14 }: Props) {
  const a = useRef(0);
  const b = useRef(0);
  const va = useRef(0.045);
  const vb = useRef(0.022);
  const paused = useRef(false);
  const [, setTick] = useState(0);

  useInput((input, key) => {
    if (key.leftArrow) vb.current -= 0.02;
    else if (key.rightArrow) vb.current += 0.02;
    else if (key.upArrow) va.current -= 0.02;
    else if (key.downArrow) va.current += 0.02;
    else if (input === " ") paused.current = !paused.current;
    else if (input === "r" || input === "R") {
      va.current = 0.045;
      vb.current = 0.022;
      paused.current = false;
    }
  });

  useEffect(() => {
    const id = setInterval(() => {
      if (!paused.current) {
        a.current += va.current;
        b.current += vb.current;
      }
      setTick((t) => (t + 1) % 1_000_000);
    }, 45);
    return () => clearInterval(id);
  }, []);

  const rows = renderTorus(a.current, b.current, width, height);

  return (
    <Box flexDirection="column">
      {rows.map((line, i) => (
        <Text key={i} color={ROW_COLORS[i % ROW_COLORS.length]}>
          {line}
        </Text>
      ))}
    </Box>
  );
}
