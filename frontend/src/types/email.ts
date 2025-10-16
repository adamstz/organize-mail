export interface Email {
  id: number;
  subject: string;
  date: string;
  priority: 'High' | 'Medium' | 'Low';
  summary: string;
  body: string;
}