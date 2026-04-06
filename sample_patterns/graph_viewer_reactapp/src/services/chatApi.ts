// Simple UI/API separation. In a real app, fetch from your backend.
// Here we simulate “MCP Server” step logs with small delays.
function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

async function* send(text: string): AsyncGenerator<string> {
  const id = crypto.randomUUID().slice(0, 8);
  const steps = [
    `From MCP Server: Creating task for: "${text}" (session ${id})`,
    "From MCP Server: Setting up agent...",
    "From MCP Server: Initializing...",
    "From MCP Server: Running…",
    "From MCP Server: Completed successfully ✅"
  ];
  for (const s of steps) {
    await sleep(500);
    yield s;
  }
}

export const chatApi = { send };
