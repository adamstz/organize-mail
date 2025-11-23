import React, { useMemo } from 'react';
import { Box, Typography, Alert, Button } from '@mui/material';
import DOMPurify from 'isomorphic-dompurify';
import VisibilityIcon from '@mui/icons-material/Visibility';
import VisibilityOffIcon from '@mui/icons-material/VisibilityOff';
import ImageIcon from '@mui/icons-material/Image';
import SecurityIcon from '@mui/icons-material/Security';

interface EmailBodyRendererProps {
  html: string;
  plainText: string;
}

const EmailBodyRenderer: React.FC<EmailBodyRendererProps> = ({
  html,
  plainText
}) => {
  const [imagesEnabled, setImagesEnabled] = React.useState(false);

  // Process HTML client-side: sanitize and optionally block images
  const processedHtml = useMemo(() => {
    if (!html) return { html: '', stats: { externalImages: 0, trackingPixels: 0 } };

    let processedHtml = html;
    let externalImageCount = 0;
    let trackingPixelCount = 0;

    // If images are blocked, replace external image sources with placeholders
    if (!imagesEnabled) {
      const parser = new DOMParser();
      const doc = parser.parseFromString(html, 'text/html');

      const images = doc.querySelectorAll('img');
      images.forEach((img) => {
        const src = img.getAttribute('src') || '';

        // Check if it's an external image (http/https)
        if (src.startsWith('http://') || src.startsWith('https://')) {
          // Check if it's a tracking pixel (1x1 or hidden)
          const width = img.getAttribute('width') || '';
          const height = img.getAttribute('height') || '';
          const style = img.getAttribute('style') || '';

          const isTrackingPixel = (
            (width === '1' && height === '1') ||
            (width === '0' || height === '0') ||
            style.includes('display:none') ||
            style.includes('display: none') ||
            style.includes('visibility:hidden') ||
            style.includes('visibility: hidden')
          );

          if (isTrackingPixel) {
            // Remove tracking pixels entirely
            img.remove();
            trackingPixelCount++;
          } else {
            // Block external images with placeholder
            img.setAttribute('data-blocked-src', src);
            img.setAttribute('src', 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="100" height="100"%3E%3Crect fill="%23ddd" width="100" height="100"/%3E%3Ctext x="50" y="50" text-anchor="middle" fill="%23999" font-size="12"%3EImage Blocked%3C/text%3E%3C/svg%3E');
            img.setAttribute('data-blocked', 'true');
            externalImageCount++;
          }
        }
      });

      processedHtml = doc.body.innerHTML;
    }

    // Sanitize with DOMPurify
    const sanitized = DOMPurify.sanitize(processedHtml, {
      ALLOWED_TAGS: [
        'p', 'br', 'div', 'span', 'a', 'img', 'b', 'i', 'u', 'strong', 'em', 'mark', 'small',
        'del', 'ins', 'sub', 'sup', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li',
        'dl', 'dt', 'dd', 'blockquote', 'pre', 'code', 'table', 'thead', 'tbody', 'tfoot',
        'tr', 'td', 'th', 'caption', 'colgroup', 'col', 'hr', 'abbr', 'cite', 'q', 'time',
        'style', 'font', 'center', 'article', 'section', 'header', 'footer', 'nav', 'aside',
        'figure', 'figcaption', 'main', 'address', 's', 'strike', 'tt', 'kbd', 'samp', 'var',
      ],
      ALLOWED_ATTR: [
        'href', 'src', 'alt', 'title', 'target', 'rel', 'style', 'data-blocked', 'data-blocked-src',
        'class', 'id', 'dir', 'lang', 'width', 'height', 'border', 'align', 'valign', 'bgcolor',
        'background', 'cellpadding', 'cellspacing', 'colspan', 'rowspan', 'hspace', 'vspace',
        'color', 'size', 'face', 'type', 'start', 'value', 'cite', 'datetime', 'name',
      ],
      ALLOWED_URI_REGEXP: /^(?:(?:(?:f|ht)tps?|mailto|tel|callto|cid|data):|[^a-z]|[a-z+.\-]+(?:[^a-z+.\-:]|$))/i,
    });

    return {
      html: sanitized,
      stats: {
        externalImages: externalImageCount,
        trackingPixels: trackingPixelCount
      }
    };
  }, [html, imagesEnabled]);

  const { externalImages, trackingPixels } = processedHtml.stats;
  const hasExternalImages = externalImages > 0;
  const hasTrackingPixels = trackingPixels > 0;

  // If no HTML, show plain text
  if (!html || html.trim().length === 0) {
    return (
      <Box>
        <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', color: 'text.secondary' }}>
          {plainText || 'No content available'}
        </Typography>
      </Box>
    );
  }

  return (
    <Box>
      {/* Image blocking info/controls */}
      {hasExternalImages && (
        <Alert
          severity={imagesEnabled ? "warning" : "info"}
          icon={<ImageIcon />}
          sx={{ mb: 2 }}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 2 }}>
            <Box>
              {imagesEnabled ? (
                <Typography variant="body2">
                  📷 Images loaded ({externalImages}) - External servers can see your IP address
                </Typography>
              ) : (
                <Typography variant="body2">
                  📷 {externalImages} external images blocked for privacy
                </Typography>
              )}
              {hasTrackingPixels && (
                <Typography variant="caption" color="text.secondary">
                  ✓ {trackingPixels} tracking pixel(s) removed
                </Typography>
              )}
            </Box>
            <Box sx={{ display: 'flex', gap: 1 }}>
              {!imagesEnabled && (
                <Button
                  size="small"
                  startIcon={<VisibilityIcon />}
                  onClick={() => setImagesEnabled(true)}
                  variant="contained"
                >
                  Load Images
                </Button>
              )}
              {imagesEnabled && (
                <Button
                  size="small"
                  startIcon={<VisibilityOffIcon />}
                  onClick={() => setImagesEnabled(false)}
                  variant="outlined"
                >
                  Block Images Again
                </Button>
              )}
            </Box>
          </Box>
        </Alert>
      )}

      {/* Tracking pixels removed notice (when no external images) */}
      {!hasExternalImages && hasTrackingPixels && (
        <Alert
          severity="success"
          icon={<SecurityIcon />}
          sx={{ mb: 2 }}
        >
          <Typography variant="body2">
            ✓ {trackingPixels} tracking pixel(s) removed
          </Typography>
        </Alert>
      )}

      {/* Sanitized HTML content */}
      <Box
        sx={{
          '& img': {
            maxWidth: '100%',
            height: 'auto',
          },
          '& a': {
            color: 'primary.main',
            textDecoration: 'underline',
          },
          wordBreak: 'break-word',
        }}
        dangerouslySetInnerHTML={{ __html: processedHtml.html }}
      />
    </Box>
  );
};

export default EmailBodyRenderer;
