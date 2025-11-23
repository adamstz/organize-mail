import { Email } from '../types/email';

// helper: extract best possible Date object from backend message dict
export const parseMessageDate = (m: Record<string, unknown>): Date | null => {
  // common fields from different serializers
  const maybeNumber = m.internalDate ?? m.internal_date ?? m['internalDate'] ?? m['internal_date'];
  if (maybeNumber) {
    const n = Number(maybeNumber);
    if (!Number.isNaN(n)) return new Date(n);
  }

  // fetched timestamps (ISO)
  const maybeFetched = m.fetchedAt ?? m.fetched_at ?? m['fetchedAt'] ?? m['fetched_at'];
  if (maybeFetched && (typeof maybeFetched === 'string' || typeof maybeFetched === 'number')) {
    const d = new Date(maybeFetched);
    if (!Number.isNaN(d.getTime())) return d;
  }

  // headers (Date header)
  const headers = m.headers ?? m['headers'];
  if (headers && typeof headers === 'object' && headers !== null) {
    const headersObj = headers as Record<string, unknown>;
    const headerDate = headersObj.Date ?? headersObj.date ?? headersObj['Date'] ?? headersObj['date'];
    if (headerDate && (typeof headerDate === 'string' || typeof headerDate === 'number')) {
      const d = new Date(headerDate);
      if (!Number.isNaN(d.getTime())) return d;
    }
  }

  return null;
};

// Decode HTML entities and strip invisible/control characters
export const decodeHtml = (input: string): string => {
  if (!input) return '';
  try {
    const txt = document.createElement('textarea');
    txt.innerHTML = input;
    return txt.value;
  } catch (e) {
    return input;
  }
};

export const sanitizeText = (input: string): string => {
  if (!input) return '';
  try {
    // decode HTML entities first (e.g. &#39; -> ')
    let out = decodeHtml(input);
    // remove invisible / format / control characters (zero-width spaces, BOM, etc.)
    // Using Unicode property escape to remove all Other/format/control characters.
    // eslint-disable-next-line no-misleading-character-class, no-control-regex
    out = out.replace(/\p{C}/gu, '');
    return out;
  } catch (e) {
    return input;
  }
};

// Define types for Gmail API payload structure
interface GmailPayloadBody {
  data?: string;
}

interface GmailPayloadPart {
  mimeType?: string;
  body?: GmailPayloadBody;
  parts?: GmailPayloadPart[];
}

interface GmailPayload {
  body?: GmailPayloadBody;
  parts?: GmailPayloadPart[];
  mimeType?: string;
}

// Extract readable body from payload
export const extractBody = (payloadObj: GmailPayload | null | undefined): string => {
  if (!payloadObj || typeof payloadObj !== 'object') {
    return '';
  }

  // Check if this part has body data
  if (payloadObj.body?.data) {
    try {
      // Gmail API returns base64url encoded body
      const decoded = atob(payloadObj.body.data.replace(/-/g, '+').replace(/_/g, '/'));
      return decoded;
    } catch (e) {
      // Failed to decode
    }
  }

  // Check for parts (multipart messages)
  if (payloadObj.parts && Array.isArray(payloadObj.parts)) {
    // Prefer text/html over text/plain (like modern email clients)
    // HTML contains images, formatting, and rich content
    const htmlPart = payloadObj.parts.find((p: GmailPayloadPart) => p.mimeType === 'text/html');
    if (htmlPart) {
      return extractBody(htmlPart);
    }

    // Fall back to text/plain if no HTML version
    const textPart = payloadObj.parts.find((p: GmailPayloadPart) => p.mimeType === 'text/plain');
    if (textPart) {
      return extractBody(textPart);
    }

    // Recursively check nested parts
    for (const part of payloadObj.parts) {
      const body = extractBody(part);
      if (body) return body;
    }
  }

  return '';
};

// More aggressive HTML tag stripping function
export const stripHtmlTags = (html: string): string => {
  if (!html) return '';

  let text = html;

  // Remove script and style tags and their content completely
  text = text.replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '');
  text = text.replace(/<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>/gi, '');

  // Remove HTML comments
  text = text.replace(/<!--[\s\S]*?-->/g, '');

  // Replace common block-level tags with newlines before removing them
  text = text.replace(/<\/?(div|p|br|h[1-6]|li|tr|table|thead|tbody)[^>]*>/gi, '\n');

  // Remove all remaining HTML tags (including any attributes)
  text = text.replace(/<[^>]+>/g, '');

  // Remove any standalone HTML attributes that might have leaked through
  text = text.replace(/\b(?:style|class|id|data-[\w-]+)\s*=\s*["'][^"']*["']/gi, '');
  text = text.replace(/\b(?:style|class|id|data-[\w-]+)\s*=\s*\S+/gi, '');

  // Remove CSS-like patterns (e.g., "color: red;", "font-size: 12px;")
  text = text.replace(/\b[\w-]+\s*:\s*[^;]+;/gi, '');

  // Decode HTML entities
  const textarea = document.createElement('textarea');
  textarea.innerHTML = text;
  text = textarea.value;

  return text;
};

