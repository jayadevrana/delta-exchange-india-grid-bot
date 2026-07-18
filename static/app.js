const startButton = document.getElementById("start-button");
const form = document.getElementById("bot-form");
const otpButton = document.getElementById("otp-button");
const otpOutput = document.getElementById("otp-output");
const stopButton = document.getElementById("stop-button");
const squareOffButton = document.getElementById("square-off-button");
const refreshButton = document.getElementById("refresh-button");

const statusFields = [
  "state",
  "product_symbol",
  "product_id",
  "current_price",
  "approx_mtm",
  "position_size",
  "position_entry_price",
  "grid_orders_sent",
  "target_orders_sent",
  "last_action",
  "last_error",
  "public_note",
];

function setStatus(status) {
  document.getElementById("state").textContent = status.running ? "Running" : "Stopped";
  document.getElementById("product_symbol").textContent = status.product_symbol || "-";
  document.getElementById("product_id").textContent = status.product_id || "-";
  document.getElementById("current_price").textContent = status.current_price || "0";
  document.getElementById("approx_mtm").textContent = status.approx_mtm || "0";
  document.getElementById("position_size").textContent = status.position_size ?? 0;
  document.getElementById("position_entry_price").textContent = status.position_entry_price || "0";
  document.getElementById("grid_orders_sent").textContent = status.grid_orders_sent ?? 0;
  document.getElementById("target_orders_sent").textContent = status.target_orders_sent ?? 0;
  document.getElementById("last_action").textContent = status.last_action || "Idle";
  document.getElementById("last_error").textContent = status.last_error || "None";
  document.getElementById("public_note").textContent = status.public_note || "";
  document.getElementById("log-output").textContent = (status.logs || []).join("\n") || "No logs yet.";
}

async function postForm(url, extraFields = {}) {
  const data = form ? new FormData(form) : new FormData();
  Object.entries(extraFields).forEach(([key, value]) => data.set(key, value));
  const response = await fetch(url, { method: "POST", body: data });
  const payload = await response.json();
  if (!response.ok || !payload.ok) {
    throw new Error(payload.error || "Request failed");
  }
  return payload.status || payload;
}

async function refreshStatus() {
  const response = await fetch("/api/status");
  const payload = await response.json();
  if (payload.ok) {
    setStatus(payload.status);
  }
}

startButton.addEventListener("click", async () => {
  try {
    const status = await postForm("/api/start");
    setStatus(status);
  } catch (error) {
    alert(error.message);
  }
});

otpButton.addEventListener("click", async () => {
  const response = await fetch("/api/totp", { method: "POST" });
  const payload = await response.json();
  otpOutput.textContent = payload.ok ? `Current OTP: ${payload.otp}` : payload.error;
});

stopButton.addEventListener("click", async () => {
  try {
    const status = await postForm("/api/stop", {
      cancel_orders: "true",
      close_positions: "false",
    });
    setStatus(status);
  } catch (error) {
    alert(error.message);
  }
});

squareOffButton.addEventListener("click", async () => {
  if (!window.confirm("Cancel all orders and close positions for this product?")) {
    return;
  }
  try {
    const response = await fetch("/api/square-off", { method: "POST" });
    const payload = await response.json();
    if (!payload.ok) {
      throw new Error(payload.error || "Square off failed");
    }
    setStatus(payload.status);
  } catch (error) {
    alert(error.message);
  }
});

refreshButton.addEventListener("click", refreshStatus);
setInterval(refreshStatus, 2500);
refreshStatus();
