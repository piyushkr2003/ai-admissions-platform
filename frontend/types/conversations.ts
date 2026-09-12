export type ConversationSummary = {
  conversation_id: string;
  status: string;
  intent: string | null;
  summary: string | null;
  language: string | null;
};

export type ConversationMessage = {
  role: string;
  content: string;
  timestamp: string;
};
