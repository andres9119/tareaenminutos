"""
Context processors globales para variables de SEO en el sitio público.
"""

from django.conf import settings


def seo_settings(request):
    """Expone los valores de Google Analytics, Search Console y la URL base a los templates."""
    return {
        'GOOGLE_ANALYTICS_ID': getattr(settings, 'GOOGLE_ANALYTICS_ID', ''),
        'GOOGLE_SITE_VERIFICATION': getattr(settings, 'GOOGLE_SITE_VERIFICATION', ''),
        'SITE_BASE_URL': getattr(settings, 'SITE_BASE_URL', '').rstrip('/'),
    }
