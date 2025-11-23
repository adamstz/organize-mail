export interface Email {
  id: string;
  subject: string;
  date: string;
  priority: 'High' | 'Normal' | 'Low' | 'Unclassified';
  summary: string;
  body: string;
  html?: string;  // Raw HTML from email payload
  plain_text?: string;  // Plain text version
  classificationLabels?: string[];
  isClassified: boolean;
  _raw?: {
    from?: unknown;
    to?: unknown;
  };
}