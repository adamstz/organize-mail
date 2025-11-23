"""CSS sanitization for email content."""

import re
import logging
from typing import List, Set

logger = logging.getLogger(__name__)


# Dangerous CSS at-rules that should be blocked
DISALLOWED_AT_RULES = {
    '@import',
    '@keyframes', 
    '@-webkit-keyframes',
    '@-moz-keyframes',
}

# Dangerous CSS functions
DISALLOWED_FUNCTIONS = {
    'expression',  # IE-specific, can execute JavaScript
    'url',         # Can be used for tracking/exfiltration (we'll handle separately)
    'javascript',
}

# Safe CSS properties whitelist (basic styling only)
ALLOWED_PROPERTIES = {
    # Font properties
    'font-family', 'font-size', 'font-weight', 'font-style', 'font-variant',
    'line-height', 'letter-spacing', 'word-spacing', 'text-transform',
    
    # Text properties
    'color', 'text-align', 'text-decoration', 'text-indent', 'vertical-align',
    'white-space', 'word-wrap', 'word-break', 'overflow-wrap',
    
    # Box model
    'margin', 'margin-top', 'margin-right', 'margin-bottom', 'margin-left',
    'padding', 'padding-top', 'padding-right', 'padding-bottom', 'padding-left',
    'width', 'height', 'max-width', 'max-height', 'min-width', 'min-height',
    
    # Border
    'border', 'border-top', 'border-right', 'border-bottom', 'border-left',
    'border-width', 'border-style', 'border-color', 'border-radius',
    'border-collapse', 'border-spacing',
    
    # Background (limited)
    'background', 'background-color',
    
    # Display and positioning (limited)
    'display', 'visibility', 'opacity',
    
    # Table
    'table-layout', 'empty-cells', 'caption-side',
    
    # Lists
    'list-style', 'list-style-type', 'list-style-position',
}


def sanitize_css_block(css: str) -> str:
    """Sanitize a CSS block (e.g., from <style> tag).
    
    This removes:
    - Dangerous at-rules (@import, @keyframes)
    - Dangerous functions (expression(), url())
    - Properties not in whitelist
    
    Args:
        css: CSS content from <style> tag
        
    Returns:
        Sanitized CSS
    """
    if not css:
        return ''
    
    try:
        # Remove dangerous at-rules
        for at_rule in DISALLOWED_AT_RULES:
            # Match @rule { ... } including nested braces
            pattern = rf'{re.escape(at_rule)}\s+[^{{]*\{{(?:[^{{}}]*|\{{[^}}]*\}})*\}}'
            css = re.sub(pattern, '', css, flags=re.IGNORECASE | re.DOTALL)
        
        # Remove dangerous functions
        for func in DISALLOWED_FUNCTIONS:
            # Match function calls like expression(...) or url(...)
            pattern = rf'{re.escape(func)}\s*\([^)]*\)'
            css = re.sub(pattern, '', css, flags=re.IGNORECASE)
        
        # Filter CSS properties
        css = filter_css_properties(css)
        
        return css
        
    except Exception as e:
        logger.error(f"Error sanitizing CSS block: {e}")
        # On error, remove all CSS for safety
        return ''


def filter_css_properties(css: str) -> str:
    """Filter CSS to only allowed properties.
    
    Args:
        css: CSS content
        
    Returns:
        CSS with only whitelisted properties
    """
    if not css:
        return ''
    
    try:
        # Split into rules
        lines = []
        
        # Simple property filter: find property: value; pairs
        for line in css.split('\n'):
            # Check if line contains CSS rule
            if ':' in line and ';' in line:
                # Extract property name
                match = re.match(r'\s*([a-z-]+)\s*:', line, re.IGNORECASE)
                if match:
                    prop = match.group(1).lower()
                    # Only keep if in whitelist
                    if prop in ALLOWED_PROPERTIES:
                        lines.append(line)
                else:
                    # Keep selectors and braces
                    if re.match(r'\s*[{}]', line) or re.match(r'.*\{$', line):
                        lines.append(line)
            else:
                # Keep selectors and structural elements
                lines.append(line)
        
        return '\n'.join(lines)
        
    except Exception as e:
        logger.error(f"Error filtering CSS properties: {e}")
        return ''


def sanitize_inline_style(style: str) -> str:
    """Sanitize inline style attribute.
    
    Args:
        style: Value of style="" attribute
        
    Returns:
        Sanitized style value
    """
    if not style:
        return ''
    
    try:
        # Remove dangerous functions
        for func in DISALLOWED_FUNCTIONS:
            pattern = rf'{re.escape(func)}\s*\([^)]*\)'
            style = re.sub(pattern, '', style, flags=re.IGNORECASE)
        
        # Filter properties
        properties = []
        for declaration in style.split(';'):
            declaration = declaration.strip()
            if ':' in declaration:
                prop_name = declaration.split(':')[0].strip().lower()
                if prop_name in ALLOWED_PROPERTIES:
                    properties.append(declaration)
        
        return '; '.join(properties)
        
    except Exception as e:
        logger.error(f"Error sanitizing inline style: {e}")
        return ''
