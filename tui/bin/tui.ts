#!/usr/bin/env node
import { render } from "ink";
import React from "react";
import { App } from "../src/App.js";

const { unmount } = render(React.createElement(App));

// Clean exit on Ctrl+C
process.on("SIGINT", () => {
  unmount();
  process.exit(0);
});
