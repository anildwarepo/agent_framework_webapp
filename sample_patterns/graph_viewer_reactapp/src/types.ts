export type ChatMessage = {
  id: string;
  role: "user" | "server";
  text: string;
  at: string; // ISO string
};
