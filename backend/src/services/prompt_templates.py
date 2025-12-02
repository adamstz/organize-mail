"""Centralized prompt templates for LLM operations.

This module consolidates all prompt templates used throughout the application,
organized by functionality. All templates use LangChain's PromptTemplate class
for consistency and composability.
"""
from langchain_core.prompts import PromptTemplate

# =============================================================================
# CLASSIFICATION PROMPTS
# =============================================================================

# System message for classification tasks
CLASSIFICATION_SYSTEM_MESSAGE = "You are an email classification assistant. Return only valid JSON with no explanations."


def build_classification_prompt(subject: str, body: str) -> str:
    """Build a structured prompt for LLM classification.

    Args:
        subject: Email subject
        body: Email body (will be truncated to 2000 chars)

    Returns:
        Formatted prompt string for LLM
    """
    # Truncate body to avoid token limits
    body_truncated = body[:2000] if body else ""

    return f"""Classify this email into categories, assign a priority level, and provide a brief summary.

Email to classify:
Subject: {subject}
Body: {body_truncated}

Instructions:
- You MUST ONLY choose labels from this exact list (do not create new labels):
  finance, banking, investments, security, authentication, meetings, appointments,
  personal, work, career, shopping, social, entertainment, news, newsletters,
  promotions, marketing, spam, travel, health, education, legal, taxes, receipts,
  notifications, updates, alerts, support, bills, insurance, job-application,
  job-interview, job-offer, job-rejection, job-ad, job-followup
- For job-related emails, use specific job labels:
  * job-application: confirmation that you applied for a job
  * job-interview: interview invitations or scheduling
  * job-offer: job offers received
  * job-rejection: rejection notifications
  * job-ad: job opportunity advertisements (LinkedIn, Indeed, etc.)
  * job-followup: follow-up emails about applications
- Choose 1-3 most relevant labels from the list above
- Assign priority: "high" (urgent/important), "normal" (routine), or "low" (can wait)
- Write a brief summary (1-2 sentences) of the email's main purpose
- Return ONLY a JSON object in this exact format:

{{"labels": ["category1", "category2"], "priority": "normal", "summary": "Brief description of the email"}}

Do not include explanations or markdown. Only output valid JSON. Do not invent labels not in the list."""


# =============================================================================
# RAG QUERY CLASSIFICATION PROMPTS
# =============================================================================

QUERY_CLASSIFICATION_PROMPT = """Classify this email query in ONE word:

"{question}"

Query types:
- conversation: greetings, thanks, help requests (hi, hello, thank you, what can you do)
- aggregation: statistics, counting, top senders (how many total, who emails most, count of)
- search-by-sender: find all from specific sender without time constraint (all from X, emails from Y)
- search-by-attachment: find emails with attachments (with attachments, has files)
- classification: label-based queries (job rejections, spam emails, receipts)
- filtered-temporal: time + topic/sender (recent uber emails, latest from amazon, last week's newsletters)
- temporal: pure time-based (recent emails, last 5 emails, newest messages) without specific topic
- semantic: content search without time constraint (about project alpha, regarding meeting)

Rules:
- If has BOTH time word (recent/latest/last) AND topic/sender → filtered-temporal
- If asks "how many total" or "who emails most" → aggregation
- If "all from X" without time → search-by-sender
- If greeting/thanks → conversation
- If time word but no topic → temporal
- Otherwise → semantic

Answer with ONE word only:"""


# =============================================================================
# RAG RETRIEVAL PROMPTS
# =============================================================================

# Semantic search RAG prompt template
SEMANTIC_SEARCH_PROMPT = PromptTemplate.from_template(
    """You are an email assistant. I have retrieved emails from the user's \
mailbox and YOU MUST analyze them.

CRITICAL: The emails below are REAL emails from the user's database. \
You have been given these emails TO ANALYZE - this is your job. \
Do NOT refuse or say you cannot access them.

YOUR TASK:
- For "how many" questions: Count the emails that match based on subject/content
- For other questions: Extract and summarize the relevant information
- Be specific and cite emails by their numbers
- RESPOND IN NATURAL LANGUAGE, NOT JSON. Write a conversational, helpful answer.

===== EMAILS FROM USER'S MAILBOX =====

{context}

===== USER QUESTION =====

{question}

Analyze the emails above and answer the question naturally."""
)

