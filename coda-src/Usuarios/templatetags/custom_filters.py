from django import template

register = template.Library()

@register.filter
def get_item(dictionary:dict, key):
    return dictionary.get(key)