// Improved body sanitization
export const sanitizeBody = (text: string): string => {
  if (!text) return '';

  let cleaned = text;

  // First, aggressively strip any HTML tags and CSS
  cleaned = stripHtmlTags(cleaned);

  // Remove common email tracking pixels and hidden content
  cleaned = cleaned.replace(/\[cid:[^\]]+\]/gi, ''); // Remove [cid:...] references

  // Remove CSS @media queries and other at-rules that might have leaked
  cleaned = cleaned.replace(/@(?:media|import|font-face|keyframes|supports|page|charset)[^{]*\{[^}]*\}/gi, '');

  // Remove any remaining curly braces (likely from CSS)
  cleaned = cleaned.replace(/\{[^}]*\}/g, '');

  // Remove excessive newlines/whitespace
  cleaned = cleaned.replace(/\n{3,}/g, '\n\n'); // Max 2 consecutive newlines
  cleaned = cleaned.replace(/[ \t]+/g, ' '); // Normalize spaces/tabs to single space
  cleaned = cleaned.replace(/^\s+/gm, ''); // Remove leading whitespace from lines

  // Remove common email footers/disclaimers patterns
  cleaned = cleaned.replace(/\n*-{3,}\n[\s\S]*?(?:unsubscribe|privacy policy|terms of service)[\s\S]*/gi, '\n\n[footer removed]');

  // Remove zero-width characters and other invisible chars
  cleaned = cleaned.replace(/[\u200B-\u200D\uFEFF]/g, '');

  // Remove control characters except newlines and tabs
  cleaned = cleaned.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, '');

  return cleaned.trim();
};

// Parse backend message to Email type
export const parseBackendMessage = (m: Record<string, unknown>): Email | null => {
  try {
    const formatter = new Intl.DateTimeFormat(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });

    // Fix double-encoded JSON strings from backend
    // labels might be "[\"INBOX\"]" (string) instead of ["INBOX"] (array)
    let labels = m.labels;
    if (typeof labels === 'string' && labels.trim().length > 0) {
      try {
        const parsed = JSON.parse(labels);
        if (Array.isArray(parsed)) {
          labels = parsed;
        }
      } catch (e) {
        labels = []; // Default to empty array on parse error
      }
    }

    // payload might be stringified JSON
    let payload = m.payload;
    if (typeof payload === 'string' && payload.trim().length > 0) {
      try {
        payload = JSON.parse(payload);
      } catch (e) {
        // If it fails, it's probably actual text content, keep it as string
      }
    }

    // headers might be stringified JSON
    let headers = m.headers;
    if (typeof headers === 'string' && headers.trim().length > 0) {
      try {
        const parsed = JSON.parse(headers);
        if (typeof parsed === 'object' && parsed !== null) {
          headers = parsed;
        }
      } catch (e) {
        headers = {}; // Default to empty object on parse error
      }
    }

    // classification_labels might be stringified
    let classificationLabels: string[] | null = null;
    const rawClassLabels = m.classification_labels ?? m.classificationLabels;
    if (typeof rawClassLabels === 'string' && rawClassLabels.trim().length > 0) {
      try {
        const parsed = JSON.parse(rawClassLabels);
        if (Array.isArray(parsed)) {
          classificationLabels = parsed.map(String);
        }
      } catch (e) {
        classificationLabels = null;
      }
    } else if (Array.isArray(rawClassLabels)) {
      classificationLabels = rawClassLabels.map(String);
    }

    const d = parseMessageDate(m);
    const displayDate = d ? formatter.format(d) : '';
    const rawSubject = m.subject ?? m['subject'] ?? 'No subject';
    const rawSummary = m.snippet ?? '';

    // Try to extract readable body
    let rawBody = '';
    if (payload && typeof payload === 'object') {
      rawBody = extractBody(payload);
    }

    // Fallback to raw if no body extracted
    if (!rawBody && m.raw) {
      rawBody = String(m.raw);
    }

    // If still empty, show snippet
    if (!rawBody) {
      rawBody = String(rawSummary);
    }

    // Don't sanitize here - let EmailBodyRenderer handle it
    // This way it can detect HTML and offer rich mode if needed
    const bodyForDisplay = rawBody;

    const priority = m.priority;
    const summary = m.summary;

    // Determine if message is classified
    // Check for non-empty arrays and non-empty strings
    const hasClassificationLabels = Boolean(classificationLabels && Array.isArray(classificationLabels) && classificationLabels.length > 0);
    const hasPriority = Boolean(priority && typeof priority === 'string' && priority.trim().length > 0 && priority.toLowerCase() !== 'null');
    const hasSummary = Boolean(summary && typeof summary === 'string' && summary.trim().length > 0 && summary.toLowerCase() !== 'null');
    const isClassified: boolean = hasClassificationLabels || hasPriority || hasSummary;

    let displayPriority: Email['priority'] = isClassified ? 'Normal' : 'Unclassified';

    if (priority && typeof priority === 'string') {
      const p = priority.toLowerCase();
      if (p === 'high') displayPriority = 'High';
      else if (p === 'medium' || p === 'normal') displayPriority = 'Normal';
      else if (p === 'low') displayPriority = 'Low';
    } return {
      id: String(m.id),
      subject: sanitizeText(String(rawSubject)),
      date: displayDate,
      priority: displayPriority,
      summary: sanitizeText(summary ? String(summary) : String(rawSummary)),
      body: bodyForDisplay, // Use raw body so EmailBodyRenderer can detect HTML
      html: typeof m.html === 'string' ? m.html : undefined,  // Raw HTML from backend
      plain_text: typeof m.plain_text === 'string' ? m.plain_text : undefined,  // Plain text from backend
      classificationLabels: classificationLabels && Array.isArray(classificationLabels)
        ? classificationLabels.map(String)
        : undefined,
      isClassified,
      // Store original data for search filtering
      _raw: {
        from: m.from,
        to: m.to,
      }
    };
  } catch (e) {
    return null;
  }
};
