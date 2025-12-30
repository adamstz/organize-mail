"""Sample email payloads for testing get_body_text() and full body extraction.

This module provides factory functions to create various email payload structures
for testing the MailMessage.get_body_text() method with different MIME types,
multipart structures, and edge cases.
"""
import base64
from typing import Dict, Any


def make_simple_text_payload(text: str) -> Dict[str, Any]:
    """Create simple text/plain payload.
    
    Args:
        text: Plain text content for the email body
        
    Returns:
        Gmail API payload dict with single text/plain part
    """
    encoded = base64.urlsafe_b64encode(text.encode('utf-8')).decode('ascii')
    return {
        "mimeType": "text/plain",
        "body": {
            "data": encoded,
            "size": len(text)
        }
    }


def make_multipart_payload(text_plain: str, text_html: str) -> Dict[str, Any]:
    """Create multipart/alternative payload with both plain and HTML versions.
    
    Args:
        text_plain: Plain text version
        text_html: HTML version
        
    Returns:
        Gmail API payload with multipart/alternative structure
    """
    plain_encoded = base64.urlsafe_b64encode(text_plain.encode('utf-8')).decode('ascii')
    html_encoded = base64.urlsafe_b64encode(text_html.encode('utf-8')).decode('ascii')
    
    return {
        "mimeType": "multipart/alternative",
        "parts": [
            {
                "mimeType": "text/plain",
                "body": {
                    "data": plain_encoded,
                    "size": len(text_plain)
                }
            },
            {
                "mimeType": "text/html",
                "body": {
                    "data": html_encoded,
                    "size": len(text_html)
                }
            }
        ]
    }


def make_nested_multipart_payload(text: str) -> Dict[str, Any]:
    """Create deeply nested multipart structure.
    
    Args:
        text: Text content to nest
        
    Returns:
        Gmail API payload with nested multipart structure
    """
    encoded = base64.urlsafe_b64encode(text.encode('utf-8')).decode('ascii')
    
    return {
        "mimeType": "multipart/mixed",
        "parts": [
            {
                "mimeType": "multipart/alternative",
                "parts": [
                    {
                        "mimeType": "text/plain",
                        "body": {
                            "data": encoded,
                            "size": len(text)
                        }
                    }
                ]
            }
        ]
    }


def make_html_only_payload(html: str) -> Dict[str, Any]:
    """Create HTML-only payload (no plain text version).
    
    Args:
        html: HTML content
        
    Returns:
        Gmail API payload with only HTML part
    """
    encoded = base64.urlsafe_b64encode(html.encode('utf-8')).decode('ascii')
    
    return {
        "mimeType": "text/html",
        "body": {
            "data": encoded,
            "size": len(html)
        }
    }


def make_invalid_base64_payload() -> Dict[str, Any]:
    """Create payload with invalid base64 encoding.
    
    Returns:
        Gmail API payload with malformed base64 data
    """
    return {
        "mimeType": "text/plain",
        "body": {
            "data": "!!!invalid-base64-data!!!",
            "size": 100
        }
    }


def make_attachment_payload(text: str, attachment_name: str = "document.pdf") -> Dict[str, Any]:
    """Create multipart payload with text and attachment.
    
    Args:
        text: Email body text
        attachment_name: Filename for attachment
        
    Returns:
        Gmail API payload with text part and attachment
    """
    text_encoded = base64.urlsafe_b64encode(text.encode('utf-8')).decode('ascii')
    
    return {
        "mimeType": "multipart/mixed",
        "parts": [
            {
                "mimeType": "text/plain",
                "body": {
                    "data": text_encoded,
                    "size": len(text)
                }
            },
            {
                "mimeType": "application/pdf",
                "filename": attachment_name,
                "body": {
                    "attachmentId": "abc123",
                    "size": 50000
                }
            }
        ]
    }


def make_long_email_payload(num_paragraphs: int = 50) -> Dict[str, Any]:
    """Create payload with very long email body.
    
    Args:
        num_paragraphs: Number of paragraphs to generate
        
    Returns:
        Gmail API payload with long text content
    """
    paragraphs = [
        f"This is paragraph {i+1}. Lorem ipsum dolor sit amet, consectetur "
        f"adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua."
        for i in range(num_paragraphs)
    ]
    text = "\n\n".join(paragraphs)
    encoded = base64.urlsafe_b64encode(text.encode('utf-8')).decode('ascii')
    
    return {
        "mimeType": "text/plain",
        "body": {
            "data": encoded,
            "size": len(text)
        }
    }
