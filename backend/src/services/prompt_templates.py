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

QUERY_CLASSIFICATION_PROMPT = """Classify this email query by INTENT. Return ONLY the type name, nothing else.

Query: "{question}"
{chat_context}

NOTE: Pronouns like "those", "them", "of these" reference previous context - focus on what the user wants to DO, not the pronouns.

Types and Examples:

search-by-sender (find emails from specific company/person):
- "last 10 ubereats mail"
- "show me amazon emails"
- "emails from uber"
- "recent doordash orders"
- "netflix messages"
- "mail from john@example.com"
- "from those senders, show me latest" (intent: get from sender)

conversation (greetings, help, thanks):
- "hello"
- "hi there"
- "thank you"
- "thanks"
- "what can you do"
- "help me"

aggregation (count, statistics, rankings):
- "how many emails total"
- "who emails me most"
- "count of unread messages"
- "top 5 senders"
- "how many from amazon"
- "of those, how many are there" (intent: count)
- "from them, who sent most" (intent: rank senders)

temporal (get recent/latest without specific filter):
- "last 10 emails"
- "recent messages"
- "newest emails"
- "show me latest 5"
- "oldest messages"
- "from those, show me 5" (intent: get some from a set)

filtered-temporal (recent + topic/keyword, NOT company):
- "recent emails about the project"
- "latest regarding the meeting"
- "newest about vacation"

classification (filter by label/category like spam, receipts, jobs):
- "show me spam"
- "job rejections"
- "receipt emails"
- "all promotions"
- "of those, which are spam" (intent: filter by spam label)
- "from them, show me receipts" (intent: filter by receipt label)
- "which are interviews" (intent: filter by interview label)

search-by-attachment (find emails with files):
- "emails with attachments"
- "messages with files"
- "which have attachments"
- "of those, which have files" (intent: filter by attachment)

semantic (search by content/topic, NOT label):
- "emails about the alpha project"
- "regarding the client proposal"
- "containing budget information"
- "of those, which mention the deadline" (intent: search content)

RULES:
1. Company/brand names (uber, ubereats, amazon, netflix, etc.) → search-by-sender
2. Labels (spam, receipts, jobs, promotions) → classification
3. Counting/ranking → aggregation
4. Pronouns ("those", "them") don't change the intent type

Classification:"""


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
Return 1-3 keywords separated by commas.

Keywords:"""


# =============================================================================
# SENDER EXTRACTION PROMPTS
# =============================================================================

SENDER_EXTRACTION_PROMPT = """Extract the sender name from the query. Return ONLY the sender name, nothing else.

Query: "emails from uber"
Sender: uber

Query: "show me uber eats emails"
Sender: uber eats

Query: "list last 5 ubereats mail"
Sender: ubereats

Query: "recent paypal receipts"
Sender: paypal

Query: "all my google mail"
Sender: google

Query: "{question}"
Sender:"""


# =============================================================================
# TOPIC EXTRACTION PROMPTS
# =============================================================================

TOPIC_EXTRACTION_PROMPT = """You are extracting a company or sender name from a user's question.
Extract ONLY the company/sender name.

User's question: "{question}"

Instructions:
- Look at the question and identify the company, service, or sender name mentioned
- Return ONLY that name, nothing else
- Do not say "not provided" or similar - extract what IS in the question

Examples:
Question: "how many uber eats emails do I have" → Answer: uber eats
Question: "how many amazon mails" → Answer: amazon
Question: "count my linkedin messages" → Answer: linkedin
Question: "how many github emails" → Answer: github

Now extract from the user's question above. Return ONLY the company/sender name:"""


# =============================================================================
# CHAT SESSION TITLE GENERATION PROMPTS
# =============================================================================

CHAT_TITLE_GENERATION_PROMPT = """Generate a concise title (3-7 words) for a chat session.

User question: "{first_message}"

Rules:
- Return ONLY the title text
- No quotes, no explanations, no extra words
- 3-7 words maximum
- Capture the main topic

Example:
Question: "What invoices did I receive last month?"
Title: Recent Invoice Summary

Question: "Show me emails from Amazon"
Title: Amazon Emails

Now generate the title:"""


# =============================================================================
# CLASSIFICATION HISTORY EXTRACTION PROMPTS
# =============================================================================

CLASSIFICATION_HISTORY_EXTRACTION_PROMPT = """Based on the conversation history below, what email \
classification label is being discussed?

{history_context}

Look for patterns like:
- "promotional emails", "marketing mail", "spam messages"
- "job applications", "interview emails", "rejection notices"
- "receipt emails", "finance messages", "security alerts"

Return ONLY the classification label (one word) or "none" if unclear:

Examples:
History: "how many promotional emails do I have?" → Label: promotional
History: "97 job applications" → Label: job
History: "security alerts" → Label: security

Now extract from the history above:"""
