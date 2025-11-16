import { Email } from '../types/email';

export const exampleEmails: Email[] = [
  {
    id: '1',
    subject: 'Project Update Meeting',
    date: '2025-10-14',
    priority: 'High',
    summary: 'Discussion about Q4 milestones and upcoming deadlines',
    body: "Dear team,\n\nI wanted to follow up on our project status and discuss the upcoming milestones for Q4. We need to ensure we're on track with our deliverables and address any potential blockers.\n\nBest regards,\nJohn",
    classificationLabels: ['Work', 'Meeting'],
    isClassified: true,
  },
  {
    id: '2',
    subject: 'New Feature Release',
    date: '2025-10-13',
    priority: 'Normal',
    summary: 'Announcing the release of our new dashboard features',
    body: "Hello everyone,\n\nWe're excited to announce the release of our new dashboard features. This includes improved analytics, customizable widgets, and better performance optimizations.\n\nRegards,\nProduct Team",
    classificationLabels: ['Product', 'Announcement'],
    isClassified: true,
  },
  {
    id: '3',
    subject: 'Team Lunch Next Week',
    date: '2025-10-12',
    priority: 'Low',
    summary: 'Planning for team lunch and social gathering',
    body: "Hi all,\n\nLet's plan for a team lunch next week to celebrate our recent successes. Please fill out the preference form for restaurant options.\n\nCheers,\nHR Team",
    classificationLabels: ['Social'],
    isClassified: true,
  },
];

export default exampleEmails;
