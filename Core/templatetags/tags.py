from django import template

register = template.Library()

@register.simple_tag(takes_context=True)
def url_replace(context, **kwargs):
    params = context['request'].GET.copy()
    for k, v in kwargs.items():
        params[k] = v
    return '?' + params.urlencode()

@register.filter
def coverselection(playlist,index):
    if playlist.select_cover(index):
        return playlist.select_cover(index)
    else: 
        return 'media/default-cover.png'