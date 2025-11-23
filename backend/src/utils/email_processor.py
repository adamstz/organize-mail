"""Email processing pipeline with security and privacy features."""

from bs4 import BeautifulSoup
from typing import Dict, List, Tuple
import logging
import re

from .html_sanitizer import sanitize_html, strip_all_html
from .css_sanitizer import sanitize_css_block, sanitize_inline_style

logger = logging.getLogger(__name__)


class EmailProcessingResult:
    """Result of email processing."""
    
    def __init__(self):
        self.sanitized_html: str = ''
        self.plain_text: str = ''
        self.has_external_images: bool = False
        self.external_image_count: int = 0
        self.tracking_pixels_removed: int = 0
        self.has_blocked_content: bool = False
        self.inline_images: List[Dict] = []
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for API response."""
        return {
            'sanitized_html': self.sanitized_html,
            'plain_text': self.plain_text,
            'has_external_images': self.has_external_images,
            'external_image_count': self.external_image_count,
            'tracking_pixels_removed': self.tracking_pixels_removed,
            'has_blocked_content': self.has_blocked_content,
            'inline_images': self.inline_images,
        }


def is_tracking_pixel(img_tag) -> bool:
    """Detect if an image tag is likely a tracking pixel.
    
    Tracking pixels are typically:
    - 1x1 or 0x0 dimensions
    - Very small file sizes
    - Hidden (display: none, visibility: hidden)
    
    Args:
        img_tag: BeautifulSoup img tag
        
    Returns:
        True if likely a tracking pixel
    """
    # Check width/height attributes
    width = img_tag.get('width', '')
    height = img_tag.get('height', '')
    
    try:
        # Check for 0 or 1 pixel dimensions
        if width and height:
            w = int(re.sub(r'[^\d]', '', str(width)))
            h = int(re.sub(r'[^\d]', '', str(height)))
            if (w <= 1 and h <= 1) or (w == 0 or h == 0):
                return True
    except (ValueError, TypeError):
        pass
    
    # Check style attribute for tiny dimensions or hidden
    style = img_tag.get('style', '')
    if style:
        style_lower = style.lower()
        # Check for hidden
        if 'display:none' in style_lower.replace(' ', '') or \
           'display: none' in style_lower or \
           'visibility:hidden' in style_lower.replace(' ', '') or \
           'visibility: hidden' in style_lower:
            return True
        
        # Check for tiny dimensions in style
        if 'width:0' in style_lower.replace(' ', '') or \
           'width:1px' in style_lower.replace(' ', '') or \
           'height:0' in style_lower.replace(' ', '') or \
           'height:1px' in style_lower.replace(' ', ''):
            return True
    
    return False


def is_external_image(img_tag) -> bool:
    """Check if an image is external (not data: or cid:).
    
    Args:
        img_tag: BeautifulSoup img tag
        
    Returns:
        True if image is external (http/https)
    """
    src = img_tag.get('src', '')
    if not src:
        return False
    
    src_lower = src.lower()
    return src_lower.startswith('http://') or src_lower.startswith('https://')


def process_email_html(html: str, block_images: bool = True) -> EmailProcessingResult:
    """Process email HTML with security and privacy features.
    
    OPTIMIZED PIPELINE:
    1. Sanitize with bleach FIRST (removes scripts, dangerous tags)
    2. Single BeautifulSoup parse
    3. Single-pass processing (images, CSS, preheaders)
    4. Return results
    
    Args:
        html: Raw HTML from email
        block_images: Whether to block external images (default: True)
        
    Returns:
        EmailProcessingResult with sanitized content
    """
    result = EmailProcessingResult()
    
    if not html:
        return result
    
    try:
        print("=" * 80)
        print(f"[PROCESSOR] INPUT HTML ({len(html)} chars)")
        print("=" * 80)
        print(f"FIRST 1000 CHARS:\n{html[:1000]}")
        print("-" * 80)
        print(f"LAST 1000 CHARS:\n{html[-1000:]}")
        print("=" * 80)
        
        logger.info(f"[EMAIL PROCESSOR] Starting processing: input HTML length = {len(html)} chars")
        
        # PERFORMANCE: Generate plain text first (simple operation)
        result.plain_text = strip_all_html(html)
        logger.info(f"[EMAIL PROCESSOR] Plain text generated: {len(result.plain_text)} chars")
        
        # PERFORMANCE: Sanitize FIRST with bleach (single parse, removes dangerous content)
        # This is faster than parsing with BeautifulSoup first, then sanitizing
        logger.info(f"[EMAIL PROCESSOR] Starting bleach sanitization on {len(html)} chars")
        sanitized = sanitize_html(html)
        logger.info(f"[EMAIL PROCESSOR] After bleach sanitization: {len(sanitized)} chars")
        
        print("=" * 80)
        print(f"[PROCESSOR] AFTER BLEACH ({len(sanitized)} chars)")
        print("=" * 80)
        print(f"FIRST 1000 CHARS:\n{sanitized[:1000]}")
        print("-" * 80)
        print(f"LAST 1000 CHARS:\n{sanitized[-1000:]}")
        print("=" * 80)
        
        # Early exit if sanitization produced empty result
        if not sanitized or len(sanitized.strip()) < 10:
            # Original was substantial but sanitization stripped everything
            # This is a sign of overly aggressive sanitization
            logger.error(
                f"[EMAIL PROCESSOR] WARNING: Sanitization produced empty/tiny result! "
                f"Original: {len(html)} chars -> Sanitized: {len(sanitized)} chars. "
                f"Returning with plain text only."
            )
            result.sanitized_html = ''
            return result
        
        # PERFORMANCE: Parse sanitized HTML once with BeautifulSoup
        logger.info(f"[EMAIL PROCESSOR] Parsing with BeautifulSoup")
        soup = BeautifulSoup(sanitized, 'html.parser')
        logger.info(f"[EMAIL PROCESSOR] BeautifulSoup parsing complete")
        
        # PERFORMANCE: Sanitize CSS in style tags (only if they exist)
        style_tags = soup.find_all('style')
        if style_tags:
            for style_tag in style_tags:
                if style_tag.string:
                    style_tag.string = sanitize_css_block(style_tag.string)
        
        # PERFORMANCE: Single-pass image processing
        img_tags = soup.find_all('img')
        if img_tags:
            for img in img_tags:
                # Check if it's a tracking pixel
                if is_tracking_pixel(img):
                    logger.debug(f"Removing tracking pixel: {img.get('src', '')[:100]}")
                    img.decompose()
                    result.tracking_pixels_removed += 1
                    continue
                
                # Check if external image
                if is_external_image(img):
                    result.has_external_images = True
                    result.external_image_count += 1
                    
                    if block_images:
                        # Replace with placeholder
                        img['data-blocked-src'] = img.get('src', '')
                        img['src'] = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="100" height="100"%3E%3Crect fill="%23ddd" width="100" height="100"/%3E%3Ctext x="50" y="50" text-anchor="middle" fill="%23999" font-size="12"%3EImage Blocked%3C/text%3E%3C/svg%3E'
                        img['data-blocked'] = 'true'
                        result.has_blocked_content = True
                
                # Sanitize inline styles (only if present)
                if img.get('style'):
                    img['style'] = sanitize_inline_style(img['style'])
        
        # PERFORMANCE: Sanitize inline styles on other elements (only if style attr exists)
        # This is more efficient than iterating ALL tags
        styled_tags = soup.find_all(style=True)
        if styled_tags:
            for tag in styled_tags:
                # Skip images - already processed above
                if tag.name != 'img':
                    tag['style'] = sanitize_inline_style(tag['style'])
        
        # PERFORMANCE: Remove hidden preheader divs only if divs exist
        div_tags = soup.find_all('div', style=True)
        if div_tags:
            for div in div_tags:
                style = div.get('style', '').lower()
                if 'display:none' in style.replace(' ', '') or 'display: none' in style:
                    # Check if it's a preheader (usually contains text but no other content)
                    if div.get_text(strip=True) and not div.find_all(['img', 'a', 'button']):
                        logger.debug("Removing hidden preheader div")
                        div.decompose()
        
        # Convert to final HTML string
        result.sanitized_html = str(soup)
        
        print("=" * 80)
        print(f"[PROCESSOR] FINAL OUTPUT ({len(result.sanitized_html)} chars)")
        print("=" * 80)
        print(f"FIRST 1000 CHARS:\n{result.sanitized_html[:1000]}")
        print("-" * 80)
        print(f"LAST 1000 CHARS:\n{result.sanitized_html[-1000:]}")
        print("=" * 80)
        print(f"✓ External images: {result.external_image_count}")
        print(f"✓ Tracking pixels removed: {result.tracking_pixels_removed}")
        print("=" * 80)
        
        logger.info(
            f"Processed email: {result.tracking_pixels_removed} tracking pixels removed, "
            f"{result.external_image_count} external images detected"
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error processing email HTML: {e}", exc_info=True)
        # On error, return safe plain text only
        result.sanitized_html = ''
        result.plain_text = strip_all_html(html)
        return result


def extract_plain_text(html: str) -> str:
    """Extract plain text from HTML email.
    
    Convenience function for getting just the text.
    
    Args:
        html: HTML content
        
    Returns:
        Plain text
    """
    return strip_all_html(html)
