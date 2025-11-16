export interface Email {
  id: string;
  subject: string;
  date: string;
  priority: 'High' | 'Normal' | 'Low' | 'Unclassified';
  summary: string;
  body: string;
  classificationLabels?: string[];
  isClassified: boolean;
  _raw?: {
    from?: unknown;
    to?: unknown;
  };
}