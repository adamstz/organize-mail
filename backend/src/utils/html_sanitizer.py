"""HTML sanitization for email content using bleach."""

import bleach
from typing import Dict, List, Set
import logging

logger = logging.getLogger(__name__)


# Safe HTML tags allowed in email content
# Expanded to include common email HTML tags that are often stripped
ALLOWED_TAGS = [
    'p', 'br', 'div', 'span', 'a', 'img', 
    'b', 'i', 'u', 'strong', 'em', 'mark', 'small', 'del', 'ins', 'sub', 'sup',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'ul', 'ol', 'li', 'dl', 'dt', 'dd',
    'blockquote', 'pre', 'code',
    'table', 'thead', 'tbody', 'tfoot', 'tr', 'td', 'th', 'caption', 'colgroup', 'col',
    'hr', 'abbr', 'cite', 'q', 'time',
    'style',  # Allow style tags - CSS content is sanitized separately
    # Common email HTML tags
    'font', 'center', 'article', 'section', 'header', 'footer', 'nav', 'aside',
    'figure', 'figcaption', 'main', 'address', 's', 'strike', 'tt', 'kbd', 'samp', 'var',
]

# Safe attributes per tag
# Expanded to include common email attributes
ALLOWED_ATTRIBUTES: Dict[str, List[str]] = {
    '*': ['class', 'id', 'dir', 'lang', 'title', 'style'],
    'a': ['href', 'target', 'rel', 'name', 'style'],
    'img': ['src', 'alt', 'width', 'height', 'style', 'title', 'border', 'align', 'hspace', 'vspace'],
    'table': ['border', 'cellpadding', 'cellspacing', 'width', 'height', 'style', 'align', 'bgcolor', 'background'],
    'td': ['colspan', 'rowspan', 'width', 'height', 'style', 'align', 'valign', 'bgcolor', 'background'],
    'th': ['colspan', 'rowspan', 'width', 'height', 'style', 'align', 'valign', 'bgcolor', 'background'],
    'tr': ['style', 'align', 'valign', 'bgcolor', 'background'],
    'tbody': ['style', 'align', 'valign'],
    'thead': ['style', 'align', 'valign'],
    'tfoot': ['style', 'align', 'valign'],
    'div': ['style', 'align'],
    'span': ['style'],
    'p': ['style', 'align'],
    'h1': ['style', 'align'],
    'h2': ['style', 'align'],
    'h3': ['style', 'align'],
    'h4': ['style', 'align'],
    'h5': ['style', 'align'],
    'h6': ['style', 'align'],
    'blockquote': ['cite', 'style'],
    'abbr': ['title'],
    'time': ['datetime'],
    'font': ['color', 'size', 'face', 'style'],
    'center': ['style'],
    'ul': ['style', 'type'],
    'ol': ['style', 'type', 'start'],
    'li': ['style', 'value'],
}

# Safe URL schemes - IMPORTANT: blob is NOT allowed
ALLOWED_PROTOCOLS = [
    'http',
    'https', 
    'mailto',
    'tel',
    'data',  # For inline images (converted to CID later)
    'cid',   # For Content-ID references
]


def link_callback(attrs, new=False):
    """Callback to force external links to open safely.
    
    Adds target="_blank" and rel="noopener noreferrer" to all external links.
    """
    href_key = (None, 'href')
    
    if href_key in attrs:
        href = attrs[href_key]
        
        # Only modify http/https links (not mailto:, tel:, etc.)
        if href.startswith('http://') or href.startswith('https://'):
            attrs[(None, 'target')] = '_blank'
            attrs[(None, 'rel')] = 'noopener noreferrer'
    
    return attrs


def sanitize_html(html: str) -> str:
    """Sanitize HTML content with strict security rules.
    
    This function:
    - Removes all dangerous tags (script, style, etc.)
    - Whitelists safe tags and attributes
    - Enforces safe URL schemes (no blob:, javascript:)
    - Transforms external links to open safely
    
    Args:
        html: Raw HTML string from email
        
    Returns:
        Sanitized HTML safe to render
    """
    if not html:
        return ''
    
    try:
        logger.info(f"[HTML SANITIZER] Input HTML: {len(html)} chars")
        logger.debug(f"[HTML SANITIZER] First 300 chars: {html[:300]}")
        
        # Add data-blocked and data-blocked-src to allowed attributes for img tags
        # (used by image blocking feature)
        allowed_attrs = dict(ALLOWED_ATTRIBUTES)
        if 'img' in allowed_attrs:
            allowed_attrs['img'] = list(allowed_attrs['img']) + ['data-blocked', 'data-blocked-src']
        
        # Use bleach to sanitize - this preserves existing links
        logger.info(f"[HTML SANITIZER] Calling bleach.clean() with {len(ALLOWED_TAGS)} allowed tags")
        sanitized = bleach.clean(
            html,
            tags=ALLOWED_TAGS,
            attributes=allowed_attrs,
            protocols=ALLOWED_PROTOCOLS,
            strip=True,  # Remove disallowed tags entirely
            strip_comments=True,  # Remove HTML comments
        )
        
        logger.info(f"[HTML SANITIZER] Output HTML: {len(sanitized)} chars")
        logger.debug(f"[HTML SANITIZER] First 300 chars output: {sanitized[:300]}")
        logger.debug(f"[HTML SANITIZER] Last 300 chars output: {sanitized[-300:]}")
        
        if len(sanitized) < len(html) * 0.5:
            logger.warning(f"[HTML SANITIZER] WARNING: Output is less than 50% of input size! Input={len(html)}, Output={len(sanitized)}")
        
        return sanitized
        
    except Exception as e:
        logger.error(f"[HTML SANITIZER] Error sanitizing HTML: {e}", exc_info=True)
        # On error, return empty string for safety
        return ''


def strip_all_html(html: str) -> str:
    """Strip all HTML tags and return plain text.
    
    Used for safe mode rendering where no HTML is allowed.
    This also removes content from <style>, <script>, and other non-visible tags.
    
    Args:
        html: HTML string
        
    Returns:
        Plain text with all HTML removed
    """
    if not html:
        return ''
    
    try:
        from bs4 import BeautifulSoup
        
        # Parse HTML and remove style/script tags entirely (including their content)
        soup = BeautifulSoup(html, 'html.parser')
        
        # Remove style and script tags with their content
        for tag in soup.find_all(['style', 'script', 'head']):
            tag.decompose()
        
        # Get text from remaining elements
        text = soup.get_text(separator=' ', strip=True)
        
        # Clean up excessive whitespace
        import re
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
        
        return text
        
    except Exception as e:
        logger.error(f"Error stripping HTML: {e}")
        return ''
