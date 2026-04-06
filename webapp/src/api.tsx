// src/lib/api.ts

// In production, use relative URLs (nginx proxies to backend)
// In development, use localhost
export const BASE_URL = import.meta.env.DEV
  ? (import.meta.env.VITE_API_BASE_URL || "http://localhost:8080")
  : "";

export const API = {
  sseEvents: `${BASE_URL}/events`,
  startConversation: (user_id: string, mode: string) => `${BASE_URL}/conversation/${user_id}?mode=${encodeURIComponent(mode)}`,
  getFaqs: (graphName: string) => `${BASE_URL}/get_faqs?graph_name=${encodeURIComponent(graphName)}`,
  signupBusiness: (email: string) => `${BASE_URL}/actor/signup/business/email/${encodeURIComponent(email)}`,
  getIndividualByEmail: (email: string) => `${BASE_URL}/party/individual/email/${encodeURIComponent(email)}`,
  graphDiscover: (graphName: string) =>
    `${BASE_URL}/graph/${encodeURIComponent(graphName)}/discover`,
  graphNodes: (graphName: string, limit?: number) =>
    `${BASE_URL}/graph/${encodeURIComponent(graphName)}/nodes${limit ? `?limit=${limit}` : ""}`,
  graphNodesByLabel: (graphName: string, label: string, limit?: number) =>
    `${BASE_URL}/graph/${encodeURIComponent(graphName)}/nodes?label=${encodeURIComponent(label)}${limit ? `&limit=${limit}` : ""}`,
  graphNodeNeighborhood: (graphName: string, nodeId: string | number) =>
    `${BASE_URL}/graph/${encodeURIComponent(graphName)}/nodes/${encodeURIComponent(String(nodeId))}/neighborhood`,
  elicitationRespond: (elicitationId: string) =>
    `${BASE_URL}/elicitation/${encodeURIComponent(elicitationId)}/respond`,
};

