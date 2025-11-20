export interface SourceEmail {
  message_id: string;
  subject: string;
  date: string;
  from?: string;
  similarity: number;
  snippet: string;
}

export interface ChatMessage {
  id: string;
  type: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  sources?: SourceEmail[];
  confidence?: string;
  isLoading?: boolean;
  error?: string;
}
