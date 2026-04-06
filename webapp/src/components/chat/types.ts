export interface McpLogEntry {
  id: string;
  timestamp: string;
  level: string;
  text: string;
}

export interface ElicitationRequest {
  elicitationId: string;
  message: string;
  options: string[];
  provided: string | null;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  parts?: {
    final: string;
    stream: string;
  };
  isTypingPlaceholder?: boolean;
  isRunLogCollapsed?: boolean;
}

export interface AgentSetting {
  id: string;
  agent_name: string;
  agent_instructions: string;
}

export interface SelectOption {
  value: string;
  label: string;
}
