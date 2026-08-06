from django import template
from django.utils.safestring import mark_safe
import markdown as md

register = template.Library()


@register.filter
def markdown_render(value):
    """Convierte texto Markdown a HTML seguro (sin ejecutar HTML crudo)."""
    if not value:
        return ''
    return mark_safe(md.markdown(value))
