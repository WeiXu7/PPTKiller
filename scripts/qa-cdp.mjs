import { writeFile } from "node:fs/promises";

const DEBUG_PORT = 9223;
const APP_URL = "http://127.0.0.1:5180/";
const SCREENSHOT_PATH = new URL("../frontend-workspace.png", import.meta.url);

const target = await fetch(`http://127.0.0.1:${DEBUG_PORT}/json/new?${encodeURIComponent(APP_URL)}`, {
  method: "PUT",
}).then((response) => response.json());

const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  socket.addEventListener("open", resolve, { once: true });
  socket.addEventListener("error", reject, { once: true });
});

let sequence = 0;
const pending = new Map();
socket.addEventListener("message", (event) => {
  const message = JSON.parse(event.data);
  if (!message.id || !pending.has(message.id)) return;
  const { resolve, reject } = pending.get(message.id);
  pending.delete(message.id);
  if (message.error) reject(new Error(message.error.message));
  else resolve(message.result);
});

function command(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++sequence;
    pending.set(id, { resolve, reject });
    socket.send(JSON.stringify({ id, method, params }));
  });
}

async function evaluate(expression) {
  const result = await command("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text || "Browser evaluation failed");
  return result.result.value;
}

async function waitFor(expression, timeout = 15000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (await evaluate(`Boolean(${expression})`)) return;
    await new Promise((resolve) => setTimeout(resolve, 150));
  }
  throw new Error(`Timed out waiting for: ${expression}`);
}

await command("Page.enable");
await command("Runtime.enable");
await command("Emulation.setDeviceMetricsOverride", {
  width: 1440,
  height: 1024,
  deviceScaleFactor: 1,
  mobile: false,
});
await command("Page.navigate", { url: APP_URL });
await waitFor(`document.readyState === "complete"`);
await evaluate(`localStorage.clear(); location.reload(); true`);
await waitFor(`document.querySelector(".authCard")`);

await evaluate(`Array.from(document.querySelectorAll("button")).find((button) => button.textContent.includes("一键进入演示账户")).click()`);
await waitFor(`document.querySelector(".sidebar")`, 20000);

await evaluate(`document.querySelector(".newProject").click()`);
await waitFor(`document.querySelector(".modal")`);
await evaluate(`(() => {
  const modal = document.querySelector(".modal");
  const inputs = modal.querySelectorAll("input");
  const topic = modal.querySelector("textarea");
  const setValue = (element, value) => {
    const descriptor = Object.getOwnPropertyDescriptor(element.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype, "value");
    descriptor.set.call(element, value);
    element.dispatchEvent(new Event("input", { bubbles: true }));
  };
  setValue(inputs[0], "AI Agent 产品战略");
  setValue(topic, "面向产品与技术团队，分析 Agent 架构、市场机会和实施路线");
  modal.requestSubmit();
})()`);
await waitFor(`document.querySelector(".topbar h2") && document.querySelector(".topbar h2").textContent.includes("AI Agent 产品战略")`, 120000);
await waitFor(`Array.from(document.querySelectorAll(".approvalActions button")).some((button) => button.textContent.includes("通过并继续") && !button.disabled)`, 120000);

await evaluate(`Array.from(document.querySelectorAll(".approvalActions button")).find((button) => button.textContent.includes("通过并继续")).click()`);
await waitFor(`document.querySelector(".step.approval h3") && document.querySelector(".step.approval h3").textContent.includes("最终检查") && !Array.from(document.querySelectorAll(".approvalActions button")).find((button) => button.textContent.includes("通过并继续")).disabled`, 10000);
await evaluate(`Array.from(document.querySelectorAll(".approvalActions button")).find((button) => button.textContent.includes("通过并继续")).click()`);
await waitFor(`document.querySelector(".topbar span") && document.querySelector(".topbar span").textContent.includes("completed")`, 10000);

const screenshot = await command("Page.captureScreenshot", {
  format: "png",
  captureBeyondViewport: false,
  fromSurface: true,
});
await writeFile(SCREENSHOT_PATH, Buffer.from(screenshot.data, "base64"));

const state = await evaluate(`({
  title: document.querySelector(".topbar h2")?.textContent.trim(),
  status: document.querySelector(".topbar span")?.textContent.trim(),
  completed: document.querySelectorAll(".step.done").length,
  exportButton: Array.from(document.querySelectorAll("button")).some((button) => button.textContent.includes("导出PPT"))
})`);

console.log(JSON.stringify({ screenshot: SCREENSHOT_PATH.pathname, state }, null, 2));
socket.close();