# Classification-based query prompt
CLASSIFICATION_QUERY_PROMPT = PromptTemplate.from_template(
    """You are an email assistant with DIRECT ACCESS to the user's email database.

The emails below are REAL emails from the user's mailbox that match the label '{label}'.
Total emails with this label: {total_count}
Sample shown below: {sample_count} emails

YOUR TASK: Answer the user's question about these labeled emails.
- Count how many if asked
- Summarize the content if asked
- List specific examples if asked
- RESPOND IN NATURAL LANGUAGE, NOT JSON

===== LABELED EMAILS =====

{context}

===== USER QUESTION =====

{question}

Answer naturally based on the emails above."""
)

# Temporal query prompt
TEMPORAL_QUERY_PROMPT = PromptTemplate.from_template(
    """You are an email assistant. The emails below are from the user's mailbox, sorted by date (most recent first).

YOUR TASK: Answer the question about these recent emails.
- If asked for "most recent" or "latest", focus on the top emails
- If asked "how many", count the relevant ones
- Be specific about dates and senders
- RESPOND IN NATURAL LANGUAGE, NOT JSON

===== RECENT EMAILS (newest first) =====

{context}

===== USER QUESTION =====

{question}

Answer naturally based on the emails above."""
)

# Filtered temporal query prompt (time + content filtering)
FILTERED_TEMPORAL_PROMPT = PromptTemplate.from_template(
    """You are an email assistant. The emails below are from the user's \
mailbox, filtered by both time and content, sorted by date \
(most recent first).

The search was filtered for keywords: {keywords}

YOUR TASK: Answer the question about these filtered emails.
- Focus on the most recent matches
- If asked "how many", count them
- Be specific about subjects and dates
- RESPOND IN NATURAL LANGUAGE, NOT JSON

===== FILTERED EMAILS (newest first) =====

{context}

===== USER QUESTION =====

{question}

Answer naturally based on the filtered emails above."""
)

# Aggregation query prompt
AGGREGATION_QUERY_PROMPT = PromptTemplate.from_template(
    """You are an email assistant. I've gathered statistics from the user's email database.

YOUR TASK: Answer the user's statistics question using the data below.
- Present numbers clearly
- Highlight top items if relevant
- Be concise but informative
- RESPOND IN NATURAL LANGUAGE, NOT JSON

===== EMAIL STATISTICS =====

{stats}

===== USER QUESTION =====

{question}

Answer naturally based on the statistics above."""
)

# Search by sender prompt
SEARCH_BY_SENDER_PROMPT = PromptTemplate.from_template(
    """You are an email assistant. The emails below are all from sender(s): {sender}

YOUR TASK: Answer the question about emails from this sender.
- Summarize the email content
- Note patterns or themes
- Count if asked
- RESPOND IN NATURAL LANGUAGE, NOT JSON

===== EMAILS FROM {sender} =====

{context}

===== USER QUESTION =====

{question}

Answer naturally based on the emails above."""
)

# Search by attachment prompt
SEARCH_BY_ATTACHMENT_PROMPT = PromptTemplate.from_template(
    """You are an email assistant. The emails below all have attachments.

YOUR TASK: Answer the question about emails with attachments.
- Describe what was found
- Note senders and subjects
- Count if asked
- RESPOND IN NATURAL LANGUAGE, NOT JSON

===== EMAILS WITH ATTACHMENTS =====

{context}

===== USER QUESTION =====

{question}

Answer naturally based on the emails above."""
)

# Conversation/greeting prompt
CONVERSATION_PROMPT = PromptTemplate.from_template(
    """You are a helpful email assistant chatbot.

The user said: "{question}"

Respond naturally:
- If greeting: Be friendly and introduce yourself
- If asking what you can do: Explain you can search emails, answer questions, find recent messages, etc.
- If thanking: Acknowledge graciously
- Keep it brief and conversational
- RESPOND IN NATURAL LANGUAGE, NOT JSON

Your response:"""
)

# =============================================================================
# KEYWORD EXTRACTION PROMPTS
# =============================================================================

KEYWORD_EXTRACTION_PROMPT = """Extract search keywords from this query in ONE line:

"{question}"

Extract ONLY the important content words (people, companies, topics, products).
Remove time words (recent, latest, last, newest).
Return 2-4 keywords separated by spaces.

Keywords:"""


# =============================================================================
# SENDER EXTRACTION PROMPTS
# =============================================================================

SENDER_EXTRACTION_PROMPT = """Extract the sender name/email from this query:

"{question}"

Return ONLY the sender name or email address, nothing else.
If no sender mentioned, return "unknown".

Sender:"""
