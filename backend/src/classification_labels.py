"""Classification label definitions and mappings.

This module centralizes all classification label definitions, making them
available for both the LLM processor and the RAG query engine.
"""

# All allowed classification labels
ALLOWED_LABELS = {
    "finance", "banking", "investments", "security", "authentication",
    "meetings", "appointments", "personal", "work", "career",
    "shopping", "social", "entertainment", "news", "newsletters",
    "promotions", "marketing", "spam", "travel", "health", "education",
    "legal", "taxes", "receipts", "notifications", "updates", "alerts",
    "support", "bills", "insurance", "job-application", "job-interview",
    "job-offer", "job-rejection", "job-ad", "job-followup"
}

# Map common query terms to classification labels for RAG queries
QUERY_TO_LABEL_MAPPING = {
    'job rejection': 'job-rejection',
    'job rejections': 'job-rejection',
    'rejected': 'job-rejection',
    'rejection': 'job-rejection',
    'job offer': 'job-offer',
    'job offers': 'job-offer',
    'offer': 'job-offer',
    'interview': 'job-interview',
    'interviews': 'job-interview',
    'job application': 'job-application',
    'job applications': 'job-application',
    'applied': 'job-application',
    'job ad': 'job-ad',
    'job ads': 'job-ad',
    'job alert': 'job-ad',
    'job followup': 'job-followup',
    'finance': 'finance',
    'financial': 'finance',
    'banking': 'banking',
    'bank': 'banking',
    'investment': 'investments',
    'investments': 'investments',
    'security alert': 'security',
    'security': 'security',
    'authentication': 'authentication',
    'meeting': 'meetings',
    'meetings': 'meetings',
    'appointment': 'appointments',
    'appointments': 'appointments',
    'promotion': 'promotions',
    'promotions': 'promotions',
    'marketing': 'marketing',
    'newsletter': 'newsletters',
    'newsletters': 'newsletters',
    'shopping': 'shopping',
    'receipt': 'receipts',
    'receipts': 'receipts',
    'bill': 'bills',
    'bills': 'bills',
    'invoice': 'finance',
    'tax': 'taxes',
    'taxes': 'taxes',
    'legal': 'legal',
    'insurance': 'insurance',
    'travel': 'travel',
    'health': 'health',
    'education': 'education',
    'spam': 'spam',
    'notification': 'notifications',
    'notifications': 'notifications',
    'alert': 'alerts',
    'alerts': 'alerts',
    'update': 'updates',
    'updates': 'updates',
    'support': 'support',
}


def get_label_from_query(query: str) -> str | None:
    """Extract classification label from a query string.

    Args:
        query: The user's query (case-insensitive matching will be applied)

    Returns:
        The matching label, or None if no match found
    """
    query_lower = query.lower()

    # Check for longest matches first to handle multi-word terms
    sorted_terms = sorted(QUERY_TO_LABEL_MAPPING.keys(), key=len, reverse=True)

    for term in sorted_terms:
        if term in query_lower:
            return QUERY_TO_LABEL_MAPPING[term]

    return None


def is_classification_query(query: str) -> bool:
    """Check if a query is asking about classification labels.

    Args:
        query: The user's query

    Returns:
        True if the query appears to be asking about classified emails
    """
    return get_label_from_query(query) is not None
